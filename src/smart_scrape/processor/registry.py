"""Extractor registry with domain-first routing."""

from __future__ import annotations

import logging
from urllib.parse import urlparse

from smart_scrape.processor.base_extractor import BaseDealExtractor
from smart_scrape.processor.deal_extractor import RetailMeNotExtractor
from smart_scrape.processor.generic_extractor import GenericDealExtractor
from smart_scrape.processor.models import DealCandidate

logger = logging.getLogger(__name__)


def _extract_domain(url: str) -> str:
    """Return the lowercase netloc from a URL."""
    parsed = urlparse(url if "://" in url else f"https://{url}")
    return (parsed.netloc or "").lower()


class ExtractorRegistry:
    """O(1) domain-map lookup → generic fallback.

    Usage::

        registry = ExtractorRegistry()
        extractor = registry.get_extractor(url, html)
        candidates = extractor.extract(html, text, url)
    """

    def __init__(self) -> None:
        self._domain_map: dict[str, BaseDealExtractor] = {}
        self._extractors: list[BaseDealExtractor] = []
        self._fallback = GenericDealExtractor()

    def register(self, extractor: BaseDealExtractor) -> None:
        """Register an extractor and map its supported domains."""
        self._extractors.append(extractor)
        for domain in extractor.supported_domains:
            self._domain_map[domain.lower()] = extractor
        logger.debug(
            "extractor_registered",
            extra={
                "name": extractor.name,
                "domains": extractor.supported_domains,
            },
        )

    def get_extractor(self, url: str, html: str = "") -> BaseDealExtractor:
        """Return the best extractor for the given URL.

        1. Fast domain-map lookup — O(1).
        2. Generic fallback — no O(N) HTML scan.
        """
        domain = _extract_domain(url)
        extractor = self._domain_map.get(domain)
        if extractor is not None:
            logger.debug(
                "extractor_matched",
                extra={"url": url, "extractor": extractor.name, "method": "domain"},
            )
            return extractor

        logger.debug(
            "extractor_fallback",
            extra={"url": url, "extractor": self._fallback.name},
        )
        return self._fallback

    def extract(
        self, html: str, text: str, url: str,
    ) -> list[DealCandidate]:
        """Convenience: pick the right extractor and run it."""
        extractor = self.get_extractor(url, html)
        return extractor.extract(html=html, text=text, url=url)


def build_default_registry() -> ExtractorRegistry:
    """Create and return a pre-configured registry."""
    registry = ExtractorRegistry()
    registry.register(RetailMeNotExtractor())
    return registry

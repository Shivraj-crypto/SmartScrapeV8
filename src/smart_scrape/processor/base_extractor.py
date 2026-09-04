"""Abstract base class for deal extractors."""

from __future__ import annotations

from abc import ABC, abstractmethod

from smart_scrape.processor.models import DealCandidate


class BaseDealExtractor(ABC):
    """Contract for site-specific and generic deal extractors."""

    __slots__ = ()

    name: str = ""
    supported_domains: tuple[str, ...] = ()

    @classmethod
    def is_configured(cls) -> bool:
        """Check if this extractor is properly configured."""
        return bool(cls.supported_domains and cls.name)

    @abstractmethod
    def extract(self, html: str, text: str, url: str) -> list[DealCandidate]:
        """Return deal candidates extracted from a page."""
        ...

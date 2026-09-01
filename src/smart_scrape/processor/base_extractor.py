"""Abstract base class for deal extractors."""

from __future__ import annotations

from abc import ABC, abstractmethod

from smart_scrape.processor.models import DealCandidate


class BaseDealExtractor(ABC):
    """Every site-specific (or generic) extractor inherits from this.

    Subclasses **must** set ``name`` and ``supported_domains`` at class
    level, and implement ``extract()``.
    """

    # Class attributes that subclasses should override
    name: str = ""
    supported_domains: list[str] = []

    @classmethod
    def is_configured(cls) -> bool:
        """Check if this extractor is properly configured."""
        return bool(cls.name and cls.supported_domains)

    @abstractmethod
    def extract(
        self, html: str, text: str, url: str
    ) -> list[DealCandidate]:
        """Return zero or more deal candidates from the given page.

        Every returned ``DealCandidate`` must have ``store``, ``offer``,
        and ``source`` populated.  Confidence is assigned by the shared
        ``score_candidate()`` utility in ``ranking.py`` — extractors
        should call it before returning.
        """
        ...

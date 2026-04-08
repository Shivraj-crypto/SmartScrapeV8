class ScraperError(Exception):
    """Base exception for scraper-related failures."""


class InvalidURLError(ScraperError):
    """Raised when a URL is malformed or unsupported."""


class NavigationError(ScraperError):
    """Raised when Playwright fails to load a page in time."""


class EmptyContentError(ScraperError):
    """Raised when scraping succeeds but no usable content is extracted."""

from __future__ import annotations

import logging
from time import perf_counter
from urllib.parse import urlparse

from scrapling.fetchers import DynamicFetcher

from smart_scrape.config import Settings
from smart_scrape.scraper.exceptions import EmptyContentError
from smart_scrape.scraper.exceptions import InvalidURLError
from smart_scrape.scraper.exceptions import NavigationError
from smart_scrape.scraper.exceptions import ScraperError
from smart_scrape.scraper.extractor import clean_html
from smart_scrape.scraper.extractor import html_to_text
from smart_scrape.scraper.models import ScrapeResult

logger = logging.getLogger(__name__)


def normalize_url(url: str) -> str:
    candidate = url.strip()
    if not candidate:
        raise InvalidURLError("URL cannot be empty.")

    parsed = urlparse(candidate)
    if not parsed.scheme:
        candidate = f"https://{candidate}"
        parsed = urlparse(candidate)

    if parsed.scheme not in {"http", "https"}:
        raise InvalidURLError("URL must use http or https.")

    if not parsed.netloc:
        raise InvalidURLError("URL is missing a valid domain.")

    return candidate


def _decode_body(body: bytes, encoding: str | None) -> str:
    if not body:
        return ""
    return body.decode(encoding or "utf-8", errors="replace")


def _extract_title(response: object) -> str:
    selector = getattr(response, "css", None)
    if not callable(selector):
        return ""

    title_selection = selector("title::text")
    if title_selection is None:
        return ""

    getter = getattr(title_selection, "get", None)
    if not callable(getter):
        return ""

    title = getter("")
    return title if isinstance(title, str) else ""


async def scrape_page(url: str, settings: Settings | None = None) -> ScrapeResult:
    current_settings = settings or Settings.from_env()
    normalized_url = normalize_url(url)

    logger.debug("scrape_start", extra={"url": normalized_url})
    started_at = perf_counter()

    try:
        response = await DynamicFetcher.async_fetch(
            normalized_url,
            headless=current_settings.headless,
            network_idle=current_settings.wait_for_network_idle,
            timeout=current_settings.navigation_timeout_ms,
        )

        raw_html = _decode_body(response.body, getattr(response, "encoding", None))
        cleaned_html = clean_html(raw_html)
        if not cleaned_html:
            raise EmptyContentError(
                f"No usable content was extracted from {normalized_url}."
            )
        cleaned_text = html_to_text(cleaned_html)

        elapsed_ms = int((perf_counter() - started_at) * 1000)

        logger.debug(
            "scrape_complete",
            extra={
                "url": normalized_url,
                "elapsed_ms": elapsed_ms,
                "status_code": getattr(response, "status", None),
                "html_size": len(cleaned_html),
                "text_size": len(cleaned_text),
            },
        )

        return ScrapeResult(
            requested_url=url,
            final_url=getattr(response, "url", normalized_url),
            title=_extract_title(response),
            raw_html=raw_html,
            cleaned_html=cleaned_html,
            cleaned_text=cleaned_text,
            status_code=getattr(response, "status", None),
            elapsed_ms=elapsed_ms,
        )
    except Exception as exc:
        if isinstance(exc, EmptyContentError):
            raise
        message = str(exc).lower()
        error_name = exc.__class__.__name__.lower()
        if "timeout" in error_name or "timed out" in message or "timeout" in message:
            raise NavigationError(
                f"Timed out while loading {normalized_url}. "
                "Try increasing SCRAPE_NAVIGATION_TIMEOUT_MS."
            ) from exc
        raise ScraperError(
            f"Scrapling failed while scraping {normalized_url}: {exc}"
        ) from exc

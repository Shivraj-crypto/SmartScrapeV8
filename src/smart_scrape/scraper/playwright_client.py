from __future__ import annotations

from time import perf_counter
from urllib.parse import urlparse

from playwright.async_api import Browser
from playwright.async_api import BrowserContext
from playwright.async_api import Error as PlaywrightError
from playwright.async_api import TimeoutError as PlaywrightTimeoutError
from playwright.async_api import async_playwright

from smart_scrape.config import Settings
from smart_scrape.scraper.exceptions import EmptyContentError
from smart_scrape.scraper.exceptions import InvalidURLError
from smart_scrape.scraper.exceptions import NavigationError
from smart_scrape.scraper.exceptions import ScraperError
from smart_scrape.scraper.extractor import clean_html
from smart_scrape.scraper.models import ScrapeResult


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


async def _safe_close_context(context: BrowserContext | None) -> None:
    if context is None:
        return
    try:
        await context.close()
    except PlaywrightError:
        pass


async def _safe_close_browser(browser: Browser | None) -> None:
    if browser is None:
        return
    try:
        await browser.close()
    except PlaywrightError:
        pass


async def scrape_page(url: str, settings: Settings | None = None) -> ScrapeResult:
    current_settings = settings or Settings.from_env()
    normalized_url = normalize_url(url)

    browser: Browser | None = None
    context: BrowserContext | None = None

    started_at = perf_counter()

    try:
        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch(headless=current_settings.headless)
            context = await browser.new_context()
            page = await context.new_page()

            # Use explicit timeouts to keep failures deterministic.
            page.set_default_navigation_timeout(current_settings.navigation_timeout_ms)
            page.set_default_timeout(current_settings.navigation_timeout_ms)

            response = await page.goto(normalized_url, wait_until="domcontentloaded")

            if current_settings.wait_for_network_idle:
                await page.wait_for_load_state(
                    "networkidle",
                    timeout=current_settings.navigation_timeout_ms,
                )

            raw_html = await page.content()
            cleaned_html = clean_html(raw_html)
            if not cleaned_html:
                raise EmptyContentError(
                    f"No usable content was extracted from {normalized_url}."
                )

            elapsed_ms = int((perf_counter() - started_at) * 1000)

            return ScrapeResult(
                requested_url=url,
                final_url=page.url,
                title=await page.title(),
                raw_html=raw_html,
                cleaned_html=cleaned_html,
                status_code=response.status if response is not None else None,
                elapsed_ms=elapsed_ms,
            )
    except PlaywrightTimeoutError as exc:
        raise NavigationError(
            f"Timed out while loading {normalized_url}. "
            "Try increasing SCRAPE_NAVIGATION_TIMEOUT_MS."
        ) from exc
    except PlaywrightError as exc:
        raise ScraperError(
            f"Playwright failed while scraping {normalized_url}: {exc}"
        ) from exc
    finally:
        await _safe_close_context(context)
        await _safe_close_browser(browser)

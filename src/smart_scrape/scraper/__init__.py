"""Scraper package exports."""

from smart_scrape.scraper.models import ScrapeResult
from smart_scrape.scraper.playwright_client import scrape_page

__all__ = ["ScrapeResult", "scrape_page"]

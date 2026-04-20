"""Question-answering module with Gemini integration."""

from smart_scrape.qa.llm_client import extract_deals_and_coupons_from_file
from smart_scrape.qa.llm_client import extract_deals_and_coupons_from_text

__all__ = ["extract_deals_and_coupons_from_file", "extract_deals_and_coupons_from_text"]

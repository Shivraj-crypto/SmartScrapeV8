"""Content processing utilities."""

from smart_scrape.processor.deal_extractor import extract_deal_candidates
from smart_scrape.processor.models import DealCandidate
from smart_scrape.processor.models import ExtractionReport

__all__ = ["DealCandidate", "ExtractionReport", "extract_deal_candidates"]

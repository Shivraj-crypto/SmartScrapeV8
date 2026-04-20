"""Content processing utilities."""

from smart_scrape.processor.base_extractor import BaseDealExtractor
from smart_scrape.processor.deal_extractor import RetailMeNotExtractor
from smart_scrape.processor.deal_extractor import extract_deal_candidates
from smart_scrape.processor.generic_extractor import GenericDealExtractor
from smart_scrape.processor.models import DealCandidate, ExtractionReport
from smart_scrape.processor.ranking import (
    deduplicate_candidates,
    normalize_candidates,
    rank_and_filter,
    score_candidate,
)
from smart_scrape.processor.registry import ExtractorRegistry, build_default_registry

__all__ = [
    "BaseDealExtractor",
    "DealCandidate",
    "ExtractionReport",
    "ExtractorRegistry",
    "GenericDealExtractor",
    "RetailMeNotExtractor",
    "build_default_registry",
    "deduplicate_candidates",
    "extract_deal_candidates",
    "normalize_candidates",
    "rank_and_filter",
    "score_candidate",
]

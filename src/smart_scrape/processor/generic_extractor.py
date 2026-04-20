"""Generic text-based deal extractor.

Falls back to regex pattern matching on the cleaned text when no
site-specific extractor matches the URL.
"""

from __future__ import annotations

import logging
import re

from smart_scrape.processor.base_extractor import BaseDealExtractor
from smart_scrape.processor.models import DealCandidate
from smart_scrape.processor.ranking import (
    PERCENT_OFF_PATTERN,
    AMOUNT_OFF_PATTERN,
    UP_TO_AMOUNT_OFF_PATTERN,
    CASHBACK_PATTERN,
    BOGO_PATTERN,
    score_candidate,
)

logger = logging.getLogger(__name__)

_FREE_SHIPPING_PATTERN = re.compile(r"\bfree shipping\b", re.IGNORECASE)
_COUPON_CODE_PATTERN = re.compile(
    r"\b(?:code|coupon|promo)[:\s]+([A-Z0-9]{4,20})\b", re.IGNORECASE,
)

# Minimum line length to consider as potential deal text
_MIN_LINE_LEN = 10
# Maximum line length — very long lines are almost certainly page noise
_MAX_LINE_LEN = 300


class GenericDealExtractor(BaseDealExtractor):
    """Regex-based extractor that works on raw cleaned text."""

    name = "generic"
    supported_domains: list[str] = []  # catches everything not routed elsewhere

    def extract(
        self, html: str, text: str, url: str,
    ) -> list[DealCandidate]:
        if not text.strip():
            return []

        candidates: list[DealCandidate] = []
        seen_offers: set[str] = set()

        for line in text.splitlines():
            stripped = line.strip()
            if len(stripped) < _MIN_LINE_LEN or len(stripped) > _MAX_LINE_LEN:
                continue

            # Must contain at least one deal signal
            has_signal = any([
                PERCENT_OFF_PATTERN.search(stripped),
                AMOUNT_OFF_PATTERN.search(stripped),
                _FREE_SHIPPING_PATTERN.search(stripped),
                CASHBACK_PATTERN.search(stripped),
                BOGO_PATTERN.search(stripped),
                _COUPON_CODE_PATTERN.search(stripped),
            ])
            if not has_signal:
                continue

            # Simple dedup by normalised lowercase
            norm_key = re.sub(r"\s+", " ", stripped).lower()
            if norm_key in seen_offers:
                continue
            seen_offers.add(norm_key)

            candidate = self._parse_line(stripped, url)
            candidate.confidence = score_candidate(candidate)
            if candidate.confidence >= 0.35:
                candidates.append(candidate)

        candidates.sort(key=lambda c: c.confidence, reverse=True)
        logger.debug(
            "generic_extract_done",
            extra={"url": url, "candidates_found": len(candidates)},
        )
        return candidates

    # ------------------------------------------------------------------

    def _parse_line(self, line: str, url: str) -> DealCandidate:
        offer_type: str | None = None
        discount_percent: float | None = None
        discount_amount: str | None = None
        max_discount_amount: str | None = None
        cashback_percent: float | None = None
        coupon_code: str | None = None

        # Detect signals
        pct = PERCENT_OFF_PATTERN.search(line)
        if pct:
            discount_percent = float(pct.group(1))
            offer_type = "SALE"

        amt = AMOUNT_OFF_PATTERN.search(line)
        if amt and not UP_TO_AMOUNT_OFF_PATTERN.search(line):
            discount_amount = amt.group(1)
            offer_type = "SALE"

        upto = UP_TO_AMOUNT_OFF_PATTERN.search(line)
        if upto:
            max_discount_amount = upto.group(1)

        cb = CASHBACK_PATTERN.search(line)
        if cb:
            cashback_percent = float(cb.group(1))
            offer_type = "REWARD"

        if _FREE_SHIPPING_PATTERN.search(line):
            offer_type = "SHIPPING"

        if BOGO_PATTERN.search(line):
            offer_type = "BOGO"

        code = _COUPON_CODE_PATTERN.search(line)
        if code:
            coupon_code = code.group(1)
            offer_type = "COUPON"

        return DealCandidate(
            store="UNKNOWN_STORE",
            offer=line,
            source=self.name,
            normalized_line=line,
            offer_type=offer_type,
            coupon_code=coupon_code,
            discount_percent=discount_percent,
            discount_amount=discount_amount,
            max_discount_amount=max_discount_amount,
            cashback_percent=cashback_percent,
        )

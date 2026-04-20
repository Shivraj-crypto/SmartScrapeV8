"""Ranking, normalisation and deduplication for deal candidates."""

from __future__ import annotations

import re

from smart_scrape.processor.models import DealCandidate


# ------------------------------------------------------------------
# Regex patterns — shared across all extractors
# ------------------------------------------------------------------

PERCENT_OFF_PATTERN = re.compile(r"(\d+(?:\.\d+)?)\s*%\s+off\b", re.IGNORECASE)
AMOUNT_OFF_PATTERN = re.compile(r"([$]\d+(?:\.\d{1,2})?)\s+off\b", re.IGNORECASE)
UP_TO_AMOUNT_OFF_PATTERN = re.compile(
    r"\bup to\s+([$]\d+(?:\.\d{1,2})?)\s+off\b", re.IGNORECASE,
)
CASHBACK_PATTERN = re.compile(
    r"(\d+(?:\.\d+)?)\s*%\s+(?:cash\s*back|back)\b", re.IGNORECASE,
)
BOGO_PATTERN = re.compile(r"\bbuy\s+\d+,\s*get\s+\d+\b|\bbogo\b", re.IGNORECASE)


# ------------------------------------------------------------------
# Shared scoring — every extractor delegates here
# ------------------------------------------------------------------

def score_candidate(candidate: DealCandidate) -> float:
    """Compute a standardised confidence score in ``[0.0, 1.0]``.

    The same formula is used regardless of which extractor produced the
    candidate, keeping scores comparable across sources.
    """
    score = 0.3
    offer_lower = (candidate.offer or "").lower()

    if candidate.offer_type == "COUPON":
        score += 0.15
        candidate.reasons.append("coupon")
    if candidate.offer_type == "REWARD":
        score += 0.10
        candidate.reasons.append("reward")
    if candidate.offer_type == "SALE":
        score += 0.05
        candidate.reasons.append("sale")
    if candidate.offer_type == "SHIPPING":
        score += 0.12
        candidate.reasons.append("shipping")
    if candidate.offer_type == "BOGO":
        score += 0.18
        candidate.reasons.append("bogo_type")

    if (
        candidate.discount_percent is not None
        or candidate.discount_amount is not None
        or AMOUNT_OFF_PATTERN.search(candidate.offer or "")
    ):
        score += 0.22
        candidate.reasons.append("discount")

    if candidate.cashback_percent is not None:
        score += 0.18
        candidate.reasons.append("cashback")
    if candidate.max_discount_amount:
        score += 0.08
        candidate.reasons.append("max_discount")
    if candidate.min_spend:
        score += 0.10
        candidate.reasons.append("min_spend")

    if candidate.expiry_type == "date":
        score += 0.12
        candidate.reasons.append("expiry_date")
    elif candidate.expiry_type == "relative":
        score += 0.04
        candidate.reasons.append("expiry_relative")

    if "free shipping" in offer_lower:
        score += 0.14
        candidate.reasons.append("free_shipping")
    if BOGO_PATTERN.search(offer_lower):
        score += 0.14
        candidate.reasons.append("bogo")
    if "up to" in offer_lower:
        score += 0.06
        candidate.reasons.append("up_to")
    if candidate.store:
        score += 0.05
        candidate.reasons.append("store")
    if candidate.offer_type in {"COUPON", "REWARD"}:
        score += 0.05
        candidate.reasons.append("strong_dom_type")

    return max(0.0, min(1.0, score))


# ------------------------------------------------------------------
# Canonical key for deduplication
# ------------------------------------------------------------------

def _canonical_offer_key(candidate: DealCandidate) -> str:
    offer = (candidate.offer or candidate.normalized_line).lower()
    offer = re.sub(
        r"^(flash sale!|labor day savings!|today only|limited time offer)\s*",
        "",
        offer,
    )
    offer = re.sub(r"\s+", " ", offer).strip()
    if candidate.discount_percent is not None:
        offer = re.sub(
            r"\b\d+(?:\.\d+)?%\s+off\b",
            f"{candidate.discount_percent:g}% off",
            offer,
        )
    if candidate.discount_amount:
        offer = re.sub(
            r"[$]\d+(?:\.\d{1,2})?\s+off\b",
            f"{candidate.discount_amount.lower()} off",
            offer,
        )
    return offer


# ------------------------------------------------------------------
# Pipeline stages
# ------------------------------------------------------------------

def normalize_candidates(candidates: list[DealCandidate]) -> list[DealCandidate]:
    """Standardise offer text and numeric fields across candidates."""
    for c in candidates:
        if c.offer:
            c.offer = re.sub(r"\s+", " ", c.offer).strip()
        if c.normalized_line:
            c.normalized_line = re.sub(r"\s+", " ", c.normalized_line).strip()
    return candidates


def deduplicate_candidates(candidates: list[DealCandidate]) -> list[DealCandidate]:
    """Remove duplicates using canonical offer key."""
    seen: set[str] = set()
    deduped: list[DealCandidate] = []
    for candidate in candidates:
        key = _canonical_offer_key(candidate)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(candidate)
    return deduped


def rank_and_filter(
    candidates: list[DealCandidate],
    *,
    min_confidence: float = 0.4,
    max_results: int | None = None,
) -> list[DealCandidate]:
    """Sort by confidence, drop low-quality, optionally cap count."""
    # 1. Remove below threshold
    filtered = [c for c in candidates if c.confidence >= min_confidence]
    # 2. Sort descending by confidence
    filtered.sort(key=lambda c: c.confidence, reverse=True)
    # 3. Cap if requested
    if max_results is not None and max_results > 0:
        filtered = filtered[:max_results]
    return filtered

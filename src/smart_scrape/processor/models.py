"""Data models for deal extraction."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class DealCandidate:
    """A single deal/coupon extracted from a page.

    Every extractor **must** populate ``store``, ``offer``, ``source``,
    and ``confidence``.  The shared ``score_candidate()`` utility in
    ``ranking.py`` handles confidence assignment to keep scoring
    consistent across extractors.
    """

    # ------------------------------------------------------------------
    # Identity — required by contract
    # ------------------------------------------------------------------
    store: str
    offer: str
    source: str  # extractor name, e.g. "retailmenot", "generic", "gemini"

    # ------------------------------------------------------------------
    # Normalised fields
    # ------------------------------------------------------------------
    offer_type: str | None = None       # COUPON | SALE | REWARD | SHIPPING | BOGO
    coupon_code: str | None = None
    discount_percent: float | None = None
    discount_amount: str | None = None
    max_discount_amount: str | None = None
    cashback_percent: float | None = None
    min_spend: str | None = None
    discount_type: str | None = None
    expiry: str | None = None
    expiry_type: str | None = None      # "date" | "relative"

    # ------------------------------------------------------------------
    # Quality
    # ------------------------------------------------------------------
    confidence: float = 0.0             # 0.0–1.0
    reasons: list[str] = field(default_factory=list)

    # ------------------------------------------------------------------
    # Raw (debugging / golden-test anchoring)
    # ------------------------------------------------------------------
    raw_html: str = ""
    normalized_line: str = ""

    # ------------------------------------------------------------------
    # Serialisation helpers
    # ------------------------------------------------------------------

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serialisable dictionary."""
        data: dict[str, Any] = {
            "store": self.store,
            "offer": self.offer,
            "source": self.source,
            "offer_type": self.offer_type,
            "coupon_code": self.coupon_code,
            "discount_percent": self.discount_percent,
            "discount_amount": self.discount_amount,
            "max_discount_amount": self.max_discount_amount,
            "cashback_percent": self.cashback_percent,
            "min_spend": self.min_spend,
            "discount_type": self.discount_type,
            "expiry": self.expiry,
            "expiry_type": self.expiry_type,
            "confidence": round(self.confidence, 3),
            "reasons": self.reasons,
        }
        return data

    def to_output_line(self) -> str:
        """Legacy pipe-delimited text line."""
        store = self.store or "UNKNOWN_STORE"
        offer = self.offer or self.normalized_line
        coupon_code = self.coupon_code or (self.offer_type or "NO_CODE")
        conditions_parts: list[str] = []
        if self.offer_type:
            conditions_parts.append(f"type={self.offer_type.lower()}")
        if self.cashback_percent is not None:
            conditions_parts.append(f"cashback={self.cashback_percent:g}%")
        if self.max_discount_amount:
            conditions_parts.append(f"max_discount={self.max_discount_amount}")
        if self.discount_amount:
            conditions_parts.append(f"discount_amount={self.discount_amount}")
        if self.discount_percent is not None:
            conditions_parts.append(f"discount={self.discount_percent:g}%")
        if self.discount_type:
            conditions_parts.append(f"discount_type={self.discount_type}")
        if self.expiry:
            conditions_parts.append(f"expiry={self.expiry}")
        if self.expiry_type:
            conditions_parts.append(f"expiry_type={self.expiry_type}")
        if self.min_spend:
            conditions_parts.append(f"min_spend={self.min_spend}")
        conditions_parts.append(f"confidence={self.confidence:.2f}")
        return f"{store} | {offer} | {coupon_code} | {', '.join(conditions_parts)}"


@dataclass(slots=True)
class ExtractionReport:
    """Result of an extraction run (heuristic + optional LLM fallback)."""

    candidates: list[DealCandidate]
    overall_confidence: float
    used_llm_fallback: bool = False
    fallback_response_text: str | None = None
    fallback_error: str | None = None

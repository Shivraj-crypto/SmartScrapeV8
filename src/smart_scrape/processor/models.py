from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class DealCandidate:
    source_line: str
    normalized_line: str
    store: str | None = None
    offer: str | None = None
    offer_type: str | None = None
    coupon_code: str | None = None
    cashback_percent: float | None = None
    max_discount_amount: str | None = None
    discount_amount: str | None = None
    discount_percent: float | None = None
    discount_type: str | None = None
    expiry: str | None = None
    expiry_type: str | None = None
    min_spend: str | None = None
    confidence: float = 0.0
    reasons: list[str] = field(default_factory=list)

    def to_output_line(self) -> str:
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
    candidates: list[DealCandidate]
    overall_confidence: float
    used_llm_fallback: bool = False
    fallback_response_text: str | None = None
    fallback_error: str | None = None

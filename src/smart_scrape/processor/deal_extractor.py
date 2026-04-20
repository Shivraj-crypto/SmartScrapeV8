from __future__ import annotations

import re

from bs4 import BeautifulSoup
from bs4.element import Tag

from smart_scrape.processor.models import DealCandidate
from smart_scrape.processor.models import ExtractionReport

EXPIRY_DATE_PATTERN = re.compile(
    r"\b([A-Za-z]{3,9}\s+\d{1,2},?\s+\d{4})\b",
    re.IGNORECASE,
)
EXPIRY_RELATIVE_PATTERN = re.compile(r"\b(expiring soon|limited time)\b", re.IGNORECASE)
MIN_SPEND_PATTERN = re.compile(
    r"\b(?:with|on|over|orders?\s+over|purchase|spend)\s+([$]\d+(?:\.\d{1,2})?\+?)",
    re.IGNORECASE,
)
AMOUNT_OFF_MIN_SPEND_PATTERN = re.compile(
    r"[$]\d+(?:\.\d{1,2})?\s+off\s+[$](\d+(?:\.\d{1,2})?\+?)",
    re.IGNORECASE,
)
PERCENT_OFF_PATTERN = re.compile(r"(\d+(?:\.\d+)?)\s*%\s+off\b", re.IGNORECASE)
AMOUNT_OFF_PATTERN = re.compile(r"([$]\d+(?:\.\d{1,2})?)\s+off\b", re.IGNORECASE)
UP_TO_AMOUNT_OFF_PATTERN = re.compile(
    r"\bup to\s+([$]\d+(?:\.\d{1,2})?)\s+off\b",
    re.IGNORECASE,
)
CASHBACK_PATTERN = re.compile(
    r"(\d+(?:\.\d+)?)\s*%\s+(?:cash\s*back|back)\b",
    re.IGNORECASE,
)
BOGO_PATTERN = re.compile(r"\bbuy\s+\d+,\s*get\s+\d+\b|\bbogo\b", re.IGNORECASE)
QUESTION_PREFIXES = ("how ", "what ", "are ", "does ", "do ", "can ", "is ", "why ", "when ")
NOISE_PHRASES = (
    "learn how we verify coupons",
    "submit a coupon",
    "why trust us",
    "featured articles",
    "store info",
    "frequently asked questions",
    "customer care",
    "return and refund policy",
    "shipping and delivery policy",
    "payment options",
    "how can i reach",
    "updated by",
    "content writer",
    "see bio",
    "popular stores",
    "similar stores",
    "view all",
    "all stores",
    "loading your offer",
)


def _normalize_text(value: str) -> str:
    normalized = re.sub(r"\s+", " ", value)
    return normalized.strip(" -*|>#")


def _extract_store_hint_from_html(soup: BeautifulSoup) -> str | None:
    heading = soup.find("h1")
    if heading is None:
        return None
    text = _normalize_text(heading.get_text(" ", strip=True))
    match = re.match(r"^(.*?)\s+Coupons?\s*&\s*Promo Codes?$", text, re.IGNORECASE)
    if not match:
        return None
    store = match.group(1).strip()
    return store or None


def _extract_offer_type(offer_link: Tag) -> str | None:
    x_data = str(offer_link.get("x-data", ""))
    match = re.search(r"'offerType':\s*'([^']+)'", x_data)
    raw_offer_type = match.group(1) if match else None

    badges = [badge.lower() for badge in _extract_offer_badges(offer_link)]
    cta_text = _normalize_text(offer_link.get_text(" ", strip=True)).lower()
    title_node = offer_link.find("h3")
    offer_text = _normalize_text(title_node.get_text(" ", strip=True)) if title_node else ""
    offer_lower = offer_text.lower()

    if "free shipping" in offer_lower:
        return "SHIPPING"
    if BOGO_PATTERN.search(offer_lower):
        return "BOGO"
    if any("online cash back" in badge for badge in badges):
        return "REWARD"
    if any(badge == "code" for badge in badges) or "show code" in cta_text:
        return "COUPON"
    if "get deal" in cta_text:
        return "SALE"
    if raw_offer_type:
        return raw_offer_type
    return None


def _extract_offer_badges(offer_link: Tag) -> list[str]:
    badges: list[str] = []
    for span in offer_link.find_all("span"):
        text = _normalize_text(span.get_text(" ", strip=True))
        if text:
            badges.append(text)
    return badges


def _extract_offer_metadata(offer_link: Tag) -> list[str]:
    values: list[str] = []
    for div in offer_link.find_all("div"):
        text = _normalize_text(div.get_text(" ", strip=True))
        if text:
            values.append(text)
    return values


def _clean_offer_text(value: str) -> str:
    cleaned = _normalize_text(value)
    cleaned = re.sub(r"\b(show code|get deal|get reward|see details)\b", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\b\d+\s+interested users?\b", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\badded by\s+[A-Za-z0-9._-]+\b", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\bverified\b", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\bexclusive\b", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned.strip(" |-")


def _extract_expiry(texts: list[str]) -> tuple[str | None, str | None]:
    for text in texts:
        match = EXPIRY_DATE_PATTERN.search(text)
        if match:
            return match.group(1), "date"
    for text in texts:
        match = EXPIRY_RELATIVE_PATTERN.search(text)
        if match:
            return match.group(1), "relative"
    return None, None


def _extract_min_spend(value: str) -> str | None:
    amount_off_match = AMOUNT_OFF_MIN_SPEND_PATTERN.search(value)
    if amount_off_match:
        return f"${amount_off_match.group(1)}"
    match = MIN_SPEND_PATTERN.search(value)
    if not match:
        return None
    return match.group(1)


def _extract_discount_percent(value: str) -> float | None:
    match = PERCENT_OFF_PATTERN.search(value)
    if not match:
        return None
    return float(match.group(1))


def _extract_discount_amount(value: str) -> str | None:
    up_to_match = UP_TO_AMOUNT_OFF_PATTERN.search(value)
    if up_to_match:
        return None

    match = AMOUNT_OFF_PATTERN.search(value)
    if not match:
        return None
    return match.group(1)


def _extract_max_discount_amount(value: str) -> str | None:
    match = UP_TO_AMOUNT_OFF_PATTERN.search(value)
    if not match:
        return None
    return match.group(1)


def _canonical_offer_key(candidate: DealCandidate) -> str:
    offer = (candidate.offer or candidate.normalized_line).lower()
    offer = re.sub(r"^(flash sale!|labor day savings!|today only|limited time offer)\s*", "", offer)
    offer = re.sub(r"\s+", " ", offer).strip()
    if candidate.discount_percent is not None:
        offer = re.sub(r"\b\d+(?:\.\d+)?%\s+off\b", f"{candidate.discount_percent:g}% off", offer)
    if candidate.discount_amount:
        offer = re.sub(r"[$]\d+(?:\.\d{1,2})?\s+off\b", f"{candidate.discount_amount.lower()} off", offer)
    return offer


def _extract_cashback_percent(value: str) -> float | None:
    match = CASHBACK_PATTERN.search(value)
    if not match:
        return None
    return float(match.group(1))


def _is_noise_offer(value: str) -> bool:
    lowered = value.lower()
    if len(lowered) < 6:
        return True
    if any(lowered.startswith(prefix) for prefix in QUESTION_PREFIXES):
        return True
    if any(phrase in lowered for phrase in NOISE_PHRASES):
        return True
    return False


def _score_candidate(candidate: DealCandidate) -> float:
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


def _dedupe_candidates(candidates: list[DealCandidate]) -> list[DealCandidate]:
    deduped: list[DealCandidate] = []
    seen: set[str] = set()
    for candidate in candidates:
        key = _canonical_offer_key(candidate)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(candidate)
    return deduped


def _extract_html_candidates(html: str) -> list[DealCandidate]:
    if not html.strip():
        return []

    soup = BeautifulSoup(html, "lxml")
    store_hint = _extract_store_hint_from_html(soup)
    offer_links = soup.select('a[data-component-class="offer_strip"]')
    candidates: list[DealCandidate] = []

    for offer_link in offer_links:
        if not isinstance(offer_link, Tag):
            continue

        offer_type = _extract_offer_type(offer_link)
        title_node = offer_link.find("h3")
        if title_node is None:
            continue

        offer_text = _clean_offer_text(title_node.get_text(" ", strip=True))
        if not offer_text or _is_noise_offer(offer_text):
            continue

        badges = _extract_offer_badges(offer_link)
        metadata = _extract_offer_metadata(offer_link)
        combined_metadata = badges + metadata

        cashback_percent = None
        if offer_type == "REWARD":
            cashback_percent = _extract_cashback_percent(" ".join(combined_metadata + [offer_text]))

        max_discount_amount = _extract_max_discount_amount(offer_text)
        discount_amount = _extract_discount_amount(offer_text)
        discount_percent = _extract_discount_percent(offer_text)
        discount_type = "upto" if max_discount_amount else None
        min_spend = _extract_min_spend(offer_text)
        expiry, expiry_type = _extract_expiry(combined_metadata)

        candidate = DealCandidate(
            source_line=str(offer_link),
            normalized_line=offer_text,
            store=store_hint,
            offer=offer_text,
            offer_type=offer_type,
            cashback_percent=cashback_percent,
            max_discount_amount=max_discount_amount,
            discount_amount=discount_amount,
            discount_percent=discount_percent,
            discount_type=discount_type,
            expiry=expiry,
            expiry_type=expiry_type,
            min_spend=min_spend,
        )
        candidate.confidence = _score_candidate(candidate)
        if candidate.confidence >= 0.4:
            candidates.append(candidate)

    candidates.sort(key=lambda item: item.confidence, reverse=True)
    return _dedupe_candidates(candidates)


def extract_deal_candidates(text: str, html: str | None = None) -> ExtractionReport:
    candidates = _extract_html_candidates(html or "")
    if not candidates:
        return ExtractionReport(candidates=[], overall_confidence=0.0)

    top_candidates = candidates[:5]
    overall_confidence = sum(item.confidence for item in top_candidates) / len(top_candidates)
    return ExtractionReport(
        candidates=candidates,
        overall_confidence=round(overall_confidence, 2),
    )

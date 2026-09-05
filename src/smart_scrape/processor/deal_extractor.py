"""RetailMeNot-specific deal extractor.

Parses the ``a[data-component-class="offer_strip"]`` DOM structure that
RetailMeNot uses on its merchant coupon pages.
"""

from __future__ import annotations

import logging
import re

from bs4 import BeautifulSoup
from bs4.element import Tag

from smart_scrape.processor.base_extractor import BaseDealExtractor
from smart_scrape.processor.models import DealCandidate, ExtractionReport
from smart_scrape.processor.ranking import (
    CASHBACK_PATTERN,
    PERCENT_OFF_PATTERN,
    AMOUNT_OFF_PATTERN,
    UP_TO_AMOUNT_OFF_PATTERN,
    BOGO_PATTERN,
    score_candidate,
    deduplicate_candidates,
)

logger = logging.getLogger(__name__)

# ------------------------------------------------------------------
# Regex patterns specific to parsing offer metadata
# ------------------------------------------------------------------

WHITESPACE_PATTERN = re.compile(r"\s+")
EXPIRY_DATE_PATTERN = re.compile(
    r"\b([A-Za-z]{3,9}\s+\d{1,2},?\s+\d{4})\b", re.IGNORECASE,
)
EXPIRY_RELATIVE_PATTERN = re.compile(
    r"\b(expiring soon|limited time)\b", re.IGNORECASE,
)
MIN_SPEND_PATTERN = re.compile(
    r"\b(?:with|on|over|orders?\s+over|purchase|spend)\s+([$]\d+(?:\.\d{1,2})?\+?)",
    re.IGNORECASE,
)
AMOUNT_OFF_MIN_SPEND_PATTERN = re.compile(
    r"[$]\d+(?:\.\d{1,2})?\s+off\s+[$](\d+(?:\.\d{1,2})?\+?)",
    re.IGNORECASE,
)

QUESTION_PREFIXES = (
    "how ", "what ", "are ", "does ", "do ", "can ", "is ", "why ", "when ",
)
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


# ------------------------------------------------------------------
# Internal helpers
# ------------------------------------------------------------------

def _normalize_text(value: str) -> str:
    normalized = WHITESPACE_PATTERN.sub(" ", value)
    return normalized.strip(" -*|>#")


def _extract_store_hint_from_html(soup: BeautifulSoup) -> str | None:
    heading = soup.find("h1")
    if heading is None:
        return None
    text = _normalize_text(heading.get_text(" ", strip=True))
    match = re.match(
        r"^(.*?)\s+Coupons?\s*&\s*Promo Codes?$", text, re.IGNORECASE,
    )
    if not match:
        return None
    store = match.group(1).strip()
    return store or None


def _extract_offer_type(
    offer_link: Tag,
    *,
    offer_text: str | None = None,
    badges: list[str] | None = None,
) -> str | None:
    x_data = str(offer_link.get("x-data", ""))
    match = re.search(r"'offerType':\s*'([^']+)'", x_data)
    raw_offer_type = match.group(1) if match else None

    if badges is None:
        badges = _extract_offer_badges(offer_link)
    badges = [badge.lower() for badge in badges]
    cta_text = _normalize_text(offer_link.get_text(" ", strip=True)).lower()
    offer_lower = (offer_text or "").lower()

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
    return [
        text
        for span in offer_link.find_all("span")
        if (text := _normalize_text(span.get_text(" ", strip=True)))
    ]


def _extract_offer_metadata(offer_link: Tag) -> list[str]:
    return [
        text
        for div in offer_link.find_all("div")
        if (text := _normalize_text(div.get_text(" ", strip=True)))
    ]


def _clean_offer_text(value: str) -> str:
    cleaned = _normalize_text(value)
    cleaned = re.sub(
        r"\b(show code|get deal|get reward|see details)\b",
        "", cleaned, flags=re.IGNORECASE,
    )
    cleaned = re.sub(
        r"\b\d+\s+interested users?\b", "", cleaned, flags=re.IGNORECASE,
    )
    cleaned = re.sub(
        r"\badded by\s+[A-Za-z0-9._-]+\b", "", cleaned, flags=re.IGNORECASE,
    )
    cleaned = re.sub(r"\bverified\b", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\bexclusive\b", "", cleaned, flags=re.IGNORECASE)
    cleaned = WHITESPACE_PATTERN.sub(" ", cleaned)
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
    if UP_TO_AMOUNT_OFF_PATTERN.search(value):
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


def _extract_cashback_percent(value: str) -> float | None:
    match = CASHBACK_PATTERN.search(value)
    if not match:
        return None
    return float(match.group(1))


def _is_noise_offer(value: str) -> bool:
    lowered = value.lower()
    if len(lowered) < 6:
        return True
    if lowered.startswith(QUESTION_PREFIXES):
        return True
    if any(phrase in lowered for phrase in NOISE_PHRASES):
        return True
    return False


# ------------------------------------------------------------------
# RetailMeNot extractor class
# ------------------------------------------------------------------

class RetailMeNotExtractor(BaseDealExtractor):
    """DOM-aware extractor for retailmenot.com store pages."""

    __slots__ = ()

    name = "retailmenot"
    supported_domains = ("retailmenot.com", "www.retailmenot.com")

    def extract(
        self, html: str, text: str, url: str
    ) -> list[DealCandidate]:
        if not html or html.isspace():
            return []

        soup = BeautifulSoup(html, "lxml")
        store_hint = _extract_store_hint_from_html(soup)
        store = store_hint or "UNKNOWN_STORE"
        offer_links = soup.select('a[data-component-class="offer_strip"]')
        candidates: list[DealCandidate] = []

        logger.debug(
            "retailmenot_extract_start",
            extra={"url": url, "offer_links_found": len(offer_links)},
        )

        for offer_link in offer_links:
            if not isinstance(offer_link, Tag):
                continue

            title_node = offer_link.find("h3")
            if title_node is None:
                continue

            title_text = _normalize_text(title_node.get_text(" ", strip=True))
            badges = _extract_offer_badges(offer_link)
            offer_type = _extract_offer_type(
                offer_link, offer_text=title_text, badges=badges,
            )
            offer_text = _clean_offer_text(title_node.get_text(" ", strip=True))
            if not offer_text or _is_noise_offer(offer_text):
                continue

            metadata = _extract_offer_metadata(offer_link)
            combined_metadata = badges + metadata

            cashback_percent = None
            if offer_type == "REWARD":
                cashback_percent = _extract_cashback_percent(
                    " ".join(combined_metadata + [offer_text])
                )

            max_discount_amount = _extract_max_discount_amount(offer_text)
            discount_amount = _extract_discount_amount(offer_text)
            discount_percent = _extract_discount_percent(offer_text)
            discount_type = "upto" if max_discount_amount else None
            min_spend = _extract_min_spend(offer_text)
            expiry, expiry_type = _extract_expiry(combined_metadata)

            candidate = DealCandidate(
                store=store,
                offer=offer_text,
                source=self.name,
                raw_html=str(offer_link),
                normalized_line=offer_text,
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
            candidate.confidence = score_candidate(candidate)
            if candidate.confidence >= 0.4:
                candidates.append(candidate)

        candidates.sort(key=lambda item: item.confidence, reverse=True)
        candidates = deduplicate_candidates(candidates)

        logger.debug(
            "retailmenot_extract_done",
            extra={
                "url": url,
                "candidates_found": len(candidates),
                "store": store_hint,
            },
        )
        return candidates


# ------------------------------------------------------------------
# Legacy wrapper — keeps old call sites working
# ------------------------------------------------------------------

def extract_deal_candidates(
    text: str, html: str | None = None
) -> ExtractionReport:
    """Backward-compatible entry point used by the pipeline."""
    extractor = RetailMeNotExtractor()
    candidates = extractor.extract(html=html or "", text=text, url="")

    if not candidates:
        return ExtractionReport(candidates=[], overall_confidence=0.0)

    top_candidates = candidates[:5]
    overall_confidence = sum(
        item.confidence for item in top_candidates
    ) / len(top_candidates)
    return ExtractionReport(
        candidates=candidates,
        overall_confidence=round(overall_confidence, 2),
    )

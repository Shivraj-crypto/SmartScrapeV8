"""Universal deal extractor.

Combines two strategies:
1. DOM-based extraction from common coupon/deal containers.
2. Text-based extraction with multi-language regex signals.
"""

from __future__ import annotations

import logging
import re
from html import unescape
from urllib.parse import urlparse

from bs4 import BeautifulSoup
from bs4.element import Tag

from smart_scrape.processor.base_extractor import BaseDealExtractor
from smart_scrape.processor.models import DealCandidate
from smart_scrape.processor.ranking import (
    AMOUNT_OFF_PATTERN,
    BOGO_PATTERN,
    CASHBACK_PATTERN,
    PERCENT_OFF_PATTERN,
    UP_TO_AMOUNT_OFF_PATTERN,
    score_candidate,
)

logger = logging.getLogger(__name__)

# ------------------------------------------------------------------
# Multi-language patterns
# ------------------------------------------------------------------

# English
_EN_FREE_SHIPPING = re.compile(r"\bfree shipping\b", re.IGNORECASE)
_EN_COUPON_CODE = re.compile(
    r"\b(?:code|coupon|promo(?:\s*code)?|use(?:\s+code)?|apply(?:\s+code)?)[:\s]+([A-Z0-9][A-Z0-9-]{2,19})\b",
    re.IGNORECASE,
)
_EN_EXTRA_OFF = re.compile(
    r"\b(?:extra|additional)\s+(\d+(?:\.\d+)?)\s*%\s*off\b", re.IGNORECASE,
)
_EN_UP_TO_PCT_OFF = re.compile(
    r"\bup\s+to\s+(\d+(?:\.\d+)?)\s*%\s*off\b", re.IGNORECASE,
)
_EN_SAVE_AMOUNT = re.compile(
    r"\bsave\s+([$€£¥₹₩]\s?\d+(?:[.,]\d{1,2})?)\b", re.IGNORECASE,
)
_EN_MIN_SPEND = re.compile(
    r"\b(?:with|on|over|orders?\s+over|purchase(?:s)?\s+over|spend|min(?:imum)?\s+purchase(?:\s+of)?|when you spend)\s+([$€£¥₹₩]?\s?\d+(?:[.,]\d{1,2})?\+?)",
    re.IGNORECASE,
)
_EN_AMOUNT_OFF_MIN_SPEND = re.compile(
    r"[$€£¥₹₩]\s?\d+(?:[.,]\d{1,2})?\s+off\s+(?:orders?\s+over|on|with|when you spend)\s+([$€£¥₹₩]?\s?\d+(?:[.,]\d{1,2})?\+?)",
    re.IGNORECASE,
)
_EN_SHIPPING_MIN_SPEND = re.compile(
    r"\bfree shipping on orders?\s+([$€£¥₹₩]?\s?\d+(?:[.,]\d{1,2})?\+?)",
    re.IGNORECASE,
)
_EN_GENERIC_DEAL_WORD = re.compile(
    r"\b(?:coupon|coupons|promo|promo code|discount|deal|sale|offer|offers|sitewide|storewide|clearance)\b",
    re.IGNORECASE,
)

# Chinese
_ZH_DISCOUNT_ZHEKOU = re.compile(r"(\d+(?:\.\d+)?)\s*折")
_ZH_EXTRA_DISCOUNT = re.compile(r"额外\s*(\d+(?:\.\d+)?)\s*折")
_ZH_LOW_AS = re.compile(r"低至\s*(\d+(?:\.\d+)?)\s*折")
_ZH_CASHBACK = re.compile(r"(\d+(?:\.\d+)?)\s*%?\s*返利")
_ZH_COUPON_CODE = re.compile(
    r"(?:优惠码|折扣码|优惠券)[：:\s]*([A-Z0-9][A-Z0-9-]{2,19})",
    re.IGNORECASE,
)
_ZH_FREE_SHIPPING = re.compile(r"(?:免邮|包邮|免运费)")
_ZH_FULL_MINUS = re.compile(
    r"满\s*([$€£¥￥]?\d+(?:\.\d{1,2})?)\s*减\s*([$€£¥￥]?\d+(?:\.\d{1,2})?)"
)
_ZH_DEAL_SIGNAL = re.compile(r"(?:优惠|折扣|特价|促销|大促|清仓|打折|秒杀|限时|闪购)")
_ZH_BUY_GET = re.compile(r"买\s*\d+\s*(?:送|赠)\s*\d+")

# Korean
_KO_DISCOUNT = re.compile(r"(\d+)\s*%\s*(?:할인|세일|OFF)", re.IGNORECASE)
_KO_COUPON = re.compile(
    r"(?:쿠폰|할인코드|프로모)[：:\s]*([A-Z0-9][A-Z0-9-]{2,19})",
    re.IGNORECASE,
)
_KO_FREE_SHIPPING = re.compile(r"무료\s*배송")

# Japanese
_JA_OFF = re.compile(r"(\d+)\s*%\s*(?:オフ|OFF|引き)", re.IGNORECASE)
_JA_COUPON = re.compile(
    r"(?:クーポン|割引コード)[：:\s]*([A-Z0-9][A-Z0-9-]{2,19})",
    re.IGNORECASE,
)
_JA_FREE_SHIPPING = re.compile(r"送料無料")

# Spanish / Portuguese
_ES_DISCOUNT = re.compile(
    r"(\d+)\s*%\s*(?:descuento|dto|de descuento|off)\b", re.IGNORECASE,
)
_ES_COUPON = re.compile(
    r"\b(?:c[oó]digo|cup[oó]n|cupom)[:\s]+([A-Z0-9][A-Z0-9-]{2,19})\b",
    re.IGNORECASE,
)
_ES_FREE_SHIPPING = re.compile(
    r"\benv[ií]o\s*(?:gratis|gratuito)\b", re.IGNORECASE,
)

EXPIRY_DATE_PATTERN = re.compile(
    r"\b([A-Za-z]{3,9}\s+\d{1,2},?\s+\d{4}|\d{4}[-/]\d{1,2}[-/]\d{1,2})\b",
    re.IGNORECASE,
)
EXPIRY_RELATIVE_PATTERN = re.compile(
    r"\b(expiring soon|limited time|today only|ends? today|ends? soon)\b",
    re.IGNORECASE,
)

_INLINE_SPLIT_PATTERN = re.compile(r"\s*(?:\||•|·)\s*")

_DEAL_HEADINGS = {
    "coupon",
    "coupons",
    "discount",
    "discounts",
    "deal",
    "deals",
    "offer",
    "offers",
    "promo",
    "promo codes",
    "sale",
    "sales",
}
_COUPON_STOPWORDS = {
    "APPLY",
    "CHECKOUT",
    "CLICK",
    "CODE",
    "COUPON",
    "DEAL",
    "DETAILS",
    "DISCOUNT",
    "HERE",
    "NOW",
    "OFFER",
    "ONLINE",
    "ORDER",
    "ORDERS",
    "PROMO",
    "PURCHASE",
    "SALE",
    "SHOP",
    "SITEWIDE",
    "STORE",
    "STOREWIDE",
    "TODAY",
    "VALID",
}
_QUESTION_PREFIXES = (
    "how ",
    "what ",
    "are ",
    "does ",
    "do ",
    "can ",
    "is ",
    "why ",
    "when ",
    "where ",
    "which ",
)
_NOISE_PHRASES = (
    "accept cookies",
    "added by",
    "all stores",
    "customer care",
    "customer support",
    "contact support",
    "download app",
    "email support",
    "faq",
    "featured articles",
    "frequently asked questions",
    "help center",
    "latest arrivals",
    "learn more",
    "loading your offer",
    "log in",
    "new arrivals",
    "newsletter",
    "payment options",
    "popular stores",
    "privacy policy",
    "return and refund policy",
    "return policy",
    "see details",
    "share this",
    "shipping and delivery policy",
    "sign in",
    "similar stores",
    "store info",
    "submit a coupon",
    "support@",
    "terms and conditions",
    "track your order",
    "updated by",
    "view all",
    "why trust us",
)

# ------------------------------------------------------------------
# DOM selectors
# ------------------------------------------------------------------

_DEAL_SELECTORS = [
    '[class*="coupon"]',
    '[class*="deal"]',
    '[class*="offer"]',
    '[class*="promo"]',
    '[class*="discount"]',
    '[class*="voucher"]',
    '[class*="code-"]',
    '[class*="savings"]',
    '[class*="reward"]',
    '[data-coupon]',
    '[data-code]',
    '[data-offer]',
    '[data-deal]',
    '[data-promo]',
    '[data-discount]',
]

_MIN_LINE_LEN = 4
_MAX_LINE_LEN = 400
_OFFER_TYPE_PRIORITY = {
    None: 0,
    "SALE": 1,
    "SHIPPING": 2,
    "REWARD": 3,
    "BOGO": 4,
    "COUPON": 5,
}


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

def _normalize_text(value: str) -> str:
    normalized = unescape(value or "")
    normalized = normalized.replace("\xa0", " ").replace("\u200b", "")
    normalized = re.sub(r"\s+", " ", normalized)
    return normalized.strip(" -*|>#:\u2022")


def _clean_candidate_text(value: str) -> str:
    cleaned = _normalize_text(value)
    cleaned = re.sub(
        r"\b(show code|get deal|get reward|see details|copy code|shop now|activate deal)\b",
        "",
        cleaned,
        flags=re.IGNORECASE,
    )
    cleaned = re.sub(r"\bverified\b", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\b\d+\s+interested users?\b", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned.strip(" |-")


def _normalize_code(value: str) -> str:
    return value.strip(" .,:;()[]{}").upper()


def _set_offer_type(current: str | None, new: str | None) -> str | None:
    if new is None:
        return current
    if _OFFER_TYPE_PRIORITY[new] >= _OFFER_TYPE_PRIORITY[current]:
        return new
    return current


def _valid_discount_percent(value: float) -> bool:
    return 0 < value <= 100


def _looks_like_coupon_code(value: str) -> bool:
    code = _normalize_code(value)
    if len(code) < 3 or len(code) > 20:
        return False
    if not re.fullmatch(r"[A-Z0-9-]+", code):
        return False
    if code.isdigit():
        return False
    if code in _COUPON_STOPWORDS:
        return False
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", code):
        return False
    if code.isalpha() and len(code) < 5:
        return False
    return True


def _extract_expiry(value: str) -> tuple[str | None, str | None]:
    match = EXPIRY_DATE_PATTERN.search(value)
    if match:
        return match.group(1), "date"
    match = EXPIRY_RELATIVE_PATTERN.search(value)
    if match:
        return match.group(1), "relative"
    return None, None


def _extract_min_spend(value: str) -> str | None:
    match = _EN_AMOUNT_OFF_MIN_SPEND.search(value)
    if match:
        return match.group(1).strip()
    match = _EN_SHIPPING_MIN_SPEND.search(value)
    if match:
        return match.group(1).strip()
    match = _EN_MIN_SPEND.search(value)
    if match:
        return match.group(1).strip()
    zh_match = _ZH_FULL_MINUS.search(value)
    if zh_match:
        return zh_match.group(1).strip()
    return None


def _is_noise_line(value: str) -> bool:
    lowered = value.lower()
    if len(lowered) < _MIN_LINE_LEN:
        return True
    if any(lowered.startswith(prefix) for prefix in _QUESTION_PREFIXES):
        return True
    if any(phrase in lowered for phrase in _NOISE_PHRASES):
        return True
    if "@" in lowered and not _EN_COUPON_CODE.search(value):
        return True
    if lowered in _DEAL_HEADINGS:
        return True
    if re.fullmatch(r"(?:home|menu|search|back|next|previous|close)", lowered):
        return True
    return False


def _split_candidate_parts(value: str) -> list[str]:
    if not value:
        return []
    parts = [part for part in _INLINE_SPLIT_PATTERN.split(value) if part]
    if len(parts) <= 1:
        return [value]
    cleaned_parts = [_clean_candidate_text(part) for part in parts]
    return [part for part in cleaned_parts if part]


def _guess_store_from_url(url: str) -> str:
    """Best-effort store name from URL path."""
    parsed = urlparse(url if "://" in url else f"https://{url}")
    path = parsed.path.strip("/")
    for prefix in ("store/", "view/", "coupons/", "brand/", "shop/"):
        if prefix in path:
            slug = path.split(prefix, 1)[1].split("/")[0].split(".")[0]
            if slug:
                return slug.replace("-", " ").replace("_", " ").title()
    domain = parsed.netloc.lower().replace("www.", "")
    return domain.split(".")[0].title() if domain else "UNKNOWN_STORE"


def _strip_store_suffix(value: str) -> str | None:
    for pattern in (
        r"^(.*?)\s+(?:Coupons?|Promo(?:\s*Codes?)?|Deals?|Discounts?|Offers?)\b",
        r"^(.*?)\s+(?:优惠|折扣|特价|促销)\b",
        r"^(.*?)\s*[（(]",
    ):
        match = re.match(pattern, value, re.IGNORECASE)
        if match and match.group(1).strip():
            return match.group(1).strip()
    return None


def _guess_store_from_html(soup: BeautifulSoup) -> str | None:
    """Try to extract store name from semantic page hints."""
    values: list[str] = []

    h1 = soup.find("h1")
    if h1:
        values.append(_normalize_text(h1.get_text(" ", strip=True)))

    if soup.title and soup.title.string:
        values.append(_normalize_text(soup.title.string))

    og_site = soup.find("meta", attrs={"property": "og:site_name"})
    if og_site and og_site.get("content"):
        values.append(_normalize_text(str(og_site.get("content"))))

    for value in values:
        stripped = _strip_store_suffix(value)
        if stripped:
            return stripped
        if value and value.lower() not in _DEAL_HEADINGS:
            return value[:80]
    return None


# ------------------------------------------------------------------
# Universal extractor
# ------------------------------------------------------------------

class GenericDealExtractor(BaseDealExtractor):
    """Universal extractor that works across sites and languages."""

    name = "generic"
    supported_domains: list[str] = []

    def extract(
        self,
        html: str,
        text: str,
        url: str,
    ) -> list[DealCandidate]:
        candidates: list[DealCandidate] = []
        seen_offers: set[str] = set()

        store = "UNKNOWN_STORE"
        if html.strip():
            soup = BeautifulSoup(html, "lxml")
            store = _guess_store_from_html(soup) or _guess_store_from_url(url)
            for candidate in self._extract_from_dom(soup, store, url):
                key = self._dedup_key(candidate)
                if key in seen_offers:
                    continue
                seen_offers.add(key)
                candidates.append(candidate)
        else:
            store = _guess_store_from_url(url)

        if text.strip():
            for candidate in self._extract_from_text(text, store, url):
                key = self._dedup_key(candidate)
                if key in seen_offers:
                    continue
                seen_offers.add(key)
                candidates.append(candidate)

        candidates.sort(key=lambda item: item.confidence, reverse=True)

        logger.debug(
            "generic_extract_done",
            extra={
                "url": url,
                "store": store,
                "candidates_found": len(candidates),
            },
        )
        return candidates

    # ------------------------------------------------------------------
    # Strategy 1: DOM-based extraction
    # ------------------------------------------------------------------

    def _extract_from_dom(
        self,
        soup: BeautifulSoup,
        store: str,
        url: str,
    ) -> list[DealCandidate]:
        """Scan HTML for elements that look like coupon/deal containers."""
        candidates: list[DealCandidate] = []
        seen_text: set[str] = set()

        for selector in _DEAL_SELECTORS:
            try:
                elements = soup.select(selector)
            except Exception:
                continue

            for element in elements:
                if not isinstance(element, Tag):
                    continue

                texts = [element.get_text(" ", strip=True), *list(element.stripped_strings)]
                for raw_text in texts:
                    for part in _split_candidate_parts(_clean_candidate_text(raw_text)):
                        if not part or len(part) < _MIN_LINE_LEN or len(part) > _MAX_LINE_LEN:
                            continue
                        normalized = re.sub(r"\s+", " ", part).lower()
                        if normalized in seen_text:
                            continue
                        seen_text.add(normalized)

                        parsed = self._parse_text(part, store)
                        if parsed is None:
                            continue
                        parsed.raw_html = str(element)[:500]
                        candidates.append(parsed)

        return candidates

    # ------------------------------------------------------------------
    # Strategy 2: Text-based extraction
    # ------------------------------------------------------------------

    def _extract_from_text(
        self,
        text: str,
        store: str,
        url: str,
    ) -> list[DealCandidate]:
        """Scan cleaned text line-by-line for deal signals."""
        candidates: list[DealCandidate] = []
        seen_text: set[str] = set()

        for raw_line in text.splitlines():
            cleaned = _clean_candidate_text(raw_line)
            for part in _split_candidate_parts(cleaned):
                if len(part) < _MIN_LINE_LEN or len(part) > _MAX_LINE_LEN:
                    continue
                normalized = part.lower()
                if normalized in seen_text:
                    continue
                seen_text.add(normalized)

                parsed = self._parse_text(part, store)
                if parsed is not None:
                    candidates.append(parsed)

        return candidates

    # ------------------------------------------------------------------
    # Core parsing
    # ------------------------------------------------------------------

    def _parse_text(self, line: str, store: str) -> DealCandidate | None:
        """Parse a single line for actionable deal signals."""
        line = _clean_candidate_text(line)
        if not line or _is_noise_line(line):
            return None

        offer_type: str | None = None
        discount_percent: float | None = None
        discount_amount: str | None = None
        max_discount_amount: str | None = None
        cashback_percent: float | None = None
        coupon_code: str | None = None
        min_spend: str | None = None
        expiry: str | None = None
        expiry_type: str | None = None
        discount_type: str | None = None
        strong_signals = 0
        weak_signals = 0

        pct = PERCENT_OFF_PATTERN.search(line)
        if pct:
            value = float(pct.group(1))
            if _valid_discount_percent(value):
                discount_percent = value
                offer_type = _set_offer_type(offer_type, "SALE")
                strong_signals += 1

        amt = AMOUNT_OFF_PATTERN.search(line)
        if amt and not UP_TO_AMOUNT_OFF_PATTERN.search(line):
            discount_amount = amt.group(1)
            offer_type = _set_offer_type(offer_type, "SALE")
            strong_signals += 1

        upto = UP_TO_AMOUNT_OFF_PATTERN.search(line)
        if upto:
            max_discount_amount = upto.group(1)
            discount_type = "upto"
            offer_type = _set_offer_type(offer_type, "SALE")
            strong_signals += 1

        up_pct = _EN_UP_TO_PCT_OFF.search(line)
        if up_pct and discount_percent is None:
            value = float(up_pct.group(1))
            if _valid_discount_percent(value):
                discount_percent = value
                discount_type = "upto"
                offer_type = _set_offer_type(offer_type, "SALE")
                strong_signals += 1

        extra = _EN_EXTRA_OFF.search(line)
        if extra and discount_percent is None:
            value = float(extra.group(1))
            if _valid_discount_percent(value):
                discount_percent = value
                offer_type = _set_offer_type(offer_type, "SALE")
                strong_signals += 1

        save = _EN_SAVE_AMOUNT.search(line)
        if save and discount_amount is None:
            discount_amount = save.group(1)
            offer_type = _set_offer_type(offer_type, "SALE")
            strong_signals += 1

        cashback = CASHBACK_PATTERN.search(line)
        if cashback:
            cashback_percent = float(cashback.group(1))
            offer_type = _set_offer_type(offer_type, "REWARD")
            strong_signals += 1

        if _EN_FREE_SHIPPING.search(line):
            offer_type = _set_offer_type(offer_type, "SHIPPING")
            strong_signals += 1

        if BOGO_PATTERN.search(line):
            offer_type = _set_offer_type(offer_type, "BOGO")
            strong_signals += 1

        code = _EN_COUPON_CODE.search(line)
        if code:
            parsed_code = _normalize_code(code.group(1))
            if _looks_like_coupon_code(parsed_code):
                coupon_code = parsed_code
                offer_type = _set_offer_type(offer_type, "COUPON")
                strong_signals += 1

        zh_extra = _ZH_EXTRA_DISCOUNT.search(line)
        if zh_extra:
            zhe_val = float(zh_extra.group(1))
            discount_percent = round((10 - zhe_val) * 10, 1)
            offer_type = _set_offer_type(offer_type, "SALE")
            strong_signals += 1

        zh_low = _ZH_LOW_AS.search(line)
        if zh_low and discount_percent is None:
            zhe_val = float(zh_low.group(1))
            discount_percent = round((10 - zhe_val) * 10, 1)
            offer_type = _set_offer_type(offer_type, "SALE")
            strong_signals += 1

        zh_zhe = _ZH_DISCOUNT_ZHEKOU.search(line)
        if zh_zhe and discount_percent is None and not zh_extra and not zh_low:
            zhe_val = float(zh_zhe.group(1))
            if 0 < zhe_val < 10:
                discount_percent = round((10 - zhe_val) * 10, 1)
                offer_type = _set_offer_type(offer_type, "SALE")
                strong_signals += 1

        zh_cashback = _ZH_CASHBACK.search(line)
        if zh_cashback:
            cashback_percent = float(zh_cashback.group(1))
            offer_type = _set_offer_type(offer_type, "REWARD")
            strong_signals += 1

        zh_code = _ZH_COUPON_CODE.search(line)
        if zh_code:
            parsed_code = _normalize_code(zh_code.group(1))
            if _looks_like_coupon_code(parsed_code):
                coupon_code = parsed_code
                offer_type = _set_offer_type(offer_type, "COUPON")
                strong_signals += 1

        if _ZH_FREE_SHIPPING.search(line):
            offer_type = _set_offer_type(offer_type, "SHIPPING")
            strong_signals += 1

        zh_full_minus = _ZH_FULL_MINUS.search(line)
        if zh_full_minus:
            min_spend = zh_full_minus.group(1)
            discount_amount = zh_full_minus.group(2)
            offer_type = _set_offer_type(offer_type, "SALE")
            strong_signals += 1

        if _ZH_BUY_GET.search(line):
            offer_type = _set_offer_type(offer_type, "BOGO")
            strong_signals += 1

        if _ZH_DEAL_SIGNAL.search(line):
            weak_signals += 1

        ko_discount = _KO_DISCOUNT.search(line)
        if ko_discount and discount_percent is None:
            value = float(ko_discount.group(1))
            if _valid_discount_percent(value):
                discount_percent = value
                offer_type = _set_offer_type(offer_type, "SALE")
                strong_signals += 1

        ko_code = _KO_COUPON.search(line)
        if ko_code and coupon_code is None:
            parsed_code = _normalize_code(ko_code.group(1))
            if _looks_like_coupon_code(parsed_code):
                coupon_code = parsed_code
                offer_type = _set_offer_type(offer_type, "COUPON")
                strong_signals += 1

        if _KO_FREE_SHIPPING.search(line):
            offer_type = _set_offer_type(offer_type, "SHIPPING")
            strong_signals += 1

        ja_discount = _JA_OFF.search(line)
        if ja_discount and discount_percent is None:
            value = float(ja_discount.group(1))
            if _valid_discount_percent(value):
                discount_percent = value
                offer_type = _set_offer_type(offer_type, "SALE")
                strong_signals += 1

        ja_code = _JA_COUPON.search(line)
        if ja_code and coupon_code is None:
            parsed_code = _normalize_code(ja_code.group(1))
            if _looks_like_coupon_code(parsed_code):
                coupon_code = parsed_code
                offer_type = _set_offer_type(offer_type, "COUPON")
                strong_signals += 1

        if _JA_FREE_SHIPPING.search(line):
            offer_type = _set_offer_type(offer_type, "SHIPPING")
            strong_signals += 1

        es_discount = _ES_DISCOUNT.search(line)
        if es_discount and discount_percent is None:
            value = float(es_discount.group(1))
            if _valid_discount_percent(value):
                discount_percent = value
                offer_type = _set_offer_type(offer_type, "SALE")
                strong_signals += 1

        es_code = _ES_COUPON.search(line)
        if es_code and coupon_code is None:
            parsed_code = _normalize_code(es_code.group(1))
            if _looks_like_coupon_code(parsed_code):
                coupon_code = parsed_code
                offer_type = _set_offer_type(offer_type, "COUPON")
                strong_signals += 1

        if _ES_FREE_SHIPPING.search(line):
            offer_type = _set_offer_type(offer_type, "SHIPPING")
            strong_signals += 1

        if _EN_GENERIC_DEAL_WORD.search(line):
            weak_signals += 1

        if strong_signals == 0:
            return None

        if min_spend is None:
            min_spend = _extract_min_spend(line)
        expiry, expiry_type = _extract_expiry(line)

        candidate = DealCandidate(
            store=store,
            offer=line,
            source=self.name,
            normalized_line=line,
            offer_type=offer_type,
            coupon_code=coupon_code,
            discount_percent=discount_percent,
            discount_amount=discount_amount,
            max_discount_amount=max_discount_amount,
            cashback_percent=cashback_percent,
            min_spend=min_spend,
            discount_type=discount_type,
            expiry=expiry,
            expiry_type=expiry_type,
        )
        candidate.confidence = score_candidate(candidate)

        if strong_signals >= 2 or (strong_signals >= 1 and weak_signals >= 1):
            candidate.confidence = min(1.0, candidate.confidence + 0.08)
            candidate.reasons.append("multi_signal")

        return candidate if candidate.confidence >= 0.3 else None

    # ------------------------------------------------------------------

    @staticmethod
    def _dedup_key(candidate: DealCandidate) -> str:
        text = re.sub(
            r"\s+",
            " ",
            (candidate.offer or candidate.normalized_line).lower(),
        ).strip()
        return text

"""Universal deal extractor — works on any website, any language.

Combines two strategies:
1. **DOM-based**: scans HTML for common deal/coupon DOM patterns
   across sites (elements with coupon/deal/promo class names, structured
   listing items with discount info).
2. **Text-based**: multi-language regex matching (English, Chinese,
   Korean, Japanese, Spanish, etc.) on cleaned text.
"""

from __future__ import annotations

import logging
import re
from urllib.parse import urlparse

from bs4 import BeautifulSoup
from bs4.element import Tag

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

# ------------------------------------------------------------------
# Multi-language patterns
# ------------------------------------------------------------------

# English
_EN_FREE_SHIPPING = re.compile(r"\bfree shipping\b", re.IGNORECASE)
_EN_COUPON_CODE = re.compile(
    r"\b(?:code|coupon|promo(?:\s*code)?|use|apply)[:\s]+([A-Z0-9]{3,20})\b",
    re.IGNORECASE,
)
_EN_EXTRA_OFF = re.compile(
    r"\b(?:extra|additional)\s+(\d+(?:\.\d+)?)\s*%\s*off\b", re.IGNORECASE,
)
_EN_UP_TO_PCT_OFF = re.compile(
    r"\bup\s+to\s+(\d+(?:\.\d+)?)\s*%\s*off\b", re.IGNORECASE,
)
_EN_SAVE_AMOUNT = re.compile(
    r"\bsave\s+([$€£¥]\d+(?:\.\d{1,2})?)\b", re.IGNORECASE,
)
_EN_FROM_PRICE = re.compile(
    r"\b(?:from|starting\s+at|as\s+low\s+as)\s+([$€£¥]\d+(?:\.\d{1,2})?)\b",
    re.IGNORECASE,
)

# Chinese (55haitao, smzdm, dealmoon, etc.)
_ZH_DISCOUNT_ZHEKOU = re.compile(r"(\d+(?:\.\d+)?)\s*折")          # 9折 = 10% off
_ZH_EXTRA_DISCOUNT = re.compile(r"额外\s*(\d+(?:\.\d+)?)\s*折")     # 额外9折
_ZH_LOW_AS = re.compile(r"低至\s*(\d+(?:\.\d+)?)\s*折")             # 低至5折
_ZH_CASHBACK = re.compile(r"(\d+(?:\.\d+)?)\s*%?\s*返利")           # 5%返利
_ZH_COUPON_CODE = re.compile(r"(?:优惠码|折扣码|优惠券)[：:\s]*([A-Z0-9]{3,20})", re.IGNORECASE)
_ZH_FREE_SHIPPING = re.compile(r"(?:免邮|包邮|免运费)")
_ZH_FULL_MINUS = re.compile(r"满\s*([$€£¥￥]?\d+(?:\.\d{1,2})?)\s*减\s*([$€£¥￥]?\d+(?:\.\d{1,2})?)")  # 满200减50
_ZH_DEAL_SIGNAL = re.compile(r"(?:优惠|折扣|特价|促销|大促|清仓|打折|秒杀|限时|闪购)")
_ZH_BUY_GET = re.compile(r"买\s*\d+\s*(?:送|赠)\s*\d+")            # 买1送1

# Korean
_KO_DISCOUNT = re.compile(r"(\d+)\s*%\s*(?:할인|세일|OFF)", re.IGNORECASE)
_KO_COUPON = re.compile(r"(?:쿠폰|할인코드|프로모)[：:\s]*([A-Z0-9]{3,20})", re.IGNORECASE)
_KO_FREE_SHIPPING = re.compile(r"무료\s*배송")

# Japanese
_JA_OFF = re.compile(r"(\d+)\s*%\s*(?:オフ|OFF|引き)", re.IGNORECASE)
_JA_COUPON = re.compile(r"(?:クーポン|割引コード)[：:\s]*([A-Z0-9]{3,20})", re.IGNORECASE)
_JA_FREE_SHIPPING = re.compile(r"送料無料")

# Spanish / Portuguese
_ES_DISCOUNT = re.compile(r"(\d+)\s*%\s*(?:descuento|dto|de descuento|off)\b", re.IGNORECASE)
_ES_COUPON = re.compile(r"\b(?:código|cupón|cupom)[:\s]+([A-Z0-9]{3,20})\b", re.IGNORECASE)
_ES_FREE_SHIPPING = re.compile(r"\benv[ií]o\s*(?:gratis|gratuito)\b", re.IGNORECASE)

# Generic currency amounts
_CURRENCY_AMOUNT = re.compile(r"([$€£¥₹￥₩]\s?\d+(?:[.,]\d{1,2})?)")

# ------------------------------------------------------------------
# DOM selectors — common across deal sites
# ------------------------------------------------------------------

_DEAL_CLASS_KEYWORDS = (
    "coupon", "deal", "offer", "promo", "discount", "voucher",
    "code", "sale", "savings", "reward", "cashback",
    # Chinese
    "youhui", "coupon-item", "offer-item", "deal-item",
)

_DEAL_SELECTORS = [
    '[class*="coupon"]', '[class*="deal"]', '[class*="offer"]',
    '[class*="promo"]', '[class*="discount"]', '[class*="voucher"]',
    '[class*="code-"]', '[class*="savings"]', '[class*="reward"]',
    '[data-coupon]', '[data-code]', '[data-offer]', '[data-deal]',
    '[data-promo]', '[data-discount]',
]

_MIN_LINE_LEN = 4    # Lowered for Chinese (shorter text)
_MAX_LINE_LEN = 400


# ------------------------------------------------------------------
# Helper: extract store name from page
# ------------------------------------------------------------------

def _guess_store_from_url(url: str) -> str:
    """Best-effort store name from URL path."""
    parsed = urlparse(url if "://" in url else f"https://{url}")
    path = parsed.path.strip("/")
    # Common patterns: /store/NAME, /view/NAME, /coupons/NAME
    for prefix in ("store/", "view/", "coupons/", "brand/", "shop/"):
        if prefix in path:
            slug = path.split(prefix, 1)[1].split("/")[0].split(".")[0]
            if slug:
                return slug.replace("-", " ").replace("_", " ").title()
    # Fall back to domain
    domain = parsed.netloc.lower().replace("www.", "")
    return domain.split(".")[0].title() if domain else "UNKNOWN_STORE"


def _guess_store_from_html(soup: BeautifulSoup) -> str | None:
    """Try to extract store name from <h1> or <title>."""
    h1 = soup.find("h1")
    if h1:
        text = h1.get_text(strip=True)
        # Common coupon page patterns
        for pattern in [
            r"^(.*?)\s+(?:Coupons?|Promo|Deals?|Discounts?|优惠|折扣)",
            r"^(.*?)\s*[（(]",  # "Store Name（description）"
        ]:
            m = re.match(pattern, text, re.IGNORECASE)
            if m and m.group(1).strip():
                return m.group(1).strip()
    return None


# ------------------------------------------------------------------
# Universal extractor
# ------------------------------------------------------------------

class GenericDealExtractor(BaseDealExtractor):
    """Universal deal extractor — works on any site or language."""

    name = "generic"
    supported_domains: list[str] = []

    def extract(
        self, html: str, text: str, url: str,
    ) -> list[DealCandidate]:
        candidates: list[DealCandidate] = []
        seen_offers: set[str] = set()

        # Guess store name
        store = "UNKNOWN_STORE"
        if html.strip():
            soup = BeautifulSoup(html, "lxml")
            store = _guess_store_from_html(soup) or _guess_store_from_url(url)
            # Strategy 1: DOM-based extraction
            dom_candidates = self._extract_from_dom(soup, store, url)
            for c in dom_candidates:
                key = self._dedup_key(c)
                if key not in seen_offers:
                    seen_offers.add(key)
                    candidates.append(c)
        else:
            store = _guess_store_from_url(url)

        # Strategy 2: Text-based multi-language extraction
        if text.strip():
            text_candidates = self._extract_from_text(text, store, url)
            for c in text_candidates:
                key = self._dedup_key(c)
                if key not in seen_offers:
                    seen_offers.add(key)
                    candidates.append(c)

        candidates.sort(key=lambda c: c.confidence, reverse=True)

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
        self, soup: BeautifulSoup, store: str, url: str,
    ) -> list[DealCandidate]:
        """Scan HTML for elements that look like coupon/deal containers."""
        candidates: list[DealCandidate] = []
        seen_text: set[str] = set()

        for selector in _DEAL_SELECTORS:
            try:
                elements = soup.select(selector)
            except Exception:
                continue

            for el in elements:
                if not isinstance(el, Tag):
                    continue
                text = el.get_text(" ", strip=True)
                if not text or len(text) < _MIN_LINE_LEN or len(text) > _MAX_LINE_LEN:
                    continue

                norm = re.sub(r"\s+", " ", text).lower()
                if norm in seen_text:
                    continue
                seen_text.add(norm)

                # Check if this element has deal signals
                parsed = self._parse_text(text, store)
                if parsed is not None:
                    parsed.raw_html = str(el)[:500]
                    candidates.append(parsed)

        return candidates

    # ------------------------------------------------------------------
    # Strategy 2: Text-based multi-language extraction
    # ------------------------------------------------------------------

    def _extract_from_text(
        self, text: str, store: str, url: str,
    ) -> list[DealCandidate]:
        """Scan cleaned text line-by-line for deal signals."""
        candidates: list[DealCandidate] = []

        for line in text.splitlines():
            stripped = line.strip()
            if len(stripped) < _MIN_LINE_LEN or len(stripped) > _MAX_LINE_LEN:
                continue

            parsed = self._parse_text(stripped, store)
            if parsed is not None:
                candidates.append(parsed)

        return candidates

    # ------------------------------------------------------------------
    # Core parsing — multi-language signal detection
    # ------------------------------------------------------------------

    def _parse_text(self, line: str, store: str) -> DealCandidate | None:
        """Parse a single text line for deal signals in any language.

        Returns None if no deal signal is found.
        """
        offer_type: str | None = None
        discount_percent: float | None = None
        discount_amount: str | None = None
        max_discount_amount: str | None = None
        cashback_percent: float | None = None
        coupon_code: str | None = None
        min_spend: str | None = None
        signals_found = 0

        # ----- English patterns -----
        pct = PERCENT_OFF_PATTERN.search(line)
        if pct:
            discount_percent = float(pct.group(1))
            offer_type = "SALE"
            signals_found += 1

        amt = AMOUNT_OFF_PATTERN.search(line)
        if amt and not UP_TO_AMOUNT_OFF_PATTERN.search(line):
            discount_amount = amt.group(1)
            offer_type = "SALE"
            signals_found += 1

        upto = UP_TO_AMOUNT_OFF_PATTERN.search(line)
        if upto:
            max_discount_amount = upto.group(1)
            signals_found += 1

        up_pct = _EN_UP_TO_PCT_OFF.search(line)
        if up_pct and discount_percent is None:
            discount_percent = float(up_pct.group(1))
            offer_type = "SALE"
            signals_found += 1

        extra = _EN_EXTRA_OFF.search(line)
        if extra and discount_percent is None:
            discount_percent = float(extra.group(1))
            offer_type = "SALE"
            signals_found += 1

        save = _EN_SAVE_AMOUNT.search(line)
        if save and discount_amount is None:
            discount_amount = save.group(1)
            offer_type = "SALE"
            signals_found += 1

        cb = CASHBACK_PATTERN.search(line)
        if cb:
            cashback_percent = float(cb.group(1))
            offer_type = "REWARD"
            signals_found += 1

        if _EN_FREE_SHIPPING.search(line):
            offer_type = "SHIPPING"
            signals_found += 1

        if BOGO_PATTERN.search(line):
            offer_type = "BOGO"
            signals_found += 1

        code = _EN_COUPON_CODE.search(line)
        if code:
            coupon_code = code.group(1)
            offer_type = "COUPON"
            signals_found += 1

        # ----- Chinese patterns -----
        zh_extra = _ZH_EXTRA_DISCOUNT.search(line)
        if zh_extra:
            zhe_val = float(zh_extra.group(1))
            discount_percent = round((10 - zhe_val) * 10, 1)
            offer_type = "SALE"
            signals_found += 1

        zh_low = _ZH_LOW_AS.search(line)
        if zh_low and discount_percent is None:
            zhe_val = float(zh_low.group(1))
            discount_percent = round((10 - zhe_val) * 10, 1)
            offer_type = "SALE"
            signals_found += 1

        zh_zhe = _ZH_DISCOUNT_ZHEKOU.search(line)
        if zh_zhe and discount_percent is None and not zh_extra and not zh_low:
            zhe_val = float(zh_zhe.group(1))
            if 0 < zhe_val < 10:
                discount_percent = round((10 - zhe_val) * 10, 1)
                offer_type = "SALE"
                signals_found += 1

        zh_cb = _ZH_CASHBACK.search(line)
        if zh_cb:
            cashback_percent = float(zh_cb.group(1))
            offer_type = "REWARD"
            signals_found += 1

        zh_code = _ZH_COUPON_CODE.search(line)
        if zh_code:
            coupon_code = zh_code.group(1)
            offer_type = "COUPON"
            signals_found += 1

        if _ZH_FREE_SHIPPING.search(line):
            offer_type = "SHIPPING"
            signals_found += 1

        zh_full_minus = _ZH_FULL_MINUS.search(line)
        if zh_full_minus:
            min_spend = zh_full_minus.group(1)
            discount_amount = zh_full_minus.group(2)
            offer_type = "SALE"
            signals_found += 1

        if _ZH_BUY_GET.search(line):
            offer_type = "BOGO"
            signals_found += 1

        if _ZH_DEAL_SIGNAL.search(line):
            signals_found += 1

        # ----- Korean patterns -----
        ko_d = _KO_DISCOUNT.search(line)
        if ko_d and discount_percent is None:
            discount_percent = float(ko_d.group(1))
            offer_type = "SALE"
            signals_found += 1

        ko_code = _KO_COUPON.search(line)
        if ko_code and coupon_code is None:
            coupon_code = ko_code.group(1)
            offer_type = "COUPON"
            signals_found += 1

        if _KO_FREE_SHIPPING.search(line):
            offer_type = "SHIPPING"
            signals_found += 1

        # ----- Japanese patterns -----
        ja_d = _JA_OFF.search(line)
        if ja_d and discount_percent is None:
            discount_percent = float(ja_d.group(1))
            offer_type = "SALE"
            signals_found += 1

        ja_code = _JA_COUPON.search(line)
        if ja_code and coupon_code is None:
            coupon_code = ja_code.group(1)
            offer_type = "COUPON"
            signals_found += 1

        if _JA_FREE_SHIPPING.search(line):
            offer_type = "SHIPPING"
            signals_found += 1

        # ----- Spanish/Portuguese -----
        es_d = _ES_DISCOUNT.search(line)
        if es_d and discount_percent is None:
            discount_percent = float(es_d.group(1))
            offer_type = "SALE"
            signals_found += 1

        es_code = _ES_COUPON.search(line)
        if es_code and coupon_code is None:
            coupon_code = es_code.group(1)
            offer_type = "COUPON"
            signals_found += 1

        if _ES_FREE_SHIPPING.search(line):
            offer_type = "SHIPPING"
            signals_found += 1

        # ----- No deal signal found -----
        if signals_found == 0:
            return None

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
        )
        candidate.confidence = score_candidate(candidate)

        # Boost multi-signal lines (very likely a real deal)
        if signals_found >= 2:
            candidate.confidence = min(1.0, candidate.confidence + 0.08)
            candidate.reasons.append("multi_signal")

        return candidate if candidate.confidence >= 0.3 else None

    # ------------------------------------------------------------------

    @staticmethod
    def _dedup_key(c: DealCandidate) -> str:
        text = re.sub(r"\s+", " ", (c.offer or c.normalized_line)).lower().strip()
        return text

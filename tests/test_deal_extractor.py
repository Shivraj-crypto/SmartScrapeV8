"""Tests for RetailMeNot and generic deal extractors."""

from __future__ import annotations

from smart_scrape.processor.deal_extractor import RetailMeNotExtractor
from smart_scrape.processor.generic_extractor import GenericDealExtractor
from smart_scrape.processor.ranking import score_candidate, deduplicate_candidates
from smart_scrape.processor.models import DealCandidate


# ------------------------------------------------------------------
# RetailMeNotExtractor
# ------------------------------------------------------------------

class TestRetailMeNotExtractor:
    def test_extracts_candidates_from_offer_strips(self, sample_retailmenot_html: str):
        extractor = RetailMeNotExtractor()
        candidates = extractor.extract(
            html=sample_retailmenot_html, text="", url="https://www.retailmenot.com/view/teststore.com",
        )
        assert len(candidates) >= 3
        # All should have the store hint from <h1>
        for c in candidates:
            assert c.store == "TestStore"
            assert c.source == "retailmenot"

    def test_detects_coupon_type(self, sample_retailmenot_html: str):
        extractor = RetailMeNotExtractor()
        candidates = extractor.extract(
            html=sample_retailmenot_html, text="", url="https://www.retailmenot.com/view/teststore.com",
        )
        coupon_candidates = [c for c in candidates if c.offer_type == "COUPON"]
        assert len(coupon_candidates) >= 1

    def test_detects_shipping_type(self, sample_retailmenot_html: str):
        extractor = RetailMeNotExtractor()
        candidates = extractor.extract(
            html=sample_retailmenot_html, text="", url="https://www.retailmenot.com/view/teststore.com",
        )
        shipping = [c for c in candidates if c.offer_type == "SHIPPING"]
        assert len(shipping) >= 1

    def test_detects_cashback(self, sample_retailmenot_html: str):
        extractor = RetailMeNotExtractor()
        candidates = extractor.extract(
            html=sample_retailmenot_html, text="", url="https://www.retailmenot.com/view/teststore.com",
        )
        cashback = [c for c in candidates if c.cashback_percent is not None]
        assert len(cashback) >= 1
        assert cashback[0].cashback_percent == 5.0

    def test_detects_bogo(self, sample_retailmenot_html: str):
        extractor = RetailMeNotExtractor()
        candidates = extractor.extract(
            html=sample_retailmenot_html, text="", url="https://www.retailmenot.com/view/teststore.com",
        )
        bogo = [c for c in candidates if c.offer_type == "BOGO"]
        assert len(bogo) >= 1

    def test_detects_discount_percent(self, sample_retailmenot_html: str):
        extractor = RetailMeNotExtractor()
        candidates = extractor.extract(
            html=sample_retailmenot_html, text="", url="https://www.retailmenot.com/view/teststore.com",
        )
        pct = [c for c in candidates if c.discount_percent is not None]
        assert len(pct) >= 1
        assert 20.0 in [c.discount_percent for c in pct]

    def test_extracts_min_spend(self, sample_retailmenot_html: str):
        extractor = RetailMeNotExtractor()
        candidates = extractor.extract(
            html=sample_retailmenot_html, text="", url="https://www.retailmenot.com/view/teststore.com",
        )
        with_spend = [c for c in candidates if c.min_spend is not None]
        assert len(with_spend) >= 1

    def test_returns_empty_for_blank_html(self):
        extractor = RetailMeNotExtractor()
        assert extractor.extract(html="", text="", url="https://example.com") == []

    def test_returns_empty_for_no_offer_strips(self):
        extractor = RetailMeNotExtractor()
        html = "<html><body><h1>No deals here</h1></body></html>"
        assert extractor.extract(html=html, text="", url="https://example.com") == []

    def test_filters_noise_offers(self):
        extractor = RetailMeNotExtractor()
        html = """
        <html><body>
        <a data-component-class="offer_strip">
            <h3>How can I reach customer support?</h3>
        </a>
        </body></html>
        """
        assert extractor.extract(html=html, text="", url="") == []


# ------------------------------------------------------------------
# GenericDealExtractor
# ------------------------------------------------------------------

class TestGenericDealExtractor:
    def test_extracts_percent_off(self, sample_generic_text: str):
        extractor = GenericDealExtractor()
        candidates = extractor.extract(html="", text=sample_generic_text, url="https://example.com")
        pct = [c for c in candidates if c.discount_percent is not None]
        assert len(pct) >= 1

    def test_extracts_amount_off(self, sample_generic_text: str):
        extractor = GenericDealExtractor()
        candidates = extractor.extract(html="", text=sample_generic_text, url="https://example.com")
        amt = [c for c in candidates if c.discount_amount is not None]
        assert len(amt) >= 1

    def test_extracts_free_shipping(self, sample_generic_text: str):
        extractor = GenericDealExtractor()
        candidates = extractor.extract(html="", text=sample_generic_text, url="https://example.com")
        shipping = [c for c in candidates if c.offer_type == "SHIPPING"]
        assert len(shipping) >= 1

    def test_extracts_cashback(self, sample_generic_text: str):
        extractor = GenericDealExtractor()
        candidates = extractor.extract(html="", text=sample_generic_text, url="https://example.com")
        cashback = [c for c in candidates if c.cashback_percent is not None]
        assert len(cashback) >= 1

    def test_extracts_bogo(self, sample_generic_text: str):
        extractor = GenericDealExtractor()
        candidates = extractor.extract(html="", text=sample_generic_text, url="https://example.com")
        bogo = [c for c in candidates if c.offer_type == "BOGO"]
        assert len(bogo) >= 1

    def test_extracts_coupon_code(self, sample_generic_text: str):
        extractor = GenericDealExtractor()
        candidates = extractor.extract(html="", text=sample_generic_text, url="https://example.com")
        codes = [c for c in candidates if c.coupon_code is not None]
        assert len(codes) >= 1
        assert "WELCOME25" in [c.coupon_code for c in codes]

    def test_source_is_generic(self, sample_generic_text: str):
        extractor = GenericDealExtractor()
        candidates = extractor.extract(html="", text=sample_generic_text, url="https://example.com")
        for c in candidates:
            assert c.source == "generic"

    def test_returns_empty_for_blank_text(self):
        extractor = GenericDealExtractor()
        assert extractor.extract(html="", text="", url="") == []

    def test_ignores_short_lines(self):
        extractor = GenericDealExtractor()
        assert extractor.extract(html="", text="hi", url="") == []

    # -- Chinese --
    def test_chinese_zhekou_discount(self):
        extractor = GenericDealExtractor()
        text = "精选额外9折"
        candidates = extractor.extract(html="", text=text, url="https://55haitao.com/store/mk.html")
        assert len(candidates) >= 1
        assert candidates[0].discount_percent == 10.0  # 9折 = 10% off

    def test_chinese_cashback(self):
        extractor = GenericDealExtractor()
        text = "最高5%返利"
        candidates = extractor.extract(html="", text=text, url="https://55haitao.com/store/mk.html")
        assert len(candidates) >= 1
        assert candidates[0].cashback_percent == 5.0

    def test_chinese_coupon_code(self):
        extractor = GenericDealExtractor()
        text = "优惠码 EXTRA10 有效至：至2026-04-21止"
        candidates = extractor.extract(html="", text=text, url="https://55haitao.com")
        codes = [c for c in candidates if c.coupon_code is not None]
        assert len(codes) >= 1
        assert "EXTRA10" in [c.coupon_code for c in codes]

    def test_chinese_free_shipping(self):
        extractor = GenericDealExtractor()
        text = "满175美元包邮"
        candidates = extractor.extract(html="", text=text, url="https://55haitao.com")
        shipping = [c for c in candidates if c.offer_type == "SHIPPING"]
        assert len(shipping) >= 1

    def test_chinese_full_minus(self):
        extractor = GenericDealExtractor()
        text = "满200减50活动"
        candidates = extractor.extract(html="", text=text, url="https://55haitao.com")
        assert len(candidates) >= 1
        assert candidates[0].min_spend == "200"
        assert candidates[0].discount_amount == "50"

    def test_chinese_low_as(self):
        extractor = GenericDealExtractor()
        text = "清仓特卖低至5折"
        candidates = extractor.extract(html="", text=text, url="https://55haitao.com")
        assert len(candidates) >= 1
        assert candidates[0].discount_percent == 50.0  # 5折 = 50% off

    def test_chinese_buy_get(self):
        extractor = GenericDealExtractor()
        text = "买1送1全场促销活动"
        candidates = extractor.extract(html="", text=text, url="https://55haitao.com")
        bogo = [c for c in candidates if c.offer_type == "BOGO"]
        assert len(bogo) >= 1

    # -- Korean --
    def test_korean_discount(self):
        extractor = GenericDealExtractor()
        text = "최대 30% 할인 세일"
        candidates = extractor.extract(html="", text=text, url="https://example.kr")
        pct = [c for c in candidates if c.discount_percent == 30.0]
        assert len(pct) >= 1

    # -- Japanese --
    def test_japanese_discount(self):
        extractor = GenericDealExtractor()
        text = "最大50%オフセール"
        candidates = extractor.extract(html="", text=text, url="https://example.jp")
        pct = [c for c in candidates if c.discount_percent == 50.0]
        assert len(pct) >= 1

    # -- Spanish --
    def test_spanish_discount(self):
        extractor = GenericDealExtractor()
        text = "20% de descuento en toda la tienda"
        candidates = extractor.extract(html="", text=text, url="https://example.es")
        pct = [c for c in candidates if c.discount_percent == 20.0]
        assert len(pct) >= 1

    def test_spanish_free_shipping(self):
        extractor = GenericDealExtractor()
        text = "Envío gratis en pedidos superiores"
        candidates = extractor.extract(html="", text=text, url="https://example.es")
        shipping = [c for c in candidates if c.offer_type == "SHIPPING"]
        assert len(shipping) >= 1

    # -- Store name guessing --
    def test_guesses_store_from_url(self):
        extractor = GenericDealExtractor()
        text = "20% off everything"
        candidates = extractor.extract(html="", text=text, url="https://55haitao.com/store/michael-kors.html")
        assert candidates[0].store == "Michael Kors"

    # -- DOM extraction --
    def test_dom_extraction_from_deal_classes(self):
        extractor = GenericDealExtractor()
        html = """
        <html><body>
        <div class="coupon-item">Save 15% off with code SAVE15</div>
        <div class="deal-card">Free shipping on orders $50+</div>
        <div class="unrelated">Just regular text here</div>
        </body></html>
        """
        candidates = extractor.extract(html=html, text="", url="https://example.com")
        assert len(candidates) >= 2


# ------------------------------------------------------------------
# Scoring
# ------------------------------------------------------------------

class TestScoring:
    def test_score_candidate_base(self):
        c = DealCandidate(store="X", offer="Something", source="test")
        score = score_candidate(c)
        assert 0.3 <= score <= 0.5  # base + store

    def test_coupon_scores_higher(self):
        c1 = DealCandidate(store="X", offer="10% off", source="test", offer_type="COUPON", discount_percent=10.0)
        c2 = DealCandidate(store="X", offer="10% off", source="test", offer_type="SALE", discount_percent=10.0)
        s1 = score_candidate(c1)
        s2 = score_candidate(c2)
        assert s1 > s2

    def test_score_clamped_to_1(self):
        c = DealCandidate(
            store="X", offer="50% off + free shipping", source="test",
            offer_type="COUPON", discount_percent=50.0, cashback_percent=5.0,
            min_spend="$50", expiry="Dec 31, 2026", expiry_type="date",
            max_discount_amount="$100",
        )
        s = score_candidate(c)
        assert s <= 1.0


# ------------------------------------------------------------------
# Deduplication
# ------------------------------------------------------------------

class TestDeduplication:
    def test_removes_exact_duplicates(self):
        c1 = DealCandidate(store="X", offer="20% off sitewide", source="test", confidence=0.8)
        c2 = DealCandidate(store="X", offer="20% off sitewide", source="test", confidence=0.7)
        result = deduplicate_candidates([c1, c2])
        assert len(result) == 1

    def test_keeps_different_offers(self):
        c1 = DealCandidate(store="X", offer="20% off sitewide", source="test")
        c2 = DealCandidate(store="X", offer="Free shipping", source="test")
        result = deduplicate_candidates([c1, c2])
        assert len(result) == 2

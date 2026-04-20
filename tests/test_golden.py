"""Golden dataset regression tests.

These tests compare extractor output against known-good fixtures to
prevent regressions when modifying extraction logic.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from smart_scrape.processor.deal_extractor import RetailMeNotExtractor

GOLDEN_DIR = Path(__file__).resolve().parent / "golden"


def _load_golden_fixtures() -> list[tuple[str, str]]:
    """Discover paired .html / .json golden fixtures."""
    pairs: list[tuple[str, str]] = []
    for html_file in sorted(GOLDEN_DIR.glob("*.html")):
        json_file = html_file.with_suffix(".json")
        if json_file.exists():
            pairs.append((str(html_file), str(json_file)))
    return pairs


GOLDEN_FIXTURES = _load_golden_fixtures()


@pytest.mark.parametrize(
    "html_path,json_path",
    GOLDEN_FIXTURES,
    ids=[Path(h).stem for h, _ in GOLDEN_FIXTURES],
)
class TestGoldenExtraction:
    def test_min_candidate_count(self, html_path: str, json_path: str):
        html = Path(html_path).read_text(encoding="utf-8")
        expected = json.loads(Path(json_path).read_text(encoding="utf-8"))

        extractor = RetailMeNotExtractor()
        candidates = extractor.extract(
            html=html, text="", url=expected["url"],
        )
        assert len(candidates) >= expected["min_expected_count"], (
            f"Expected at least {expected['min_expected_count']} candidates, "
            f"got {len(candidates)}"
        )

    def test_store_name(self, html_path: str, json_path: str):
        html = Path(html_path).read_text(encoding="utf-8")
        expected = json.loads(Path(json_path).read_text(encoding="utf-8"))

        extractor = RetailMeNotExtractor()
        candidates = extractor.extract(
            html=html, text="", url=expected["url"],
        )
        if candidates:
            assert candidates[0].store == expected["expected_store"]

    def test_top_offers_match(self, html_path: str, json_path: str):
        html = Path(html_path).read_text(encoding="utf-8")
        expected = json.loads(Path(json_path).read_text(encoding="utf-8"))

        extractor = RetailMeNotExtractor()
        candidates = extractor.extract(
            html=html, text="", url=expected["url"],
        )

        for exp_offer in expected.get("expected_top_offers", []):
            offer_substr = exp_offer["offer_contains"]
            matching = [
                c for c in candidates
                if offer_substr.lower() in (c.offer or "").lower()
            ]
            assert matching, (
                f"Expected a candidate containing '{offer_substr}', "
                f"but none found among {[c.offer for c in candidates[:10]]}"
            )

            best = matching[0]

            if "offer_type" in exp_offer:
                assert best.offer_type == exp_offer["offer_type"], (
                    f"Offer '{best.offer}' — expected type={exp_offer['offer_type']}, "
                    f"got type={best.offer_type}"
                )

            if "discount_percent" in exp_offer:
                assert best.discount_percent == exp_offer["discount_percent"]

            if "cashback_percent" in exp_offer:
                assert best.cashback_percent == exp_offer["cashback_percent"]

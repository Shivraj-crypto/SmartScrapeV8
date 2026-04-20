"""Tests for rendering strategies (Text, JSON, CSV)."""

from __future__ import annotations

import csv
import io
import json

from smart_scrape.processor.models import DealCandidate, ExtractionReport
from smart_scrape.rendering.base import create_renderer
from smart_scrape.rendering.text import TextRenderer
from smart_scrape.rendering.json_renderer import JSONRenderer
from smart_scrape.rendering.csv_renderer import CSVRenderer


def _make_report() -> ExtractionReport:
    return ExtractionReport(
        candidates=[
            DealCandidate(
                store="TestStore",
                offer="20% Off Sitewide",
                source="retailmenot",
                offer_type="COUPON",
                discount_percent=20.0,
                confidence=0.85,
                reasons=["coupon", "discount"],
            ),
            DealCandidate(
                store="TestStore",
                offer="Free Shipping On $50+",
                source="retailmenot",
                offer_type="SHIPPING",
                min_spend="$50+",
                confidence=0.71,
                reasons=["shipping", "min_spend"],
            ),
        ],
        overall_confidence=0.78,
    )


def _make_empty_report() -> ExtractionReport:
    return ExtractionReport(candidates=[], overall_confidence=0.0)


# ------------------------------------------------------------------
# Factory
# ------------------------------------------------------------------

class TestCreateRenderer:
    def test_text(self):
        r = create_renderer("text")
        assert isinstance(r, TextRenderer)

    def test_json(self):
        r = create_renderer("json")
        assert isinstance(r, JSONRenderer)

    def test_csv(self):
        r = create_renderer("csv")
        assert isinstance(r, CSVRenderer)

    def test_unknown_raises(self):
        import pytest
        with pytest.raises(ValueError, match="Unknown output format"):
            create_renderer("xml")


# ------------------------------------------------------------------
# TextRenderer
# ------------------------------------------------------------------

class TestTextRenderer:
    def test_contains_confidence(self):
        output = TextRenderer().render(_make_report())
        assert "OVERALL_CONFIDENCE=0.78" in output

    def test_contains_candidates(self):
        output = TextRenderer().render(_make_report())
        assert "20% Off Sitewide" in output
        assert "Free Shipping" in output

    def test_empty_report(self):
        output = TextRenderer().render(_make_empty_report())
        assert "NO_DEALS_FOUND" in output

    def test_llm_fallback_output(self):
        report = _make_empty_report()
        report.used_llm_fallback = True
        report.fallback_response_text = "TestStore | 10% off | CODE123"
        output = TextRenderer().render(report)
        assert "LLM_FALLBACK_OUTPUT" in output
        assert "CODE123" in output

    def test_file_extension(self):
        assert TextRenderer().file_extension == "txt"


# ------------------------------------------------------------------
# JSONRenderer
# ------------------------------------------------------------------

class TestJSONRenderer:
    def test_valid_json(self):
        output = JSONRenderer().render(_make_report())
        data = json.loads(output)
        assert isinstance(data, dict)

    def test_contains_candidates(self):
        output = JSONRenderer().render(_make_report())
        data = json.loads(output)
        assert data["candidate_count"] == 2
        assert len(data["candidates"]) == 2
        assert data["candidates"][0]["store"] == "TestStore"
        assert data["candidates"][0]["discount_percent"] == 20.0

    def test_overall_confidence(self):
        output = JSONRenderer().render(_make_report())
        data = json.loads(output)
        assert data["overall_confidence"] == 0.78

    def test_empty_report(self):
        output = JSONRenderer().render(_make_empty_report())
        data = json.loads(output)
        assert data["candidate_count"] == 0
        assert data["candidates"] == []

    def test_file_extension(self):
        assert JSONRenderer().file_extension == "json"


# ------------------------------------------------------------------
# CSVRenderer
# ------------------------------------------------------------------

class TestCSVRenderer:
    def test_valid_csv(self):
        output = CSVRenderer().render(_make_report())
        reader = csv.DictReader(io.StringIO(output))
        rows = list(reader)
        assert len(rows) == 2

    def test_contains_fields(self):
        output = CSVRenderer().render(_make_report())
        reader = csv.DictReader(io.StringIO(output))
        rows = list(reader)
        assert rows[0]["store"] == "TestStore"
        assert rows[0]["offer"] == "20% Off Sitewide"
        assert rows[0]["discount_percent"] == "20.0"

    def test_empty_report(self):
        output = CSVRenderer().render(_make_empty_report())
        reader = csv.DictReader(io.StringIO(output))
        rows = list(reader)
        assert len(rows) == 0

    def test_file_extension(self):
        assert CSVRenderer().file_extension == "csv"

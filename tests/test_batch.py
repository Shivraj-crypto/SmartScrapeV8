"""Tests for batch utilities."""

from __future__ import annotations

import csv
import io
from pathlib import Path

from smart_scrape.batch.excel_batch import (
    BatchSummaryRecord,
    build_output_stem,
    write_batch_summary_csv,
    _normalize_header,
    _looks_like_url,
)


class TestNormalizeHeader:
    def test_lowercases(self):
        assert _normalize_header("URL") == "url"

    def test_replaces_spaces(self):
        assert _normalize_header("Page URL") == "page_url"

    def test_strips_special_chars(self):
        assert _normalize_header("  Deal-URL! ") == "deal_url"


class TestLooksLikeUrl:
    def test_full_url(self):
        assert _looks_like_url("https://example.com") is True

    def test_without_scheme(self):
        assert _looks_like_url("example.com") is True

    def test_blank(self):
        assert _looks_like_url("") is False

    def test_whitespace_only(self):
        assert _looks_like_url("   ") is False


class TestBuildOutputStem:
    def test_basic_url(self):
        stem = build_output_stem(1, "https://www.retailmenot.com/view/test.com")
        assert stem.startswith("row_00001_")
        assert "retailmenot" in stem

    def test_truncates_long_slugs(self):
        long_url = "https://example.com/" + "a" * 200
        stem = build_output_stem(42, long_url)
        # Slug is capped at 80 chars
        slug_part = stem.split("_", 2)[-1]
        assert len(slug_part) <= 80

    def test_handles_query_params(self):
        stem = build_output_stem(3, "https://example.com/page?q=test&sort=asc")
        assert "example" in stem

    def test_handles_bare_domain(self):
        stem = build_output_stem(1, "example.com")
        assert "example" in stem


class TestWriteBatchSummaryCsv:
    def test_writes_valid_csv(self, tmp_path: Path):
        records = [
            BatchSummaryRecord(
                row_number=1,
                requested_url="https://example.com",
                status="ok",
                final_url="https://example.com/",
                title="Example",
                status_code=200,
                elapsed_ms=1500,
                overall_confidence=0.85,
                candidate_count=12,
            ),
            BatchSummaryRecord(
                row_number=2,
                requested_url="https://bad.com",
                status="error",
                error="Timeout",
            ),
        ]
        out = tmp_path / "summary.csv"
        write_batch_summary_csv(records, out)
        assert out.exists()

        content = out.read_text(encoding="utf-8")
        reader = csv.DictReader(io.StringIO(content))
        rows = list(reader)
        assert len(rows) == 2
        assert rows[0]["status"] == "ok"
        assert rows[0]["overall_confidence"] == "0.85"
        assert rows[1]["status"] == "error"
        assert rows[1]["error"] == "Timeout"

"""CSV renderer for tabular deal output."""

from __future__ import annotations

import csv
import io

from smart_scrape.processor.models import ExtractionReport
from smart_scrape.rendering.base import Renderer

_FIELDS = [
    "store",
    "offer",
    "source",
    "offer_type",
    "coupon_code",
    "discount_percent",
    "discount_amount",
    "max_discount_amount",
    "cashback_percent",
    "min_spend",
    "expiry",
    "expiry_type",
    "confidence",
]


class CSVRenderer(Renderer):
    """Outputs deals as a CSV table with headers."""

    format_name = "csv"

    def render(self, report: ExtractionReport) -> str:
        buf = io.StringIO()
        writer = csv.DictWriter(buf, fieldnames=_FIELDS)
        writer.writeheader()
        for c in report.candidates:
            row = c.to_dict()
            writer.writerow({k: row.get(k, "") for k in _FIELDS})
        return buf.getvalue()

    @property
    def file_extension(self) -> str:
        return "csv"

"""JSON renderer for structured deal output."""

from __future__ import annotations

import json

from smart_scrape.processor.models import ExtractionReport
from smart_scrape.rendering.base import Renderer


class JSONRenderer(Renderer):
    """Outputs deals as a JSON document."""

    format_name = "json"

    def render(self, report: ExtractionReport) -> str:
        payload = {
            "overall_confidence": round(report.overall_confidence, 3),
            "used_llm_fallback": report.used_llm_fallback,
            "candidate_count": len(report.candidates),
            "candidates": [c.to_dict() for c in report.candidates],
        }
        if report.fallback_response_text:
            payload["llm_fallback_output"] = report.fallback_response_text
        if report.fallback_error:
            payload["llm_fallback_error"] = report.fallback_error
        return json.dumps(payload, indent=2, ensure_ascii=False) + "\n"

    @property
    def file_extension(self) -> str:
        return "json"

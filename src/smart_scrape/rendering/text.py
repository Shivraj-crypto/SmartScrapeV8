"""Plain-text renderer — backward-compatible with the original output format."""

from __future__ import annotations

from smart_scrape.processor.models import ExtractionReport
from smart_scrape.rendering.base import Renderer


class TextRenderer(Renderer):
    """Pipe-delimited text output (the legacy default)."""

    format_name = "text"

    def render(self, report: ExtractionReport) -> str:
        lines = [
            f"OVERALL_CONFIDENCE={report.overall_confidence:.2f}",
            f"USED_LLM_FALLBACK={'yes' if report.used_llm_fallback else 'no'}",
        ]

        lines.append("HEURISTIC_CANDIDATES")
        if report.candidates:
            for candidate in report.candidates:
                lines.append(candidate.to_output_line())
        else:
            lines.append("NO_DEALS_FOUND")

        if report.fallback_response_text:
            lines.append("LLM_FALLBACK_OUTPUT")
            lines.append(report.fallback_response_text)
        if report.fallback_error:
            lines.append("LLM_FALLBACK_ERROR")
            lines.append(report.fallback_error)

        return "\n".join(lines) + "\n"

    @property
    def file_extension(self) -> str:
        return "txt"

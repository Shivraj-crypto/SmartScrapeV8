from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class ScrapeResult:
    requested_url: str
    final_url: str
    title: str
    raw_html: str
    cleaned_html: str
    status_code: int | None
    elapsed_ms: int

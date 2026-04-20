"""Pipeline metrics collection."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class PipelineMetrics:
    """Tracks key performance indicators across a pipeline run."""

    urls_processed: int = 0
    urls_succeeded: int = 0
    urls_failed: int = 0
    total_retries: int = 0
    total_candidates_extracted: int = 0
    total_after_dedup: int = 0
    confidence_scores: list[float] = field(default_factory=list)

    # ------------------------------------------------------------------
    # Derived properties
    # ------------------------------------------------------------------

    @property
    def dedup_reduction_pct(self) -> float:
        """Percentage of candidates removed during deduplication."""
        if self.total_candidates_extracted == 0:
            return 0.0
        removed = self.total_candidates_extracted - self.total_after_dedup
        return round((removed / self.total_candidates_extracted) * 100, 1)

    @property
    def avg_confidence(self) -> float:
        """Mean confidence score across all retained candidates."""
        if not self.confidence_scores:
            return 0.0
        return round(sum(self.confidence_scores) / len(self.confidence_scores), 3)

    @property
    def retry_rate(self) -> float:
        """Retries per URL processed."""
        if self.urls_processed == 0:
            return 0.0
        return round(self.total_retries / self.urls_processed, 2)

    def summary(self) -> dict[str, Any]:
        """Return a serialisable summary dict."""
        return {
            "urls_processed": self.urls_processed,
            "urls_succeeded": self.urls_succeeded,
            "urls_failed": self.urls_failed,
            "total_retries": self.total_retries,
            "retry_rate": self.retry_rate,
            "total_candidates_extracted": self.total_candidates_extracted,
            "total_after_dedup": self.total_after_dedup,
            "dedup_reduction_pct": self.dedup_reduction_pct,
            "avg_confidence": self.avg_confidence,
        }

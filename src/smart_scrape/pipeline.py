"""DealExtractionPipeline — class-based orchestration.

Full deal lifecycle:
    scrape → extract → normalize → deduplicate → rank → enrich → render
"""

from __future__ import annotations

import asyncio
import logging
import random
import uuid
from dataclasses import dataclass
from pathlib import Path
from time import perf_counter

from smart_scrape.config import Settings
from smart_scrape.metrics import PipelineMetrics
from smart_scrape.processor.models import DealCandidate, ExtractionReport
from smart_scrape.processor.ranking import (
    deduplicate_candidates,
    normalize_candidates,
    rank_and_filter,
)
from smart_scrape.processor.registry import ExtractorRegistry, build_default_registry
from smart_scrape.qa.llm_client import LLMClientError, extract_deals_and_coupons_from_text
from smart_scrape.rendering.base import Renderer, create_renderer
from smart_scrape.scraper.exceptions import (
    EmptyContentError,
    InvalidURLError,
    NavigationError,
    ScraperError,
)
from smart_scrape.scraper.models import ScrapeResult
from smart_scrape.scraper.playwright_client import scrape_page

logger = logging.getLogger(__name__)


# Error classification for retry logic
_TRANSIENT_ERRORS = (NavigationError, ScraperError, OSError, TimeoutError)
_NON_RETRYABLE_ERRORS = (InvalidURLError, EmptyContentError)


@dataclass(slots=True)
class PipelineRunResult:
    """Complete output of a single-URL pipeline run."""

    scrape_result: ScrapeResult
    report: ExtractionReport
    run_id: str = ""


@dataclass(slots=True)
class SavedOutputPaths:
    html_path: Path | None = None
    text_path: Path | None = None
    deals_path: Path | None = None


class DealExtractionPipeline:
    """Full deal lifecycle: scrape → extract → normalize → dedup → rank → enrich → render.

    Designed for testability, extensibility, and metrics collection.
    """

    def __init__(
        self,
        settings: Settings,
        *,
        registry: ExtractorRegistry | None = None,
        renderer: Renderer | None = None,
        gemini_model: str | None = None,
        llm_fallback_threshold: float = 0.6,
        max_retries: int = 2,
        retry_backoff: float = 5.0,
        jitter: float = 2.0,
        min_confidence: float = 0.4,
    ) -> None:
        self.settings = settings
        self.registry = registry or build_default_registry()
        self.renderer = renderer or create_renderer("text")
        self.gemini_model = gemini_model
        self.llm_fallback_threshold = min(1.0, max(0.0, llm_fallback_threshold))
        self.max_retries = max_retries
        self.retry_backoff = retry_backoff
        self.jitter = jitter
        self.min_confidence = min_confidence
        self.metrics = PipelineMetrics()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def run(self, url: str) -> PipelineRunResult:
        """Execute the full pipeline for a single URL."""
        run_id = uuid.uuid4().hex[:12]
        logger.info(
            "pipeline_start",
            extra={"url": url, "run_id": run_id},
        )
        started_at = perf_counter()

        self.metrics.urls_processed += 1

        scrape_result = await self._scrape_with_retry(url, run_id)

        # Extract
        candidates = self._extract(scrape_result, url)
        pre_dedup_count = len(candidates)
        self.metrics.total_candidates_extracted += pre_dedup_count

        # Normalize → Dedup → Rank
        candidates = self._normalize(candidates)
        candidates = self._deduplicate(candidates)
        self.metrics.total_after_dedup += len(candidates)
        candidates = self._rank_and_filter(candidates)

        # Enrich — LLM fallback if heuristic confidence is low
        report = self._build_report(candidates)
        report = self._enrich_with_llm(report, scrape_result.cleaned_text, run_id)

        # Record confidence scores
        for c in report.candidates:
            self.metrics.confidence_scores.append(c.confidence)

        self.metrics.urls_succeeded += 1
        elapsed_ms = int((perf_counter() - started_at) * 1000)
        logger.info(
            "pipeline_complete",
            extra={
                "url": url,
                "run_id": run_id,
                "elapsed_ms": elapsed_ms,
                "candidates": len(report.candidates),
                "confidence": report.overall_confidence,
                "dedup_reduction": pre_dedup_count - len(report.candidates),
            },
        )

        return PipelineRunResult(
            scrape_result=scrape_result,
            report=report,
            run_id=run_id,
        )

    def render_report(self, report: ExtractionReport) -> str:
        """Render an extraction report using the configured renderer."""
        return self.renderer.render(report)

    def save_outputs(
        self,
        run_result: PipelineRunResult,
        *,
        save_html: str | None = None,
        save_text: str | None = None,
        save_deals: str | None = None,
        verbose: bool = True,
    ) -> SavedOutputPaths:
        """Write pipeline outputs to disk."""
        result = run_result.scrape_result
        saved = SavedOutputPaths()

        if save_html:
            output_path = Path(save_html).expanduser().resolve()
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(result.cleaned_html, encoding="utf-8")
            saved.html_path = output_path
            if verbose:
                logger.info("saved_html", extra={"path": str(output_path)})

        if save_text:
            output_path = Path(save_text).expanduser().resolve()
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(result.cleaned_text, encoding="utf-8")
            saved.text_path = output_path
            if verbose:
                logger.info("saved_text", extra={"path": str(output_path)})

        if save_deals:
            output_path = Path(save_deals).expanduser().resolve()
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(
                self.renderer.render(run_result.report), encoding="utf-8",
            )
            saved.deals_path = output_path
            if verbose:
                logger.info("saved_deals", extra={"path": str(output_path)})

        return saved

    def print_run_summary(self, run_result: PipelineRunResult) -> None:
        """Print a human-readable summary to the console."""
        r = run_result.scrape_result
        rpt = run_result.report

        logger.info(
            "run_summary",
            extra={
                "requested_url": r.requested_url,
                "final_url": r.final_url,
                "title": r.title or "(no title)",
                "status_code": r.status_code,
                "html_size": len(r.cleaned_html),
                "text_size": len(r.cleaned_text),
                "elapsed_ms": r.elapsed_ms,
                "heuristic_confidence": rpt.overall_confidence,
                "llm_fallback": rpt.used_llm_fallback,
                "candidates": len(rpt.candidates),
            },
        )

        if rpt.candidates:
            for candidate in rpt.candidates[:10]:
                logger.info("  candidate: %s", candidate.to_output_line())
        elif not rpt.used_llm_fallback:
            logger.info("  heuristic candidates: none")

        if rpt.fallback_response_text:
            logger.info("  LLM fallback output:\n%s", rpt.fallback_response_text)
        if rpt.fallback_error:
            logger.warning("  LLM fallback error: %s", rpt.fallback_error)

    def print_metrics_summary(self) -> None:
        """Log pipeline-wide metrics."""
        summary = self.metrics.summary()
        logger.info("pipeline_metrics: %s", summary)

    # ------------------------------------------------------------------
    # Internal stages
    # ------------------------------------------------------------------

    async def _scrape_with_retry(self, url: str, run_id: str) -> ScrapeResult:
        """Fetch page with exponential backoff + jitter on transient errors."""
        for attempt in range(self.max_retries + 1):
            try:
                return await scrape_page(url=url, settings=self.settings)
            except _NON_RETRYABLE_ERRORS:
                raise  # Fail fast
            except _TRANSIENT_ERRORS as exc:
                if attempt == self.max_retries:
                    raise
                backoff = self.retry_backoff * (2 ** attempt) + random.uniform(
                    0, self.jitter,
                )
                self.metrics.total_retries += 1
                logger.warning(
                    "retry_scrape",
                    extra={
                        "url": url,
                        "run_id": run_id,
                        "attempt": attempt + 1,
                        "max_retries": self.max_retries,
                        "backoff_seconds": round(backoff, 1),
                        "error": str(exc),
                    },
                )
                await asyncio.sleep(backoff)

        # Unreachable, but keeps type checkers happy.
        raise ScraperError(f"All retries exhausted for {url}")  # pragma: no cover

    def _extract(
        self, scrape_result: ScrapeResult, url: str
    ) -> list[DealCandidate]:
        """Run the registered extractor for this URL."""
        return self.registry.extract(
            html=scrape_result.cleaned_html,
            text=scrape_result.cleaned_text,
            url=url,
        )

    def _normalize(
        self, candidates: list[DealCandidate]
    ) -> list[DealCandidate]:
        return normalize_candidates(candidates)

    def _deduplicate(
        self, candidates: list[DealCandidate]
    ) -> list[DealCandidate]:
        return deduplicate_candidates(candidates)

    def _rank_and_filter(
        self, candidates: list[DealCandidate]
    ) -> list[DealCandidate]:
        return rank_and_filter(candidates, min_confidence=self.min_confidence)

    def _build_report(
        self, candidates: list[DealCandidate]
    ) -> ExtractionReport:
        if not candidates:
            return ExtractionReport(candidates=[], overall_confidence=0.0)

        top = candidates[:5]
        overall = sum(c.confidence for c in top) / len(top)
        return ExtractionReport(
            candidates=candidates,
            overall_confidence=round(overall, 2),
        )

    def _enrich_with_llm(
        self,
        report: ExtractionReport,
        cleaned_text: str,
        run_id: str,
    ) -> ExtractionReport:
        """Call Gemini if heuristic confidence is below threshold."""
        if report.overall_confidence >= self.llm_fallback_threshold:
            return report

        if not self.settings.gemini_api_key:
            return report

        model_name = (
            self.gemini_model.strip()
            if self.gemini_model
            else self.settings.gemini_model
        )

        logger.info(
            "llm_fallback_triggered",
            extra={
                "run_id": run_id,
                "confidence": report.overall_confidence,
                "threshold": self.llm_fallback_threshold,
                "model": model_name,
            },
        )

        try:
            fallback_text = extract_deals_and_coupons_from_text(
                text=cleaned_text,
                api_key=self.settings.gemini_api_key,
                model_name=model_name,
            )
            report.used_llm_fallback = True
            report.fallback_response_text = fallback_text
        except LLMClientError as exc:
            report.fallback_error = str(exc)
            logger.error(
                "llm_fallback_failed",
                extra={"run_id": run_id, "error": str(exc)},
            )

        return report

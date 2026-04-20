"""SmartScrapeV8 CLI entry-point.

Handles argument parsing, mode dispatch (single URL / text-file / batch),
and top-level error handling.  All orchestration logic lives in
``smart_scrape.pipeline.DealExtractionPipeline``.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from pathlib import Path

# Allow running this file directly without installing the package first.
PROJECT_ROOT = Path(__file__).resolve().parent
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from smart_scrape.batch import (
    BatchInputError,
    BatchSummaryRecord,
    build_output_stem,
    load_urls_from_excel,
    write_batch_summary_csv,
)
from smart_scrape.config import Settings
from smart_scrape.logging_config import setup_logging
from smart_scrape.pipeline import DealExtractionPipeline, SavedOutputPaths
from smart_scrape.qa.llm_client import LLMClientError, extract_deals_and_coupons_from_file
from smart_scrape.rendering.base import create_renderer
from smart_scrape.scraper.exceptions import (
    EmptyContentError,
    InvalidURLError,
    NavigationError,
    ScraperError,
)

logger = logging.getLogger(__name__)


# ------------------------------------------------------------------
# CLI argument parsing
# ------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Scrape a URL with Scrapling, or upload a .txt file to Gemini "
            "for deals/coupons extraction."
        ),
    )
    parser.add_argument(
        "url", nargs="?",
        help="URL to scrape, for example: https://apple.com",
    )
    parser.add_argument("--save-html", default=None)
    parser.add_argument("--save-text", default=None)
    parser.add_argument(
        "--input-text-file", default=None,
        help="Path to a .txt file for Gemini deals extraction.",
    )
    parser.add_argument(
        "--input-excel-file", default=None,
        help="Path to .xlsx/.xlsm for batch scraping.",
    )
    parser.add_argument("--excel-sheet", default=None)
    parser.add_argument("--excel-url-column", default=None)
    parser.add_argument("--save-deals", default=None)
    parser.add_argument("--gemini-model", default=None)
    parser.add_argument(
        "--llm-fallback-threshold", type=float, default=0.6,
        help="LLM fallback when heuristic confidence is below this (0.0–1.0).",
    )
    parser.add_argument("--batch-output-dir", default="output/batch_run")
    parser.add_argument("--batch-size", type=int, default=5)
    parser.add_argument("--delay-between-urls-seconds", type=float, default=3.0)
    parser.add_argument("--delay-between-batches-seconds", type=float, default=20.0)
    parser.add_argument("--cooldown-on-error-seconds", type=float, default=30.0)
    parser.add_argument("--batch-save-html", action="store_true")
    parser.add_argument(
        "--output-format", default="text", choices=["text", "json", "csv"],
        help="Output format for extracted deals (default: text).",
    )
    parser.add_argument(
        "--max-retries", type=int, default=2,
        help="Max retries on transient failures.",
    )
    parser.add_argument(
        "--retry-backoff-seconds", type=float, default=5.0,
        help="Base backoff between retries.",
    )
    parser.add_argument(
        "--verbose", "-v", action="store_true",
        help="Enable DEBUG-level logging.",
    )
    return parser.parse_args()


# ------------------------------------------------------------------
# Mode: single URL
# ------------------------------------------------------------------

async def run_single_url(pipeline: DealExtractionPipeline, args: argparse.Namespace) -> int:
    url = args.url.strip() if args.url else input("Enter URL to scrape: ").strip()
    if not url:
        logger.error("URL is required.")
        return 2

    run_result = await pipeline.run(url)
    pipeline.print_run_summary(run_result)
    pipeline.save_outputs(
        run_result,
        save_html=args.save_html,
        save_text=args.save_text,
        save_deals=args.save_deals,
    )
    return 0


# ------------------------------------------------------------------
# Mode: text file → Gemini
# ------------------------------------------------------------------

def run_gemini_deals_mode(settings: Settings, args: argparse.Namespace) -> int:
    model_name = (
        args.gemini_model.strip() if args.gemini_model else settings.gemini_model
    )
    input_file = args.input_text_file
    save_deals = args.save_deals or "output/deals_and_coupons.txt"

    response_text = extract_deals_and_coupons_from_file(
        input_text_file=Path(input_file),
        output_text_file=Path(save_deals),
        api_key=settings.gemini_api_key or "",
        model_name=model_name,
    )
    logger.info(
        "gemini_deals_complete",
        extra={
            "input": str(Path(input_file).expanduser().resolve()),
            "model": model_name,
            "response_size": len(response_text),
            "output": str(Path(save_deals).expanduser().resolve()),
        },
    )
    return 0


# ------------------------------------------------------------------
# Mode: Excel batch
# ------------------------------------------------------------------

async def run_excel_batch(pipeline: DealExtractionPipeline, args: argparse.Namespace) -> int:
    url_records = load_urls_from_excel(
        input_excel_file=Path(args.input_excel_file),
        url_column=args.excel_url_column,
        sheet_name=args.excel_sheet,
    )

    output_dir = Path(args.batch_output_dir).expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    text_dir = output_dir / "text"
    deals_dir = output_dir / "deals"
    html_dir = output_dir / "html"
    text_dir.mkdir(parents=True, exist_ok=True)
    deals_dir.mkdir(parents=True, exist_ok=True)
    if args.batch_save_html:
        html_dir.mkdir(parents=True, exist_ok=True)

    total_urls = len(url_records)
    total_batches = (total_urls + args.batch_size - 1) // args.batch_size
    summary_records: list[BatchSummaryRecord] = []
    failed_count = 0

    logger.info(
        "batch_start",
        extra={
            "total_urls": total_urls,
            "input_file": str(Path(args.input_excel_file).expanduser().resolve()),
            "batch_size": args.batch_size,
            "delay_between_urls": args.delay_between_urls_seconds,
            "delay_between_batches": args.delay_between_batches_seconds,
            "cooldown_on_error": args.cooldown_on_error_seconds,
        },
    )

    for batch_offset in range(0, total_urls, args.batch_size):
        batch_index = (batch_offset // args.batch_size) + 1
        batch_records = url_records[batch_offset : batch_offset + args.batch_size]
        logger.info(
            "batch_chunk_start",
            extra={
                "batch": f"{batch_index}/{total_batches}",
                "urls_in_batch": len(batch_records),
            },
        )

        for offset, url_record in enumerate(batch_records):
            global_index = batch_offset + offset + 1
            output_stem = build_output_stem(url_record.row_number, url_record.url)
            html_path = html_dir / f"{output_stem}.html" if args.batch_save_html else None
            text_path = text_dir / f"{output_stem}.txt"
            deals_ext = pipeline.renderer.file_extension
            deals_path = deals_dir / f"{output_stem}.{deals_ext}"

            logger.info(
                "batch_url",
                extra={
                    "index": f"{global_index}/{total_urls}",
                    "row": url_record.row_number,
                    "url": url_record.url,
                },
            )

            slept_for_error = False
            try:
                run_result = await pipeline.run(url_record.url)
                saved = pipeline.save_outputs(
                    run_result,
                    save_html=str(html_path) if html_path else None,
                    save_text=str(text_path),
                    save_deals=str(deals_path),
                    verbose=False,
                )
                top_candidate = (
                    run_result.report.candidates[0]
                    if run_result.report.candidates
                    else None
                )
                summary_records.append(
                    BatchSummaryRecord(
                        row_number=url_record.row_number,
                        requested_url=run_result.scrape_result.requested_url,
                        status="ok",
                        final_url=run_result.scrape_result.final_url,
                        title=run_result.scrape_result.title or None,
                        status_code=run_result.scrape_result.status_code,
                        elapsed_ms=run_result.scrape_result.elapsed_ms,
                        overall_confidence=run_result.report.overall_confidence,
                        candidate_count=len(run_result.report.candidates),
                        used_llm_fallback=run_result.report.used_llm_fallback,
                        fallback_error=run_result.report.fallback_error,
                        top_offer=top_candidate.offer if top_candidate else None,
                        top_offer_type=top_candidate.offer_type if top_candidate else None,
                        html_path=str(saved.html_path) if saved.html_path else None,
                        text_path=str(saved.text_path) if saved.text_path else None,
                        deals_path=str(saved.deals_path) if saved.deals_path else None,
                    ),
                )
                logger.info(
                    "  OK | status=%s | confidence=%.2f | candidates=%d",
                    run_result.scrape_result.status_code or "unknown",
                    run_result.report.overall_confidence,
                    len(run_result.report.candidates),
                )

            except (
                InvalidURLError, NavigationError, EmptyContentError,
                ScraperError, OSError,
            ) as exc:
                failed_count += 1
                pipeline.metrics.urls_failed += 1
                summary_records.append(
                    BatchSummaryRecord(
                        row_number=url_record.row_number,
                        requested_url=url_record.url,
                        status="error",
                        error=str(exc),
                    ),
                )
                logger.error("  FAILED | %s", exc)
                if args.cooldown_on_error_seconds > 0 and global_index < total_urls:
                    logger.info(
                        "  Cooling down %.1fs after error",
                        args.cooldown_on_error_seconds,
                    )
                    await asyncio.sleep(args.cooldown_on_error_seconds)
                    slept_for_error = True

            except Exception as exc:
                failed_count += 1
                pipeline.metrics.urls_failed += 1
                summary_records.append(
                    BatchSummaryRecord(
                        row_number=url_record.row_number,
                        requested_url=url_record.url,
                        status="error",
                        error=f"{exc.__class__.__name__}: {exc}",
                    ),
                )
                logger.error("  FAILED | %s: %s", exc.__class__.__name__, exc)
                if args.cooldown_on_error_seconds > 0 and global_index < total_urls:
                    logger.info(
                        "  Cooling down %.1fs after unexpected error",
                        args.cooldown_on_error_seconds,
                    )
                    await asyncio.sleep(args.cooldown_on_error_seconds)
                    slept_for_error = True

            has_next_url = global_index < total_urls
            has_next_in_batch = offset < len(batch_records) - 1
            if (
                has_next_url
                and has_next_in_batch
                and args.delay_between_urls_seconds > 0
                and not slept_for_error
            ):
                logger.info(
                    "  Sleeping %.1fs before next URL",
                    args.delay_between_urls_seconds,
                )
                await asyncio.sleep(args.delay_between_urls_seconds)

        if batch_index < total_batches and args.delay_between_batches_seconds > 0:
            logger.info(
                "Batch %d/%d complete. Sleeping %.1fs",
                batch_index, total_batches,
                args.delay_between_batches_seconds,
            )
            await asyncio.sleep(args.delay_between_batches_seconds)

    summary_path = output_dir / "batch_summary.csv"
    write_batch_summary_csv(summary_records, summary_path)
    logger.info("Batch summary saved to: %s", summary_path)
    logger.info(
        "Batch finished. Total: %d, succeeded: %d, failed: %d",
        total_urls, total_urls - failed_count, failed_count,
    )
    pipeline.print_metrics_summary()
    return 0 if failed_count == 0 else 9


# ------------------------------------------------------------------
# Main
# ------------------------------------------------------------------

def main() -> int:
    args = parse_args()
    setup_logging(verbose=args.verbose)

    settings = Settings.from_env()

    # Validate mutually exclusive inputs
    active_inputs = [
        bool(args.url), bool(args.input_text_file), bool(args.input_excel_file),
    ]
    if sum(active_inputs) > 1:
        logger.error(
            "Use only one of URL, --input-text-file, or --input-excel-file."
        )
        return 2

    if args.batch_size <= 0:
        logger.error("--batch-size must be greater than 0.")
        return 2

    if any(
        v < 0 for v in (
            args.delay_between_urls_seconds,
            args.delay_between_batches_seconds,
            args.cooldown_on_error_seconds,
        )
    ):
        logger.error("Batch delay values must be 0 or greater.")
        return 2

    # Build pipeline
    renderer = create_renderer(args.output_format)
    pipeline = DealExtractionPipeline(
        settings=settings,
        renderer=renderer,
        gemini_model=args.gemini_model,
        llm_fallback_threshold=args.llm_fallback_threshold,
        max_retries=args.max_retries,
        retry_backoff=args.retry_backoff_seconds,
    )

    # Dispatch to the selected mode
    if args.input_text_file:
        try:
            return run_gemini_deals_mode(settings, args)
        except LLMClientError as exc:
            logger.error("Gemini extraction failed: %s", exc)
            return 6
        except OSError as exc:
            logger.error("File operation failed: %s", exc)
            return 7

    if args.input_excel_file:
        try:
            return asyncio.run(run_excel_batch(pipeline, args))
        except BatchInputError as exc:
            logger.error("Batch input error: %s", exc)
            return 8
        except OSError as exc:
            logger.error("Batch file operation failed: %s", exc)
            return 7

    try:
        return asyncio.run(run_single_url(pipeline, args))
    except InvalidURLError as exc:
        logger.error("Invalid URL: %s", exc)
        return 2
    except NavigationError as exc:
        logger.error("Navigation failed: %s", exc)
        return 3
    except EmptyContentError as exc:
        logger.error("No usable content: %s", exc)
        return 4
    except ScraperError as exc:
        logger.error("Scraper error: %s", exc)
        return 5


if __name__ == "__main__":
    raise SystemExit(main())

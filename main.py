from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

# Allow running this file directly without installing the package first.
PROJECT_ROOT = Path(__file__).resolve().parent
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from smart_scrape.config import Settings
from smart_scrape.scraper.exceptions import (
    EmptyContentError,
    InvalidURLError,
    NavigationError,
    ScraperError,
)
from smart_scrape.scraper.playwright_client import scrape_page


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Fetch a URL with Playwright and return cleaned HTML."
    )
    parser.add_argument(
        "url",
        nargs="?",
        help="URL to scrape, for example: https://apple.com",
    )
    parser.add_argument(
        "--save-html",
        default=None,
        help="Optional file path to write cleaned HTML output.",
    )
    return parser.parse_args()


async def run(url: str, save_html: str | None) -> int:
    settings = Settings.from_env()
    result = await scrape_page(url=url, settings=settings)

    print(f"Requested URL: {result.requested_url}")
    print(f"Final URL: {result.final_url}")
    print(f"Title: {result.title or '(no title)'}")
    print(
        "Status Code: "
        f"{result.status_code if result.status_code is not None else 'unknown'}"
    )
    print(f"Cleaned HTML size: {len(result.cleaned_html)} characters")
    print(f"Elapsed: {result.elapsed_ms} ms")

    if save_html:
        output_path = Path(save_html).expanduser().resolve()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(result.cleaned_html, encoding="utf-8")
        print(f"Saved cleaned HTML to: {output_path}")

    return 0


def main() -> int:
    args = parse_args()
    url = args.url.strip() if args.url else input("Enter URL to scrape: ").strip()

    if not url:
        print("Error: URL is required.", file=sys.stderr)
        return 2

    try:
        return asyncio.run(run(url=url, save_html=args.save_html))
    except InvalidURLError as exc:
        print(f"Invalid URL: {exc}", file=sys.stderr)
        return 2
    except NavigationError as exc:
        print(f"Navigation failed: {exc}", file=sys.stderr)
        return 3
    except EmptyContentError as exc:
        print(f"No usable content: {exc}", file=sys.stderr)
        return 4
    except ScraperError as exc:
        print(f"Scraper error: {exc}", file=sys.stderr)
        return 5


if __name__ == "__main__":
    raise SystemExit(main())

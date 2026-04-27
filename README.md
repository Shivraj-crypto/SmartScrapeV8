<p align="center">
  <img src="src/res/SmartScrapeV8.png" alt="SmartScrapeV8" width="900">
</p>

<h1 align="center">SmartScrapeV8 &mdash; AI Deal Extraction Pipeline</h1>

<p align="center">
  <strong>Scrape pages, detect deals and coupons, score candidates, and fall back to Gemini only when heuristics are not confident enough.</strong>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.10%2B-3776AB?style=for-the-badge&logo=python&logoColor=white" alt="Python 3.10+">
  <img src="https://img.shields.io/badge/Scraper-Scrapling-111827?style=for-the-badge" alt="Scrapling">
  <img src="https://img.shields.io/badge/Extractor-Heuristic--first-0F766E?style=for-the-badge" alt="Heuristic first">
  <img src="https://img.shields.io/badge/Fallback-Gemini-F97316?style=for-the-badge" alt="Gemini fallback">
  <img src="https://img.shields.io/badge/Batch-Excel%20Mode-2563EB?style=for-the-badge" alt="Excel batch mode">
</p>

<p align="center">
  <a href="#quick-start">Quick Start</a> &middot;
  <a href="#what-is-implemented-now">Features</a> &middot;
  <a href="#generic-extractor-strategy">Extractor Strategy</a> &middot;
  <a href="#notes">Notes</a>
</p>

SmartScrapeV8 is a heuristic-first scraping and extraction project focused on finding real e-commerce deals from messy web content. It fetches a page, cleans the HTML, converts it to readable text, runs domain-aware and generic extractors, scores the results, and only calls Gemini when the heuristic layer is not strong enough.

Supported workflows include single-URL scraping, text-file-only extraction, structured deal output saving, and paced Excel batch processing for multiple URLs.

## What is implemented now

- Step 1: Python project setup and module structure
- Step 2: Scrapling-based scraper that fetches a page and returns cleaned HTML + readable text
- Heuristic-first deals extraction: domain-specific extractors plus a generic multi-language fallback with confidence scoring
- Gemini fallback: only used when heuristic confidence is below the configured threshold
- Excel batch mode: read URLs from `.xlsx` / `.xlsm`, process them in batches, and throttle requests between URLs and batches
- Gemini integration: upload a `.txt` file, extract only deals/coupons, and save output to `.txt`

## Quick start

1. Create and activate a virtual environment.
2. Install dependencies:

   `pip install -r requirements.txt`

3. Install Scrapling browser/runtime support:

   `python scripts/setup_env.py`

4. Set your Gemini API key (PowerShell):

   `$env:GEMINI_API_KEY="your_api_key_here"`

5. Run a scrape:

   `python main.py https://apple.com --save-html output/apple.html --save-text output/apple.txt`

   To also save extracted deals:

   `python main.py https://apple.com --save-html output/apple.html --save-text output/apple.txt --save-deals output/apple_deals.txt`

6. Run deals/coupons extraction from a text file:

   `python main.py --input-text-file sample_input.txt --save-deals output/deals.txt`

7. Run Excel batch scraping with request pacing:

   `python main.py --input-excel-file input/urls.xlsx --excel-url-column url --batch-output-dir output/batch_run --batch-size 5 --delay-between-urls-seconds 3 --delay-between-batches-seconds 20 --cooldown-on-error-seconds 30`

   This creates:

   - `output/batch_run/batch_summary.csv`
   - `output/batch_run/text/`
   - `output/batch_run/deals/`
   - `output/batch_run/html/` if `--batch-save-html` is used

## Generic extractor strategy

The generic extractor is the default fallback for sites that do not have a dedicated parser yet. The current accuracy idea is:

- Use two passes instead of one: scan coupon-like DOM containers first, then scan cleaned text line by line.
- Normalize before matching: strip CTA noise such as `Show Code`, collapse whitespace, decode HTML entities, and split packed lines like `Deal | Code | Expiry`.
- Require at least one strong deal signal: a candidate must contain a real signal such as `% off`, `$ off`, cashback, free shipping, BOGO, or a valid coupon code.
- Treat generic promo words as weak signals only: words like `deal`, `offer`, `sale`, or generic promo labels can boost confidence, but they do not create a candidate by themselves.
- Extract structured fields when possible: `offer_type`, `coupon_code`, `discount_percent`, `discount_amount`, `max_discount_amount`, `cashback_percent`, `min_spend`, `expiry`, and `store`.
- Support multiple languages in the fallback layer: English, Chinese, Korean, Japanese, Spanish, and Portuguese-style coupon text patterns are handled by the generic parser.
- Score and deduplicate at the end: strong multi-signal lines rank higher, while repeated DOM/text matches collapse into one candidate.

This makes the fallback extractor more conservative on noisy content such as support text, generic promo headings, cookie banners, and article text, while still improving recall on real coupon/deal lines.

## Notes

- Gemini extraction uses a strict system prompt that returns only deals/coupons.
- Scrape mode runs regex heuristics first and prints an overall confidence score.
- Gemini fallback in scrape mode is controlled by `--llm-fallback-threshold` and only runs when `GEMINI_API_KEY` is available.
- Excel batch mode auto-detects common URL headers such as `url`, `link`, `website`, and `page_url`. Use `--excel-url-column` if your file uses a different header.
- Batch processing is sequential inside each batch to reduce the chance of rate limiting or IP bans. Use `--batch-size`, `--delay-between-urls-seconds`, `--delay-between-batches-seconds`, and `--cooldown-on-error-seconds` to tune pacing.
- Optional model override: `--gemini-model gemini-2.5-flash`
- If no deals are found, Gemini is instructed to return `NO_DEALS_FOUND`.

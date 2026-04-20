# SmartScrapeV8

MVP foundation for an AI-powered web scraping and question-answering system.

## What is implemented now

- Step 1: Python project setup and module structure
- Step 2: Scrapling-based scraper that fetches a page and returns cleaned HTML + readable text
- Heuristic-first deals extraction: regex-based cashback, discount, coupon code, expiry, and min-spend extraction with confidence scoring
- Gemini fallback: only used when heuristic confidence is below the configured threshold
- Gemini integration: upload a `.txt` file, extract only deals/coupons, and save output to `.txt`

## Quick start

1. Create and activate a virtual environment.
2. Install dependencies:

   pip install -r requirements.txt

3. Install Scrapling browser/runtime support:

   python scripts/setup_env.py

4. Set your Gemini API key (PowerShell):

   $env:GEMINI_API_KEY="your_api_key_here"

5. Run a scrape:

   python main.py https://apple.com --save-html output/apple.html --save-text output/apple.txt

   To also save extracted deals:

   python main.py https://apple.com --save-html output/apple.html --save-text output/apple.txt --save-deals output/apple_deals.txt

6. Run deals/coupons extraction from a text file:

   python main.py --input-text-file sample_input.txt --save-deals output/deals.txt

## Notes

- Gemini extraction uses a strict system prompt that returns only deals/coupons.
- Scrape mode runs regex heuristics first and prints an overall confidence score.
- Gemini fallback in scrape mode is controlled by `--llm-fallback-threshold` and only runs when `GEMINI_API_KEY` is available.
- Optional model override: `--gemini-model gemini-2.5-flash`
- If no deals are found, Gemini is instructed to return `NO_DEALS_FOUND`.

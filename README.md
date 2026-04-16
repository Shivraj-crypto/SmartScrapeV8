# SmartScrapeV8

MVP foundation for an AI-powered web scraping and question-answering system.

## What is implemented now

- Step 1: Python project setup and module structure
- Step 2: Scrapling-based scraper that fetches a page and returns cleaned HTML

## Quick start

1. Create and activate a virtual environment.
2. Install dependencies:

   pip install -r requirements.txt

3. Install Scrapling browser/runtime support:

   python scripts/setup_env.py

4. Run a scrape:

   python main.py https://apple.com

## Notes

- The current implementation focuses on scraping only.
- Processing, chunking, embeddings, retrieval, and final QA will be added next.

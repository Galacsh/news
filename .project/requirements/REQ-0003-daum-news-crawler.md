# REQ-0003: Daum News Scraper & Reliable Major News Curation

Status: captured
Origin: User request (2026-10-25)

## 1. Overview & Objectives
Previously, the daily briefing platform ingested arbitrary RSS feeds and prompted the Gemini LLM to select and curate what it considered "important/major" news. This approach exhibited low reliability, inconsistent headline quality, and arbitrary selection due to the lack of human/editorial curation in raw RSS feeds.

To overcome this, the platform pivots towards scraping portal-curated major news directly from Daum News (`https://news.daum.net`), where editorial and algorithmic headline ranking already exists.

The immediate goal is to implement a fast, reliable Daum News scraper that fetches and outputs the top major news / headlines into structured articles.

---

## 2. Requirements Catalog

### 2.1 Major News Scraper (`src/ingest/daum.py`)
- **R-DAUM-01 (Headline & Major News Extraction)**:
  - Crawl Daum News home (`https://news.daum.net`).
  - Extract headline and major news items (`item_newsheadline2`, `item_newsbasic`, etc.).
  - Extract title, article link (`https://v.daum.net/v/...`), outlet / publisher, summary snippet, relative publish time, and thumbnail image.
- **R-DAUM-02 (Data Normalization)**:
  - Transform parsed news items into standard `Article` instances (`src/ingest/models.py`).
  - Generate stable article IDs based on the Daum article ID (e.g. `daum:20261025224200955`).
  - Set category mapping or `is_major` flag.
- **R-DAUM-03 (CLI Output Utility)**:
  - Provide a runnable CLI command / entrypoint (e.g., `python -m src.ingest.daum` or `src/tools/crawl_daum.py`) to print the current major news clearly in text or JSON format for verification.
- **R-DAUM-04 (Resilience & Zero Heavy Dependencies)**:
  - Use Python standard library (`urllib.request`, `html.parser` / regex) without adding heavy headless browsers or complex third-party scrapers.
  - Set realistic User-Agent headers, timeouts, and graceful error handling on network or parsing failure.
  - Comprehensive unit test coverage with static HTML test fixtures.

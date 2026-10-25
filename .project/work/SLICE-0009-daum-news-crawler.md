# SLICE-0009: Daum News Scraper & Major News Extractor

Status: completed
Source: REQ-0003

## Outcome & Boundaries
- Outcome: A dedicated Daum News crawler/scraper module (`src/ingest/daum.py`) that crawls `https://news.daum.net`, parses human/editorially curated major headlines (`item_newsheadline2`, `item_newsbasic`), normalizes them into standard `Article` model instances, and provides a runnable CLI output to display the latest major news.
- Boundaries:
  - In: `src/ingest/daum.py`, CLI output invocation, comprehensive unit tests in `tests/test_daum.py`, mock HTML test fixtures.
  - Out: Full pipeline replacement / Gemini briefing integration (deferred to subsequent pipeline integration slice).

## Specification
### Acceptance Criteria
- **AC-1 (Headline & Major News Scraping)**:
  - Given `https://news.daum.net` HTML
  - When `DaumNewsScraper.fetch_major_news()` runs
  - Then it extracts headline items containing title, URL (`https://v.daum.net/v/<article_id>`), outlet / publisher, description snippet, relative publication time, and thumbnail image.
- **AC-2 (Model Normalization)**:
  - Given parsed raw items from Daum News
  - When normalized
  - Then each item is converted to an `Article` instance with ID `daum:<article_id>`, cleaned title (decoded entities, trimmed), full target URL, outlet name, and ISO timestamp or current run time.
- **AC-3 (CLI Output)**:
  - Given a CLI invocation (`python -m src.ingest.daum` or `--format text|json`)
  - When executed
  - Then it prints a numbered list of major news headlines (title, outlet, link) or structured JSON to stdout.
- **AC-4 (Resilience & Error Handling)**:
  - Given network errors, timeouts, or HTML structure anomalies
  - When scraping fails or partial elements are missing
  - Then it falls back gracefully without crashing, logging informative errors, and returning parsed articles up to the failure point.

## Tasks & Batches
| Task ID | Batch | Title | Locked Files | Verify Command | Status |
|---|---|---|---|---|---|
| TASK-01 | Batch 1 | Implement Daum News scraper, model normalization, and CLI runner | `src/ingest/daum.py,tests/test_daum.py` | `.venv/bin/pytest tests/test_daum.py` | [x] verified|

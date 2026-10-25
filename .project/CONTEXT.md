# Project Context & Memory

## Charter
Purpose: Automated Daily Korea News Briefing website published via GitHub Pages at zero operating cost, powered by Korean RSS feeds, web scraping, and Google Gemini API free tier.
Scope: Automated end-to-end pipeline (fetch -> filter -> Gemini synthesize -> JSON write -> GitHub Pages deploy) executed daily via GitHub Actions.

## Commands
Dev: `.venv/bin/python -m src.pipeline` (once implemented in SLICE-0003)
Test: `.venv/bin/pytest`
Lint: `.venv/bin/ruff check .` (or standard linter)

## Architecture
Components:
- Ingest: RSS feed parser, encoding handler, and network probe ([`src/ingest/rss.py`](../src/ingest/rss.py), [`src/ingest/sources.py`](../src/ingest/sources.py))
- Filter: Article deduplicator (URL/title similarity), recency validator, and category quota trimmer ([`src/ingest/filter.py`](../src/ingest/filter.py))
- Summarizer: Gemini API free tier client for structured news synthesis ([`src/llm/summarizer.py`](../src/llm/summarizer.py) - SLICE-0002)
- Frontend: Single-page responsive dashboard loading JSON dynamically ([`index.html`](../index.html))
- CI/CD: Scheduled GitHub Actions cron workflow deploying static assets to GitHub Pages (SLICE-0004)

Data Invariants & Partitioning:
- **`data/categories.json`**: Invariant categories configuration (`id`, `name`, `badgeColor`, `aliases`).
- **`data/feeds.json`**: External RSS feed catalog mapped via `categoryId: int`, editable without touching Python code.
- **`data/latest.json`**: Dynamic daily briefing payload (`briefingDate` in ISO format, `topHeadlines`, `articles` mapped via `categoryId: int`).

## Decisions
| ID | Decision | Status | Date |
|---|---|---|---|
| DEC-0001 | Use Python pipeline for fetch, Gemini API summarization, and static HTML rendering | accepted | 2026-10-25 |
| DEC-0002 | Use query timestamp cache-busting (`?_t=${Date.now()}`) and `cache: no-cache` on JSON fetches | accepted | 2026-10-25 |
| DEC-0003 | Separate invariant configuration (`data/categories.json`) from dynamic daily briefing (`data/latest.json`) | accepted | 2026-10-25 |
| DEC-0004 | Extract RSS FeedSource catalog to `data/feeds.json` loaded via `load_feed_sources()` for code-free feed management | accepted | 2026-10-25 |
| DEC-0005 | Use relational foreign key `categoryId: int` across `data/latest.json`, `data/feeds.json`, and UI rather than literal string names | accepted | 2026-10-25 |
| DEC-0006 | Client-side refresh toast notification with smart change detection (distinguish updated vs identical data) | accepted | 2026-10-25 |
| DEC-0007 | Use official google-genai SDK (from google import genai) with structured JSON schema and exponential backoff retry for news synthesis | accepted | 2026-10-25 |
| DEC-0008 | Use continuous 1-based sequential integers for all article IDs (top headlines 1..3, articles 4..N) for unambiguous DOM mapping and clean relational schema | accepted | 2026-10-25 |

# SLICE-0010: Cross-Outlet Consensus, BS4 Body Extraction & Category Deep-Dive Briefing

Status: completed
Source: REQ-0004

## Outcome & Boundaries
- Outcome: End-to-end upgrade delivering (1) legally compliant multi-outlet RSS catalog (`bot: true` outlets only), (2) cross-outlet consensus clustering that prioritizes news reported simultaneously by multiple independent outlets and attaches sibling source links, along with targeted `BeautifulSoup4` full-text body extraction in memory for top selected articles, (3) timeout-safe batched Gemini summarization producing category-specific `deepDive` analytical sections alongside `headline`, `summary`, and `impact`, and (4) a clean main card UI (`index.html`) that navigates on click to a dedicated `detail.html` page showing the category-specific deep dive and an always-expanded related articles list at the bottom.
- Boundaries:
  - In: `data/feeds.json`, `src/ingest/sources.py`, `src/ingest/models.py`, `src/ingest/filter.py`, `src/ingest/body_extractor.py`, `src/llm/prompts.py`, `src/llm/summarizer.py`, `src/pipeline.py`, `.github/workflows/daily-briefing.yml`, `index.html`, `archive.html`, `detail.html`, and corresponding pytest suites.
  - Out: Portal frontpage HTML scraping (`src/ingest/daum.py` remains unused in main pipeline), persistence of raw full-text article bodies to disk.

## Specification
- Acceptance Criteria:
  - Given `data/feeds.json` and `DEFAULT_FALLBACK_FEEDS` in `src/ingest/sources.py`
  - When feed sources are loaded and verified against `data/presslist.json`
  - Then zero outlets marked `"bot": false` (such as 조선일보, 경향신문, 블로터) are present, and all 10 categories contain multiple independent `"bot": true` feeds.
  - Given candidate articles ingested from multiple outlets per category
  - When `ArticleFilterPipeline` processes and clusters articles
  - Then articles covering the same event/topic are grouped by keyword/token overlap, clusters are ranked by distinct outlet count (cross-outlet consensus) and recency, sibling source links are preserved on the representative `Article`, and `ArticleBodyExtractor` enriches selected top articles with clean `BeautifulSoup4` body text in memory (truncated to ~900 chars) with graceful fallback on HTTP/parse errors.
  - Given enriched candidate articles across up to 10 categories
  - When `NewsSummarizer.summarize_articles()` runs
  - Then it executes Gemini calls in category batches (e.g., 3–4 categories per batch) to prevent timeouts/truncation, isolates per-batch fallback, and outputs `headline`, `summary` (핵심), `impact` (파급), `links` (including clustered sibling links), and a category-tailored `deepDive` object (`lensTitle` and 2 `sections` in 해요체) matching the 10 category lenses.
  - Given `index.html` and `detail.html`
  - When a user views the main briefing and clicks a card
  - Then main cards display only the category badge, `headline`, `summary`, and `impact` (without in-card link toggle buttons) and navigate to `detail.html?id=<id>` (preserving `?archive=<archive>` when in archive mode), where `detail.html` renders the summary, impact, `deepDive` sections, and an always-visible (non-collapsible) list of source `links` at the bottom.
- Dependencies: SLICE-0001, SLICE-0002, SLICE-0003, SLICE-0004, SLICE-0008

## Tasks & Batches
| Task ID | Batch | Title | Locked Files | Verify Command | Status |
|---|---|---|---|---|---|
| TASK-01 | Batch 1 | Reconfigure feed catalog with legally compliant multi-outlet feeds across 10 categories | `data/feeds.json,src/ingest/sources.py,tests/test_rss.py` | `.venv/bin/pytest tests/test_rss.py tests/test_feed_checker.py` | [x] verified|
| TASK-02 | Batch 1 | Implement cross-outlet consensus clustering and BeautifulSoup4 article body extractor | `src/ingest/models.py,src/ingest/filter.py,src/ingest/body_extractor.py,tests/test_filter.py` | `.venv/bin/pytest tests/test_filter.py` | [x] verified|
| TASK-03 | Batch 1 | Add 10 category-specific deepDive lenses and batched Gemini summarization | `src/llm/prompts.py,src/llm/summarizer.py,tests/test_summarizer.py` | `.venv/bin/pytest tests/test_summarizer.py` | [x] verified|
| TASK-04 | Batch 1 | Update main cards for click navigation and implement detail.html with deepDive and expanded links | `index.html,archive.html,detail.html,tests/test_archive_ui.py` | `.venv/bin/pytest tests/test_archive_ui.py` | [x] verified|
| TASK-05 | Batch 2 | Integrate body extraction and batched summarization in pipeline and add workflow timeout safety | `src/pipeline.py,.github/workflows/daily-briefing.yml,tests/test_pipeline.py,tests/test_workflow.py` | `.venv/bin/pytest` | [x] verified|

## Verification Evidence
- TASK-01: `.venv/bin/pytest tests/test_rss.py tests/test_feed_checker.py` (51 passed)
- TASK-02: `.venv/bin/pytest tests/test_filter.py` (38 passed, 1 skipped)
- TASK-03: `.venv/bin/pytest tests/test_summarizer.py` (17 passed)
- TASK-04: `.venv/bin/pytest tests/test_archive_ui.py` (16 passed)
- TASK-05: `.venv/bin/pytest` (215 passed, 1 skipped in 1.13s)

## Review Findings
PASS. Audited by reviewer subagent.
- Acceptance Criteria verified: Zero `bot: false` feeds in active/fallback catalogs; cross-outlet consensus clustering ranking multi-outlet stories over single-outlet clickbait; in-memory transient BeautifulSoup4 article body enrichment; 10 category-tailored `deepDive` lenses; batched category synthesis preventing timeouts; clean clickable main cards navigating to `detail.html`; always-expanded related links at the bottom of the detail page; `timeout-minutes: 15` in GitHub Actions workflow.
- Universal Coding Standards: Compliant with `coding-standards.md` (deep modules, boundary validation for URL schemes, defensive link pools, transient in-memory body handling without leaking to disk, full test suite passes).

# SLICE-0011: Rich Multi-Outlet Consensus Clustering & Exact 3-Article Category Quota

Status: completed
Source: REQ-0005

## Outcome & Boundaries
- Outcome: (1) Expand active `bot: true` feeds to 50+ by fixing DongA international and adding Hankyoreh, SBS, MBN, and NocutNews, (2) reform `deduplicate_articles` and `cluster_articles_by_topic` in `src/ingest/filter.py` so cross-outlet articles covering the same topic are clustered via title token overlap (>=2 common keywords or min overlap >= 0.30) rather than discarded, populating representative articles with 2 to 5 distinct outlet source links, and (3) strictly enforce exactly 3 articles per category in `src/llm/prompts.py`, `src/llm/summarizer.py`, and `src/pipeline.py`.
- Boundaries:
  - In: `data/feeds.json`, `src/ingest/sources.py`, `src/ingest/filter.py`, `src/llm/prompts.py`, `src/llm/summarizer.py`, `src/pipeline.py`, and test suites.
  - Out: Changes to HTML UI structure.

## Specification
- Acceptance Criteria:
  - Given `data/feeds.json` and `src/ingest/sources.py`
  - When feeds are loaded
  - Then DongA international points to `international.xml` (yielding active articles), and verified feeds for Hankyoreh, SBS, MBN, and NocutNews are included, totaling >45 active feeds with zero `bot: false` outlets.
  - Given articles ingested across multiple outlets
  - When processed through `ArticleFilterPipeline`
  - Then articles on the same topic from different outlets are preserved, clustered using token overlap, and the representative article has `related_links` with multiple distinct outlets attached.
  - Given candidate articles for each active category
  - When `summarize_articles()` executes (or falls back)
  - Then each category present produces EXACTLY 3 distinct articles.

## Tasks & Batches
| Task ID | Batch | Title | Locked Files | Verify Command | Status |
|---|---|---|---|---|---|
| TASK-01 | Batch 1 | Repair DongA international feed and add Hankyoreh, SBS, MBN, and NocutNews feeds | `data/feeds.json,src/ingest/sources.py,tests/test_rss.py` | `.venv/bin/pytest tests/test_rss.py tests/test_feed_checker.py` | [x] verified|
| TASK-02 | Batch 1 | Reform deduplication and enhance consensus clustering with title token overlap | `src/ingest/filter.py,tests/test_filter.py` | `.venv/bin/pytest tests/test_filter.py` | [x] verified|
| TASK-03 | Batch 1 | Enforce exact 3 articles per category in Gemini prompts and fallback normalizer | `src/llm/prompts.py,src/llm/summarizer.py,tests/test_summarizer.py` | `.venv/bin/pytest tests/test_summarizer.py` | [x] verified|
| TASK-04 | Batch 2 | Integrate candidate quota in pipeline and verify end-to-end multi-link output | `src/pipeline.py,tests/test_pipeline.py` | `.venv/bin/pytest` | [x] verified|

## Verification Evidence
- TASK-01: `.venv/bin/pytest tests/test_rss.py tests/test_feed_checker.py` (51 passed)
- TASK-02: `.venv/bin/pytest tests/test_filter.py` (50 passed, 1 skipped)
- TASK-03: `.venv/bin/pytest tests/test_summarizer.py` (20 passed)
- TASK-04: `.venv/bin/pytest` (226 passed, 1 skipped in 1.13s)

## Review Findings
PASS. Audited by reviewer subagent.
- Acceptance Criteria verified: DongA international feed repaired (`international.xml`), verified feeds for Hankyoreh, SBS, MBN, and NocutNews added (48 active feeds, zero `bot: false` outlets); `deduplicate_articles` preserves cross-outlet articles for clustering; `are_articles_same_topic` clusters same-topic articles and attaches distinct outlet sibling links; exact 3-article category quota enforced in prompts, summarizer, and pipeline orchestrator.
- Universal Coding Standards: Compliant with `coding-standards.md`. Full regression suite passes cleanly (226 passed, 1 skipped).

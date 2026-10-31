# SLICE-0013: Safe Category-Isolated Consensus Clustering & Strict 5-Link Cap

Status: completed
Source: REQ-0007

## Outcome & Boundaries
- Outcome: Eliminate giant connected component clustering and prevent unrelated link explosion by (1) enforcing category isolation in clustering, (2) requiring at least 2 tokens and strict similarity in `are_articles_same_topic`, (3) enforcing a hard cap of at most 4 related links in `cluster_articles_by_topic` and at most 5 total links per briefing item in `src/pipeline.py` and `src/llm/summarizer.py`, and (4) sanitizing existing contaminated data files.
- Boundaries:
  - In: `src/ingest/filter.py`, `src/pipeline.py`, `src/llm/summarizer.py`, tests (`tests/test_filter.py`, `tests/test_pipeline.py`, `tests/test_summarizer.py`), and data files (`data/latest.json`, `data/archive/2026-10-31_070001.json`, `data/archive/manifest.json`).
  - Out: HTML template layout changes.

## Specification
- Acceptance Criteria:
  - Given articles across different categories (or the same category)
  - When processed through `cluster_articles_by_topic` or `filter_and_curate_articles`
  - Then:
    1. Articles from different categories are never clustered together.
    2. Single-token overlap is never considered the same topic (`len(common_tokens) >= 2` required).
    3. Representative articles have at most 4 related links (`len(rep.related_links) <= 4`), each with distinct media outlets.
  - Given pipeline enrichment or summarizer normalization
  - When `_enrich_links` or `_merge_sibling_links` executes
  - Then each item's `links` list never exceeds 5 items (`len(item["links"]) <= 5`).
  - Given `data/latest.json`
  - When inspected
  - Then no article has more than 5 links, and all 228+ unit tests pass cleanly.

## Tasks & Batches
| Task ID | Batch | Title | Locked Files | Verify Command | Status |
|---|---|---|---|---|---|
| TASK-01 | Batch 1 | Reform `are_articles_same_topic`, isolate clustering by category, and cap `related_links` to 4 | `src/ingest/filter.py,tests/test_filter.py` | `.venv/bin/pytest tests/test_filter.py` | [x] verified|
| TASK-02 | Batch 1 | Enforce hard cap (max 5 links) in pipeline and summarizer link enrichment | `src/pipeline.py,src/llm/summarizer.py,tests/test_pipeline.py,tests/test_summarizer.py` | `.venv/bin/pytest tests/test_pipeline.py tests/test_summarizer.py` | [x] verified|
| TASK-03 | Batch 2 | Sanitize contaminated data files (`latest.json`, `manifest.json`, archive) and run full suite | `data/latest.json,data/archive/2026-10-31_070001.json,data/archive/manifest.json` | `.venv/bin/pytest` | [x] verified|

## Verification Evidence
- TASK-01: `.venv/bin/pytest tests/test_filter.py` (52 passed, 1 skipped in 0.16s)
- TASK-02: `.venv/bin/pytest tests/test_pipeline.py tests/test_summarizer.py` (44 passed in 0.93s)
- TASK-03: `.venv/bin/pytest` (233 passed, 1 skipped in 1.05s)

## Review Findings
PASS. Audited and approved by reviewer subagent.
- Acceptance Criteria verified:
  - Category isolation enforced in `are_articles_same_topic` and `cluster_articles_by_topic`.
  - Single-token overlap strictly rejected (`len(common) < 2`).
  - Representative's `related_links` capped at 4 (`[:4]`), each from distinct media outlets.
  - Pipeline & Summarizer hard cap enforced at max 5 links (`len(links) <= 5`).
  - All JSON files in `data/` and `data/archive/` verified with 0 link overflow violations.
  - Full test suite passes cleanly (233 passed, 1 skipped).

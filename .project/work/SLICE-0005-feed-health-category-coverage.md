# SLICE-0005: Feed Health Checker & Category Coverage Enhancement

Status: proposed
Source: REQ-0002

## Outcome & Boundaries
- Outcome: Automated RSS feed health-checker utility that validates candidate feeds from `rss-unverified.json`, enriches `data/feeds.json` with active verified feeds for deficient categories (AI·빅테크, IT·통신, 문화, 라이프스타일 등), and introduces adaptive lookback fallback so every category reliably retains at least 2 to 3 candidate articles daily.
- Boundaries:
  - In: `src/tools/feed_checker.py` (or `src/ingest/health.py`), updated `data/feeds.json`, adaptive lookback logic in `src/ingest/filter.py` or `src/pipeline.py`, unit tests.
  - Out: Telemetry dashboard visualization (SLICE-0006).

## Specification
- Acceptance Criteria:
  - Given the candidate feed catalog `rss-unverified.json`
  - When the health-check runner executes
  - Then it validates HTTP 200, latency <5s, valid XML feed items, and recent publish dates, producing a curated recommendation list.
  - Given active categories in `data/categories.json`
  - When the pipeline runs against the enriched `data/feeds.json`
  - Then every category reliably yields at least 2 candidate articles without empty-category anomalies.
- Dependencies: SLICE-0003

## Tasks & Batches
| Task ID | Batch | Title | Locked Files | Verify Command | Status |
|---|---|---|---|---|---|
| TASK-01 | Batch 1 | Implement automated RSS feed health checker utility | `src/tools/feed_checker.py,tests/test_feed_checker.py` | `.venv/bin/pytest tests/test_feed_checker.py` | `[ ] pending` |
| TASK-02 | Batch 2 | Enrich deficient categories in feeds catalog and implement adaptive category lookback | `data/feeds.json,src/ingest/filter.py,tests/test_filter.py` | `.venv/bin/pytest tests/test_filter.py` | `[ ] pending` |

## Verification Evidence
NOT RUN

## Review Findings
NOT RUN

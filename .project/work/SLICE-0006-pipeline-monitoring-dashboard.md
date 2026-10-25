# SLICE-0006: Pipeline Telemetry & Collection Reporting Dashboard

Status: proposed
Source: REQ-0002

## Outcome & Boundaries
- Outcome: Pipeline execution telemetry logging (`data/telemetry/latest.json`) and a dedicated static monitoring dashboard (`monitoring.html`) that visualizes ingestion funnel stats, feed response latencies, error logs, and category retention health.
- Boundaries:
  - In: Telemetry collection in `src/pipeline.py`, telemetry output schema, `monitoring.html` dashboard, unit tests.
  - Out: Notice center (SLICE-0007).

## Specification
- Acceptance Criteria:
  - Given an execution of `DailyBriefingPipeline`
  - When the pipeline completes or encounters errors
  - Then it records structured telemetry metrics (`feeds_attempted`, `feeds_failed`, `raw_articles_count`, `filtered_count`, `gemini_latency_ms`, `category_breakdown`) to `data/telemetry/latest.json`.
  - Given `monitoring.html` loaded in the browser
  - When viewing the dashboard
  - Then it renders collection health badges, ingestion funnel statistics, and per-feed status tables.
- Dependencies: SLICE-0003

## Tasks & Batches
| Task ID | Batch | Title | Locked Files | Verify Command | Status |
|---|---|---|---|---|---|
| TASK-01 | Batch 1 | Implement pipeline telemetry logging and serialization | `src/pipeline.py,tests/test_pipeline.py` | `.venv/bin/pytest tests/test_pipeline.py` | `[ ] pending` |
| TASK-02 | Batch 2 | Build monitoring dashboard page and metrics visualizer | `monitoring.html,tests/test_monitoring.py` | `.venv/bin/pytest tests/test_monitoring.py` | `[ ] pending` |

## Verification Evidence
NOT RUN

## Review Findings
NOT RUN

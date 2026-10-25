# SLICE-0003: Daily News Pipeline Orchestration

Status: proposed
Source: REQ-0001

## Outcome & Boundaries
- Outcome: Single command orchestration script that links ingestion, Gemini synthesis, and updates `data/latest.json` and historical `data/YYYY-MM-DD.json`, fully validating the schema for `index.html`.
- Boundaries:
  - In: Pipeline orchestration (`python -m src.pipeline`), date formatting, schema validation, disk persistence of daily JSON.
  - Out: Cloud deployment / CI/CD (handled in SLICE-0004).

## Specification
- Acceptance Criteria:
  - Given active feeds and Gemini API key
  - When running the pipeline command
  - Then `data/latest.json` and `data/YYYY-MM-DD.json` are generated matching `index.html` schema without manual intervention.
- Dependencies: SLICE-0001, SLICE-0002

## Tasks & Batches
| Task ID | Batch | Title | Locked Files | Verify Command | Status |
|---|---|---|---|---|---|
| TASK-01 | Batch 1 | Assemble end-to-end pipeline runner | `src/pipeline.py` | `pytest tests/test_pipeline.py` | `[ ] pending` |

## Verification Evidence
NOT RUN

## Review Findings
NOT RUN

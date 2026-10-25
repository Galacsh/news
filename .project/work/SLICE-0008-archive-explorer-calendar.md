# SLICE-0008: Historical Briefing Archive Explorer & Calendar UI

Status: proposed
Source: REQ-0002

## Outcome & Boundaries
- Outcome: Automated archive manifest index (`data/archive/manifest.json`) and a dedicated historical briefing exploration page (`archive.html`) featuring an interactive calendar/date picker, past briefing preview cards, and seamless navigation.
- Boundaries:
  - In: Archive manifest generator in `src/pipeline.py`, `archive.html` explorer page, calendar/date picker component, unit tests.
  - Out: Telemetry dashboard (SLICE-0006).

## Specification
- Acceptance Criteria:
  - Given existing archive files in `data/archive/YYYY-MM-DD.json`
  - When the pipeline executes
  - Then it generates and updates `data/archive/manifest.json` indexing available briefing dates with preview headlines.
  - Given `archive.html` opened in the browser
  - When selecting an available date on the calendar or preview grid
  - Then it displays the briefing preview and links directly to `index.html?date=YYYY-MM-DD`.
- Dependencies: SLICE-0003

## Tasks & Batches
| Task ID | Batch | Title | Locked Files | Verify Command | Status |
|---|---|---|---|---|---|
| TASK-01 | Batch 1 | Generate archive manifest index in briefing pipeline | `src/pipeline.py,tests/test_pipeline.py` | `.venv/bin/pytest tests/test_pipeline.py` | `[ ] pending` |
| TASK-02 | Batch 2 | Implement archive explorer page with calendar picker and preview grid | `archive.html,tests/test_archive_ui.py` | `.venv/bin/pytest tests/test_archive_ui.py` | `[ ] pending` |

## Verification Evidence
NOT RUN

## Review Findings
NOT RUN

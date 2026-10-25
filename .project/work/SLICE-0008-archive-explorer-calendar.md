# SLICE-0008: Historical Briefing Archive Explorer & Calendar UI

Status: complete
Source: REQ-0002

## Outcome & Boundaries
- Outcome: Automated timestamped archive generation (`data/archive/YYYY-MM-DD_HHMMSS.json`), manifest index (`data/archive/manifest.json`) supporting intra-day multiple runs with backward compatibility for existing archives (`YYYY-MM-DD.json`), and a dedicated historical briefing exploration page (`archive.html`) featuring an interactive calendar/date picker, intra-day briefing preview cards, and seamless navigation.
- Boundaries:
  - In: Timestamped archive filenames and manifest generator in `src/pipeline.py`, `archive.html` explorer page with intra-day run selector, calendar/date picker component, navigation integration in `index.html`, unit tests.
  - Out: Telemetry dashboard (SLICE-0006).

## Specification
- Acceptance Criteria:
  - Given the pipeline executes multiple times on the same date (or with timestamped dates)
  - When writing archive outputs
  - Then it saves timestamped archive files (`data/archive/YYYY-MM-DD_HHMMSS.json`) while maintaining day-level access (`data/archive/YYYY-MM-DD.json`), preserving multiple runs without overwriting.
  - Given existing archive files in `data/archive/` (both `YYYY-MM-DD_HHMMSS.json` and legacy `YYYY-MM-DD.json`)
  - When the pipeline generates `data/archive/manifest.json`
  - Then it indexes all available briefing runs sorted in reverse chronological order with date, time, briefingDate, topHeadlines, and totalArticles.
  - Given `archive.html` opened in the browser
  - When selecting an available date on the calendar or preview grid
  - Then it displays the briefing runs for that date (supporting multiple runs per day) and links directly to `index.html?archive=<filename>` (or `?date=<filename>`).
- Dependencies: SLICE-0003

## Tasks & Batches
| Task ID | Batch | Title | Locked Files | Verify Command | Status |
|---|---|---|---|---|---|
| TASK-01 | Batch 1 | Generate timestamped archive runs and manifest index in briefing pipeline | `src/pipeline.py,tests/test_pipeline.py` | `.venv/bin/pytest tests/test_pipeline.py` | [x] verified|
| TASK-02 | Batch 2 | Implement archive explorer page with calendar picker, intra-day run selector, and preview grid | `archive.html,index.html,tests/test_archive_ui.py` | `.venv/bin/pytest tests/test_archive_ui.py` | [x] verified |

## Verification Evidence
- TASK-01: `.venv/bin/pytest tests/test_pipeline.py` (16 passed)
- TASK-02: `.venv/bin/pytest tests/test_archive_ui.py` (10 passed)

## Review Findings
PASS. Audited by reviewer subagent.
- Acceptance Criteria verified: Timestamped archive writing (`YYYY-MM-DD_HHMMSS.json`), day-level compatibility (`YYYY-MM-DD.json`), manifest generator (`data/archive/manifest.json`), calendar explorer UI (`archive.html`), and query param integration (`index.html?archive=<filename>`) all verified.
- Universal Coding Standards: Compliant with `coding-standards.md` (deep module `generate_archive_manifest`, boundary validation with regex and json parsing, XSS escaping in DOM manipulation, single source of truth for archives).
- Test Integrity: 26/26 tests passed (`tests/test_pipeline.py`, `tests/test_archive_ui.py`) and full regression suite passed (167 passed, 1 skipped).


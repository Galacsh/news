# SLICE-0014: Remove Article Count Badge from Related Articles Section in Detail Page

Status: completed
Source: REQ-0008

## Outcome & Boundaries
- Outcome: Remove the "총 N건" badge (`#articlesCountBadge`) from the "언론사별 관련 보도" section header in `detail.html`, clean up associated script logic, and update unit test assertions in `tests/test_archive_ui.py`.
- Boundaries:
  - In: `detail.html`, `tests/test_archive_ui.py`.
  - Out: Backend python pipeline, feed ingestion, other HTML pages.

## Specification
- Acceptance Criteria:
  - Given `detail.html`
  - When rendered
  - Then the "언론사별 관련 보도" header does not display the "총 N건" badge.
  - Given `tests/test_archive_ui.py`
  - When executed
  - Then all unit tests pass cleanly.

## Tasks & Batches
| Task ID | Batch | Title | Locked Files | Verify Command | Status |
|---|---|---|---|---|---|
| TASK-01 | Batch 1 | Remove `#articlesCountBadge` from `detail.html` and update `tests/test_archive_ui.py` | `detail.html,tests/test_archive_ui.py` | `.venv/bin/pytest tests/test_archive_ui.py` | [x] verified|

## Verification Evidence
- TASK-01: `.venv/bin/pytest tests/test_archive_ui.py` (17 passed in 0.01s; TASK-01 PASS in 0.29s)
- Full regression suite: `.venv/bin/pytest` (233 passed, 1 skipped in 1.16s)

## Review Findings
PASS.
- Acceptance Criteria verified:
  - Removed `#articlesCountBadge` and associated text logic ("총 N건") from "언론사별 관련 보도" header in `detail.html`.
  - Section layout cleanly styled without empty badge spacing.
  - Test suite updated in `tests/test_archive_ui.py` and passes cleanly without regressions.

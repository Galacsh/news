# SLICE-0016: Remove Article Count Badge from Category Selection Area in Main Page

Status: completed
Source: REQ-0010

## Outcome & Boundaries
- Outcome: Remove the article count badge (`#articleCountBadge`, "N건") from the sticky category navigation header in `index.html`, clean up associated script logic, and verify that all UI tests and regressions pass cleanly.
- Boundaries:
  - In: `index.html`, `tests/test_archive_ui.py`.
  - Out: Backend python pipeline, feed ingestion, other HTML pages.

## Specification
- Acceptance Criteria:
  - Given `index.html`
  - When category bar is rendered
  - Then `#articleCountBadge` is not present, and the category title displays cleanly without count badge.
  - Given the full test suite
  - When executed
  - Then all tests pass.

## Tasks & Batches
| Task ID | Batch | Title | Locked Files | Verify Command | Status |
|---|---|---|---|---|---|
| TASK-01 | Batch 1 | Remove `#articleCountBadge` from `index.html` markup and script | `index.html` | `.venv/bin/pytest tests/test_archive_ui.py` | [x] verified|

## Verification Evidence
- TASK-01: `.venv/bin/pytest tests/test_archive_ui.py` (17 passed in 0.04s; TASK-01 PASS in 0.18s)
- Full regression suite: `.venv/bin/pytest` (233 passed, 1 skipped in 1.07s)

## Review Findings
PASS.
- Acceptance Criteria verified:
  - Removed `#articleCountBadge` markup and text logic ("N건") from sticky category header in `index.html`.
  - Category header displays cleanly with icon and title.
  - All unit and regression tests pass cleanly with zero regressions.

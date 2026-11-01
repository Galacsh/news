# SLICE-0015: Detail Page Deep-Dive Section UI Copy Refinement & Tag Removal

Status: completed
Source: REQ-0009

## Outcome & Boundaries
- Outcome: Update `detail.html` deep-dive header title to "심층 분석", subtitle to "분야별로 심층적으로 분석했어요.", remove the analytical lens badge tag (`#lensBadgeContainer`), clean up script logic, and update unit test assertions in `tests/test_archive_ui.py`.
- Boundaries:
  - In: `detail.html`, `tests/test_archive_ui.py`.
  - Out: Backend python pipeline, summarizer, other HTML files.

## Specification
- Acceptance Criteria:
  - Given `detail.html`
  - When deep-dive section is viewed
  - Then:
    1. Title is "심층 분석".
    2. Subtitle is "분야별로 심층적으로 분석했어요.".
    3. Analytical lens tag (`#lensTitleBadge`) is removed.
  - Given `tests/test_archive_ui.py`
  - When executed
  - Then all tests pass.

## Tasks & Batches
| Task ID | Batch | Title | Locked Files | Verify Command | Status |
|---|---|---|---|---|---|
| TASK-01 | Batch 1 | Refine deep-dive header copy, remove lens tag from `detail.html`, and update `tests/test_archive_ui.py` | `detail.html,tests/test_archive_ui.py` | `.venv/bin/pytest tests/test_archive_ui.py` | [x] verified|

## Verification Evidence
- TASK-01: `.venv/bin/pytest tests/test_archive_ui.py` (17 passed in 0.04s; TASK-01 PASS in 0.14s)
- Full regression suite: `.venv/bin/pytest` (233 passed, 1 skipped in 1.13s)

## Review Findings
PASS.
- Acceptance Criteria verified:
  - Deep-dive section title updated to "심층 분석".
  - Subtitle updated to "분야별로 심층적으로 분석했어요.".
  - Analytical lens badge tag (`#lensBadgeContainer`) completely removed from markup and script.
  - Regression tests in `tests/test_archive_ui.py` updated and pass cleanly with zero regressions.

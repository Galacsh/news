# SLICE-0012: Mobile Header & Non-Content Responsive UI Polish

Status: completed
Source: REQ-0006

## Outcome & Boundaries
- Outcome: Eliminate awkward line wrapping and layout breakage on mobile viewports (<= 375px) across all frontend pages (`index.html`, `detail.html`, `archive.html`, `notices.html`, `monitoring.html`) by applying `break-keep`, responsive font scaling, `whitespace-nowrap`, and `shrink-0` to headers, buttons, navigation links, and badges, with 100% test passing rate.
- Boundaries:
  - In: `index.html`, `detail.html`, `archive.html`, `notices.html`, `monitoring.html`, and UI DOM unit tests (`tests/test_archive_ui.py`, `tests/test_notices.py`, `tests/test_monitoring.py`).
  - Out: Backend python ingestion, scraping, Gemini prompts, and pipeline logic.

## Specification
- Acceptance Criteria:
  - Given any of `index.html`, `detail.html`, `archive.html`, `notices.html`, or `monitoring.html` viewed on mobile viewports (<= 375px)
  - When header titles, back links, action buttons, category tabs, or banners are rendered
  - Then:
    1. Header titles do not awkwardly break words (`break-keep`, responsive font scaling).
    2. Back buttons and action links remain single-line (`whitespace-nowrap`, `shrink-0`).
    3. Action button clusters remain inline and accessible.
    4. Badges and banner actions wrap only at intentional element boundaries without broken text.
  - Given UI test suites (`tests/test_archive_ui.py`, `tests/test_notices.py`, `tests/test_monitoring.py`)
  - When executed with pytest
  - Then all existing assertions and new responsive checks pass cleanly.

## Tasks & Batches
| Task ID | Batch | Title | Locked Files | Verify Command | Status |
|---|---|---|---|---|---|
| TASK-01 | Batch 1 | Polish mobile headers, banners, and card actions in `index.html` and `detail.html` | `index.html,detail.html` | `.venv/bin/pytest tests/test_archive_ui.py` | [x] verified|
| TASK-02 | Batch 1 | Polish mobile headers, navigation, and badges in `archive.html`, `notices.html`, and `monitoring.html` | `archive.html,notices.html,monitoring.html` | `.venv/bin/pytest tests/test_archive_ui.py tests/test_notices.py tests/test_monitoring.py` | [x] verified|
| TASK-03 | Batch 2 | Update and enhance UI DOM regression tests for mobile responsive classes | `tests/test_archive_ui.py,tests/test_notices.py,tests/test_monitoring.py` | `.venv/bin/pytest` | [x] verified|

## Verification Evidence
- TASK-01: `.venv/bin/pytest tests/test_archive_ui.py` (16 passed in 0.05s)
- TASK-02: `.venv/bin/pytest tests/test_archive_ui.py tests/test_notices.py tests/test_monitoring.py` (40 passed in 0.02s)
- TASK-03: `.venv/bin/pytest` (227 passed, 1 skipped in 1.09s)

## Review Findings
PASS. Audited by reviewer subagent.
- Acceptance Criteria verified:
  - Mobile header titles (<= 375px): `break-keep` and responsive font scaling (`text-lg sm:text-2xl` / `text-base sm:text-xl`) correctly prevent awkward CJK word breaks across `index.html`, `detail.html`, `archive.html`, `notices.html`, and `monitoring.html`.
  - Back buttons and action links: Configured with `whitespace-nowrap` and `shrink-0` to remain single-line and uncompressed. Adaptive mobile labels (e.g. `← 메인` on mobile, `← 뉴스 브리핑` on desktop) ensure clean fitting without overflow.
  - Action button clusters: `shrink-0` and `aspect-square` maintain consistent touch-target dimensions and prevent squishing in header action bars.
  - Badges and banners: Dynamic and static badges (`#overallStatusBadge`, `#categoryBadge`, card badges) apply `whitespace-nowrap` and `shrink-0`. Banner actions wrap only at intentional element boundaries.
  - Test adequacy: Comprehensive DOM assertions added across `tests/test_archive_ui.py`, `tests/test_notices.py`, and `tests/test_monitoring.py`.
- Universal Coding Standards: Compliant with `coding-standards.md`. Full test suite passes cleanly (227 passed, 1 skipped).

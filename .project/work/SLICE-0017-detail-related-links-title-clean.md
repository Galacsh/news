# SLICE-0017: Detail Related Links Title Clean & Sanitization

Status: completed
Source: REQ-0011

## Outcome & Boundaries
- Outcome: In `detail.html`, sanitize related article link titles by stripping redundant leading bracketed prefixes (e.g. `[한겨레]`, `[한국경제 - 라이프]`, `[속보]`) so titles render cleanly beside the outlet badge (`${outlet}`). Prioritize URL hostname in `getOutletName` to avoid non-outlet tags (like `속보`) masquerading as outlet names. Add tests in `tests/test_archive_ui.py` and verify all tests pass.
- Boundaries:
  - In: `detail.html`, `tests/test_archive_ui.py`.
  - Out: Backend python pipeline, feed ingestion, other HTML pages.

## Specification
- Acceptance Criteria:
  - Given `detail.html`
  - When related article links are rendered in `#relatedLinksList`
  - Then leading bracketed prefixes matching `^(?:\[[^\]]+\]\s*)+` are stripped from the displayed title.
  - And the outlet badge (`<span class="...">${outlet}</span>`) remains visible and correctly identifies the outlet.
  - Given `tests/test_archive_ui.py`
  - When executed
  - Then assertions verify the title sanitization logic in `detail.html`, and all test suites pass.

## Tasks & Batches
| Task ID | Batch | Title | Locked Files | Verify Command | Status |
|---|---|---|---|---|---|
| TASK-01 | Batch 1 | Strip leading bracketed prefixes in `detail.html` and update `getOutletName` | `detail.html` | `.venv/bin/pytest tests/test_archive_ui.py` | [x] verified|
| TASK-02 | Batch 1 | Add unit/DOM assertions in `tests/test_archive_ui.py` | `tests/test_archive_ui.py` | `.venv/bin/pytest tests/test_archive_ui.py` | [x] verified|

## Verification Evidence
- TASK-01: `.venv/bin/pytest tests/test_archive_ui.py` (17 passed in 0.02s; TASK-01 PASS in 0.14s)
- TASK-02: `.venv/bin/pytest tests/test_archive_ui.py` (18 passed in 0.04s; TASK-02 PASS in 0.14s)
- Full regression suite: `.venv/bin/pytest` (234 passed, 1 skipped in 1.27s)

## Review Findings
PASS.
- Acceptance Criteria verified:
  - In `detail.html`, leading bracketed prefixes matching `^(?:\[[^\]]+\]\s*)+` are stripped cleanly from related article link titles.
  - In `detail.html`, `getOutletName` prioritizes URL host matching over title bracket tags and ignores editorial terms (e.g. `속보`, `단독`), correctly identifying outlets like 매일경제 for `mk.co.kr`.
  - Outlet badge tag (`<span class="...">${outlet}</span>`) remains cleanly visible beside the sanitized article title.
  - All unit, integration, and UI tests pass with zero regressions.

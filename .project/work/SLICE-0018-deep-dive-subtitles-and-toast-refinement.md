# SLICE-0018: Deep Dive Subtitles & Toast Copy Refinement

Status: completed
Source: REQ-0012

## Outcome & Boundaries
- Outcome: Shorten the toast notification copy in `index.html` to `"새로운 변경 사항이 없습니다."`, simplify section subheadings across all 10 categories in `src/llm/prompts.py`, implement deep dive section label normalization in `detail.html`, update test suites, and verify all tests pass.
- Boundaries:
  - In: `index.html`, `detail.html`, `src/llm/prompts.py`, `tests/test_archive_ui.py`, `tests/test_summarizer.py`.
  - Out: RSS ingestion, clustering algorithms.

## Specification
- Acceptance Criteria:
  - Given `index.html`
  - When the user checks for updates and no new updates are available
  - Then the toast notification displays `"새로운 변경 사항이 없습니다."`.
  - Given `detail.html`
  - When deep-dive sections are rendered
  - Then legacy section titles (e.g. `"마케팅 빼고 진짜 바뀐 기술 본질"`, `"개발자·실무·생태계 판도 변화"`) are normalized to concise terms (e.g. `"본질"`, `"판도 변화"`).
  - Given `src/llm/prompts.py`
  - When `CATEGORY_LENS_DEFINITIONS` are loaded
  - Then all 10 categories define concise, punchy section subheadings.
  - Given the full test suite
  - When executed
  - Then all tests pass with zero regressions.

## Tasks & Batches
| Task ID | Batch | Title | Locked Files | Verify Command | Status |
|---|---|---|---|---|---|
| TASK-01 | Batch 1 | Update toast copy in `index.html` and section subheadings in `detail.html` and `src/llm/prompts.py` | `index.html`, `detail.html`, `src/llm/prompts.py` | `.venv/bin/pytest tests/test_archive_ui.py tests/test_summarizer.py` | [x] verified|
| TASK-02 | Batch 1 | Update UI and summarizer tests | `tests/test_archive_ui.py`, `tests/test_summarizer.py` | `.venv/bin/pytest` | [x] verified|

## Verification Evidence
- TASK-01: `.venv/bin/pytest tests/test_archive_ui.py tests/test_summarizer.py` (40 passed in 0.17s; TASK-01 PASS in 0.32s)
- TASK-02: `.venv/bin/pytest` (236 passed, 1 skipped in 1.04s; TASK-02 PASS in 1.22s)
- Full regression suite: `.venv/bin/pytest` (236 passed, 1 skipped in 1.04s)

## Review Findings
PASS.
- Acceptance Criteria verified:
  - In `index.html`, the refresh toast notification text was cleanly shortened from `"새로운 변경 사항이 없습니다. (최신 상태 유지 중)"` to `"새로운 변경 사항이 없습니다."`.
  - In `detail.html`, `formatDeepDiveLabel` normalizes legacy section headings (e.g. `"마케팅 빼고 진짜 바뀐 기술 본질"` ➔ `"본질"`, `"개발자·실무·생태계 판도 변화"` ➔ `"판도 변화"`) to concise terms across all categories.
  - In `src/llm/prompts.py`, `CATEGORY_LENSES` defines concise 1~2 word section subheadings for all 10 categories.
  - All unit, integration, and UI tests pass with zero regressions.

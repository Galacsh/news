# SLICE-0007: Notice Center with 7-Day Unread LocalStorage Badge

Status: proposed
Source: REQ-0002

## Outcome & Boundaries
- Outcome: Structured announcements repository (`data/notices.json`), a dedicated notice/changelog page (`notices.html`), and a smart unread badge in `index.html` header that flags notices published within the last 7 days that have not been read in browser `localStorage`.
- Boundaries:
  - In: `data/notices.json` schema, `notices.html` page, header badge and `localStorage` synchronization in `index.html`, unit tests.
  - Out: Archive explorer (SLICE-0008).

## Specification
- Acceptance Criteria:
  - Given `data/notices.json` with announcements
  - When a user opens `index.html`
  - Then an unread badge indicator is displayed on the notice icon if any notice dated within 7 days is unread in `localStorage`.
  - When the user visits `notices.html` (or marks notices as read)
  - Then the notice IDs are recorded in `localStorage.setItem("read_notice_ids", ...)` and the unread badge is cleared.
- Dependencies: SLICE-0003

## Tasks & Batches
| Task ID | Batch | Title | Locked Files | Verify Command | Status |
|---|---|---|---|---|---|
| TASK-01 | Batch 1 | Define notices schema and build notices viewer page | `data/notices.json,notices.html,tests/test_notices.py` | `.venv/bin/pytest tests/test_notices.py` | `[ ] pending` |
| TASK-02 | Batch 2 | Integrate 7-day unread badge and localStorage state in main dashboard | `index.html,tests/test_notices.py` | `.venv/bin/pytest tests/test_notices.py` | `[ ] pending` |

## Verification Evidence
NOT RUN

## Review Findings
NOT RUN

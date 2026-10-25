# SLICE-0004: GitHub Actions & Pages Automation

Status: in-progress
Source: REQ-0001

## Outcome & Boundaries
- Outcome: Fully automated CI/CD workflow running daily on GitHub Actions that runs the daily pipeline with Gemini API secret, commits newly generated daily JSON to repository, and deploys the static dashboard to GitHub Pages.
- Boundaries:
  - In: `.github/workflows/daily-briefing.yml`, GitHub Pages deployment action, scheduled cron triggers (e.g. 06:30 KST or 07:00 KST / 22:00 UTC), and manual `workflow_dispatch`.
  - Out: Local generation logic (handled in SLICE-0003).

## Specification
- Acceptance Criteria:
  - Given GitHub Actions workflow triggered via cron or dispatch
  - When the workflow runs
  - Then it executes the pipeline with GEMINI_API_KEY, commits data updates, and publishes the site to GitHub Pages.
- Dependencies: SLICE-0003

## Tasks & Batches
| Task ID | Batch | Title | Locked Files | Verify Command | Status |
|---|---|---|---|---|---|
| TASK-01 | Batch 1 | Configure GitHub Actions cron & Pages deploy | `.github/workflows/daily-briefing.yml,tests/test_workflow.py` | `.venv/bin/pytest tests/test_workflow.py` | [x] verified|

## Verification Evidence
NOT RUN

## Review Findings
NOT RUN

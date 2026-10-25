# SLICE-0002: Gemini Free Tier News Summarizer

Status: proposed
Source: REQ-0001

## Outcome & Boundaries
- Outcome: News synthesis engine powered by Gemini API free tier that takes categorized candidate articles and generates structured summaries (headline, summary, impact analysis, and related source links) while strictly respecting free-tier rate limits.
- Boundaries:
  - In: Gemini API client integration, structured prompt design, JSON schema output enforcement, rate limit & quota handling (RPM/RPD retries/backoff).
  - Out: Feed fetching (handled in SLICE-0001), GitHub deployment (handled in SLICE-0004).

## Specification
- Acceptance Criteria:
  - Given a cluster of news articles for a category
  - When submitted to the Gemini synthesis module
  - Then it returns structured JSON containing top headlines and category news with "핵심" (summary) and "파급" (impact) adhering to UI schema.
- Dependencies: SLICE-0001

## Tasks & Batches
| Task ID | Batch | Title | Locked Files | Verify Command | Status |
|---|---|---|---|---|---|
| TASK-01 | Batch 1 | Implement Gemini client & structured prompt | `src/llm/summarizer.py` | `pytest tests/test_summarizer.py` | `[ ] pending` |

## Verification Evidence
NOT RUN

## Review Findings
NOT RUN

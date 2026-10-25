# SLICE-0002: Gemini Free Tier News Summarizer

Status: completed
Source: REQ-0001

## Outcome & Boundaries
- Outcome: Robust, rate-limit compliant news summarization and briefing engine powered by Google Gemini API free tier that accepts normalized candidate articles, clusters and synthesizes them into Top 3 headlines and category briefings with "핵심" (Summary) and "파급" (Impact), and outputs JSON strictly adhering to the dashboard schema (`categoryId: int`).
- Boundaries:
  - In: Gemini API client using official `google-genai` SDK (`from google import genai`) with structured JSON schema enforcement, prompt engineering, exponential backoff for HTTP 429 / transient errors, mock/dry-run mode for keyless testing, and synthesis orchestrator producing Top 3 headlines and category articles.
  - Out: RSS ingestion (handled in SLICE-0001), full disk pipeline and historical archival (handled in SLICE-0003), GitHub deployment (handled in SLICE-0004).

## Specification
### Acceptance Criteria
- **AC-1 (Structured JSON Output & Schema Conformance)**:
  - Given a set of filtered candidate articles across categories
  - When the summarizer executes
  - Then it returns a payload containing `topHeadlines` (exactly 3 items) and `articles` (categorized items) where every item has `id`, `categoryId: int`, `headline`, `summary` (핵심), `impact` (파급), and `links: list[{title, url}]`.
- **AC-2 (Free Tier Quota & Rate Limit Resilience)**:
  - Given Gemini free tier constraints (15 RPM / 1,500 RPD)
  - When making API calls
  - Then the client implements exponential backoff retries on HTTP 429 / 503, minimizes API round-trips via batching, and provides a dry-run/mock mode when `GEMINI_API_KEY` is absent.
- **AC-3 (Accurate Category ID Association)**:
  - Given articles grouped by category
  - When Gemini synthesizes the briefing
  - Then all output items preserve the correct `categoryId` matching `data/categories.json`.
- **AC-4 (Korean Language Quality & Guardrails)**:
  - Given candidate article headlines and snippets
  - When prompts are rendered
  - Then the LLM output is in clear, natural Korean with concise bullet-free summary and impact descriptions.

### Non-goals
- Managing RSS feeds (completed in SLICE-0001).
- Direct GitHub Pages deployment (deferred to SLICE-0004).

### Edge Cases
- Missing `GEMINI_API_KEY`: client raises clear `ValueError` or executes mock mode if enabled.
- Network timeouts: strict request timeout (default 30s) with retries.
- Empty candidate list for a category: handles empty inputs gracefully without throwing uncaught exceptions.
- Malformed model responses: JSON validation and fallback handling.

## Tasks & Batches
| Task ID | Batch | Title | Locked Files | Verify Command | Status |
|---|---|---|---|---|---|
| TASK-01 | Batch 1 | Implement Gemini REST client, prompt builder & retry logic | `src/llm/client.py`, `src/llm/prompts.py` | `.venv/bin/pytest tests/test_gemini_client.py` | [x] verified|
| TASK-02 | Batch 2 | Implement news synthesis engine & schema output formatting | `src/llm/summarizer.py` | `.venv/bin/pytest tests/test_summarizer.py` | [x] verified|

## Verification Evidence
- `.venv/bin/pytest tests/test_gemini_client.py`: 19 passed in 0.25s
- `.venv/bin/pytest tests/test_summarizer.py`: 12 passed in 0.05s
- `.venv/bin/pytest`: 95 passed in 0.30s (full regression test suite clean)
- Both TASK-01 and TASK-02 verified via `flow.py complete`.

## Review Findings
- Auditor: `flow_reviewer` (Verdict: **PASS**)
- AC-1 (Structured JSON & Schema): PASS (strict 3 topHeadlines, integer sequential `id`, integer `categoryId`, valid links).
- AC-2 (Free Tier Quota & Rate Limit): PASS (`google-genai` SDK `HttpOptions`/`HttpRetryOptions` + app-level backoff, mock mode).
- AC-3 (Accurate Category ID Association): PASS (dynamic resolution against `data/categories.json`).
- AC-4 (Korean Language Quality): PASS (English instructions with strict Korean output mandate, bullet-free prose).

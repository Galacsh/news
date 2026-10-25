# SLICE-0001: RSS Feed Ingestion & Normalization

Status: completed
Source: REQ-0001

## Outcome & Boundaries
- Outcome: Validated, resilient Python RSS ingestion module that fetches live Korean news feeds, deduplicates articles, categorizes them according to the 10 target categories, and extracts article titles, snippets, source outlets, and URLs.
- Boundaries:
  - In: RSS/Atom parsing (via `feedparser` / `urllib`), feed health verification, HTML stripping/unescaping, URL/title deduplication, category mapping, and per-category candidate trimming.
  - Out: LLM summarization (deferred to SLICE-0002), JSON disk persistence (deferred to SLICE-0003), GitHub Actions automation (deferred to SLICE-0004).

## Specification
### Acceptance Criteria
- **AC-1 (Parsing & Normalization)**:
  - Given a valid RSS/Atom feed URL or XML content
  - When parsed by `RSSFeedParser`
  - Then it extracts articles with normalized fields: `id` (hash), `title` (clean text, no raw HTML entities), `summary`, `url`, `outlet`, `published_at` (ISO timestamp), and `category`.
- **AC-2 (Resilience & Error Handling)**:
  - Given an unreachable, timeout, or malformed RSS feed URL
  - When the ingestion engine executes
  - Then it logs a warning, skips the faulty feed gracefully, and continues processing remaining feeds without raising an uncaught exception. Strict request timeout (5s) is enforced.
- **AC-3 (Deduplication & Category Filtering)**:
  - Given multiple feeds containing identical URLs or near-duplicate titles
  - When articles are aggregated
  - Then duplicate entries are pruned and articles are grouped into the 10 target categories (`정치`, `경제·금융`, `산업·기업`, `사회`, `국제·글로벌`, `AI·빅테크`, `IT·통신`, `문화·콘텐츠`, `스포츠`, `라이프스타일`).
- **AC-4 (Per-Category Quota & Recency)**:
  - Given aggregated articles for each category
  - When sorted by publication date
  - Then it retains only the top N (configurable, default 5) most recent articles from the past 24-48 hours to prevent token overflow for downstream LLM synthesis.
- **AC-5 (Feed Health Check Utility)**:
  - Given candidate feed URLs (e.g. from `rss-unverified.txt` or curated feeds)
  - When running the feed probe utility
  - Then it verifies HTTP status code, content validity, and outputs verified active feeds.

### Non-goals
- Full-text scraping of JavaScript-heavy or paywalled news outlets.
- LLM summarization or impact extraction (deferred to SLICE-0002).
- Final static site generation or deployment (deferred to SLICE-0003 & SLICE-0004).

### Edge Cases & Failure Modes
- Feeds using legacy Korean encodings (`EUC-KR`, `CP949`) instead of `UTF-8` -> handle automatic decoding.
- Feeds with HTML tags, CDATA blocks, or escaped quotes in `title` / `description` -> strip tags and unescape HTML.
- Feeds with invalid or missing `<pubDate>` -> fallback to fetch time.
- Feeds returning empty item lists -> ignore gracefully.
- Slow network or hanging connections -> apply 5s connection/read timeout per feed.

## Tasks & Batches
| Task ID | Batch | Title | Locked Files | Verify Command | Status |
|---|---|---|---|---|---|
| TASK-01 | Batch 1 | Implement RSS models & feed parsing engine | `src/ingest/rss.py`, `src/ingest/models.py` | `.venv/bin/pytest tests/test_rss.py` | [x] verified|
| TASK-02 | Batch 2 | Implement deduplication, category filtering & feed curation | `src/ingest/filter.py`, `src/ingest/sources.py` | `.venv/bin/pytest tests/test_filter.py` | [x] verified|

## Verification Evidence
PASS: 62/62 tests passing in 0.07s (`.venv/bin/pytest`)
- TASK-01 verified (36 tests)
- TASK-02 verified (26 tests)

## Review Findings
PASS: Audited by Code Reviewer.
- Verified against AC-1 (Parsing & Normalization)
- Verified against AC-2 (Resilience & 5s Timeouts)
- Verified against AC-3 (Deduplication & Category Mapping)
- Verified against AC-4 (Quota & Recency Limits)
- Verified against AC-5 (Feed Health Probe & Catalog Persistence)
- Verified UI cache bump & change detection toast notifications

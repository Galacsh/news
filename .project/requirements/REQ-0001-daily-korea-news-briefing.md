# REQ-0001: Daily Korea News Briefing Website

Status: captured
Origin: User request (2026-10-25) - "Daily Korea News Briefing website via GitHub Action & Pages, Gemini API Key free tier, RSS Feeds & scraping. I've already got HTML template"

## 1. Problem & Desired Outcome
Deliver an automated daily briefing website of major Korean news published to GitHub Pages at zero operating cost. The system collects news articles via verified Korean RSS feeds, deduplicates and categorizes them, synthesizes summaries via Google Gemini API free tier, outputs structured daily JSON (`data/latest.json`), and renders an interactive, responsive dashboard (`index.html`) on a daily automated GitHub Actions schedule.

## 2. Stakeholders & Cost Invariants
- **Target Audience**: Readers seeking concise, daily Korean news digests on mobile and web.
- **Maintainer**: Managing the system strictly within zero-cost service tiers:
  - Google Gemini API free tier (RPM/TPM/RPD limits).
  - GitHub Actions free runner minutes (scheduled cron execution).
  - GitHub Pages free static hosting.

## 3. Scope & Requirements Catalog

### 3.1 Data Architecture & Schema Normalization
- **R-DATA-01 (Separation of Invariants & Dynamic Data)**:
  - `data/categories.json`: Invariant category definitions containing `id` (integer), `name`, `badgeColor`, and `aliases`.
  - `data/feeds.json`: Externalized RSS feed configuration decoupled from Python source code, storing `name`, `url`, `categoryId`, `category`, and `is_active` flag.
  - `data/latest.json`: Dynamic daily briefing output containing ISO 8601 `briefingDate`, `topHeadlines` (Top 3), and `articles` list.
- **R-DATA-02 (Relational ID Mapping)**:
  - All category references across `data/latest.json` and `data/feeds.json` must map via integer `categoryId` foreign key rather than literal category name strings.
- **R-DATA-03 (ISO Date Standard)**:
  - `briefingDate` in `data/latest.json` must use standard ISO 8601 formatting (`YYYY-MM-DDTHH:mm:ss+09:00` or `YYYY-MM-DD`). The client UI formats this to Korean locale text.

### 3.2 RSS Feed Ingestion & Curation
- **R-FEED-01 (Candidate Pool & Deduplication)**:
  - Candidate feeds sourced from `rss-unverified.txt` (860+ candidate URLs).
  - Feed parser removes duplicate URLs and strips adhered delimiters/non-ASCII characters.
- **R-FEED-02 (Catalog Retention for Future Category Changes)**:
  - Verified working feeds are preserved in the catalog (`data/feeds.json`) even if not currently active, allowing seamless re-activation if target categories change.
- **R-FEED-03 (Active Category Filtering)**:
  - Filter logic identifies and selects only RSS feeds matching the currently active interested categories (10 target categories).
- **R-FEED-04 (Parser Resilience)**:
  - Enforce strict 5.0s connection/read timeout per feed.
  - Gracefully handle malformed XML, 404/500 HTTP errors, and timeouts without crashing the pipeline.
  - Support legacy Korean encodings (`EUC-KR`, `CP949`) alongside `UTF-8`.
  - Clean text by unescaping HTML entities and stripping HTML tags.

### 3.3 Article Filtering & Quota Management
- **R-ART-01 (Article Deduplication)**:
  - Deduplicate articles by normalized tracking-free URL (pruning UTM parameters) and fuzzy title similarity (`difflib.SequenceMatcher >= 0.8`).
- **R-ART-02 (Recency Filtering)**:
  - Retain only articles published within the last 24–48 hours, handling arbitrary timezones.
- **R-ART-03 (Per-Category Quota Limits)**:
  - Sort articles descending by publication date and retain top N (default 5) per category to prevent token overflow for downstream Gemini synthesis.

### 3.4 Client Dashboard UI (`index.html`)
- **R-UI-01 (Dynamic JSON Rendering)**:
  - Converted from `sample.html` into a dynamic client-side SPA rendering Top 3 headlines, category tabs, and news cards with related article toggles.
- **R-UI-02 (Header Cleanliness)**:
  - Removed `"종합 관심도 기준"` subtext from the Top 3 section header.
- **R-UI-03 (Manual Refresh & Cache Busting)**:
  - Header refresh button triggers data reload.
  - All JSON fetches employ cache-busting query parameter `?_t=${Date.now()}` and `{ cache: "no-cache" }` to prevent stale GitHub Pages / CDN caching.
- **R-UI-04 (Toast Notification & Change Detection)**:
  - Bottom-centered toast notification system.
  - If data changed: re-renders views and alerts `"최신 브리핑 데이터로 갱신되었습니다."` (`success`).
  - If data is identical: alerts `"새로운 변경 사항이 없습니다. (최신 상태 유지 중)"` (`info`).
  - If fetch fails: alerts error notification.

### 3.5 LLM Summarization & Delivery (Slices 2 & 4)
- **R-LLM-01**: Synthesize categorized news into Top 3 headlines and category briefings with "핵심" (Summary) and "파급" (Impact) using Gemini API free tier.
- **R-CI-01**: GitHub Actions workflow running on a daily cron (e.g. 06:30 KST) and manual dispatch, committing new daily JSON and deploying to GitHub Pages.

## 4. Verification & Constraints
- Unit test suite enforcing parsing, filtering, feed catalog serialization, and fallback coverage.
- Pure static HTML/CSS/JS + JSON output with no backend server required at runtime.

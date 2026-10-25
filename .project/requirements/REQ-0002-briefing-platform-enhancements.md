# REQ-0002: Daily Korea News Briefing Platform Enhancements

Status: captured
Origin: User request (2026-10-25)

## 1. Overview & Objectives
Following the successful deployment of the core MVP (ingestion, Gemini synthesis, static dashboard, and GitHub Actions automation), this requirements document captures the next evolution of the platform:
1. Enhancing content quality and category completeness by expanding RSS feeds and automated health checks.
2. Providing transparency and diagnostics via a pipeline telemetry monitoring page.
3. Engaging users with announcements and a changelog center with unread indicator badges.
4. Enabling intuitive historical briefing discovery via a dedicated archive explorer page.

---

## 2. Requirements Catalog

### 2.1 Content Quality & Category Coverage (피드 확장 및 카테고리 균형 수집)
- **R-COV-01 (Category Article Minimum Quota)**:
  - Address categories that currently have 0 or only 1 article extracted (e.g. AI·빅테크, IT·통신, 문화·콘텐츠, 라이프스타일).
  - Target: Each active category should reliably retain at least 2 to 3 candidate articles daily after filtering.
- **R-COV-02 (Automated Feed Health Check Utility)**:
  - Provide an automated CLI tool (`src/tools/feed_checker.py` or `src/ingest/health.py`) that scans candidate feeds from `rss-unverified.json` (863 feeds).
  - Tests HTTP status, latency, XML validity, encoding, and recency of newest article.
  - Automatically recommends or registers active, healthy feeds into `data/feeds.json` for deficient categories.
- **R-COV-03 (Adaptive Category Lookback Window)**:
  - For slow-publishing categories (e.g. weekly cultural/tech deep dives), allow a category-specific fallback lookback window (e.g., up to 48 hours) if fewer than 2 articles are found within the standard 24-hour window.

---

### 2.2 Pipeline Telemetry & Monitoring Dashboard (수집 모니터링 & 리포팅)
- **R-MON-01 (Pipeline Execution Telemetry)**:
  - `src/pipeline.py` records operational metrics during each run:
    - Execution start/end time and total duration.
    - Feeds attempted, succeeded, and failed (with HTTP error codes / exceptions).
    - Total raw articles ingested vs deduplicated vs recency-filtered.
    - Per-category retention counts (candidate pool size vs summarized count).
    - Gemini API status (response time, retry count, model used, fallback triggered).
  - Serializes telemetry to `data/telemetry/latest.json` and historical archive `data/telemetry/archive/YYYY-MM-DD.json`.
- **R-MON-02 (Monitoring Dashboard Page `monitoring.html`)**:
  - Standalone, lightweight static dashboard page linked from the main site footer/header.
  - Overall pipeline health badge (정상 / 주의 / 장애).
  - Funnel metrics visualization: "총 N건 수집 → 중복·시간 필터 후 M건 선별 → 최종 요약 K건".
  - Media feed status table: per-feed HTTP latency and success/failure status.

---

### 2.3 Notice Center & Unread Badge (공지사항 & 미열람 뱃지)
- **R-NOT-01 (Notices Data Schema `data/notices.json`)**:
  - Structured static data containing announcements:
    - `id`: Unique identifier (e.g. `notice-20261025-01`).
    - `title`: Notice title.
    - `date`: Publication date (`YYYY-MM-DD` or ISO 8601).
    - `category`: Badge category (e.g. "신규 기능", "공지", "점검").
    - `content`: Plain text or markdown announcement text.
- **R-NOT-02 (Notice View / Page `notices.html`)**:
  - Accessible via header navigation link/icon.
  - Displays notices in reverse chronological order with badges, dates, and clear readable prose.
- **R-NOT-03 (7-Day Unread Badge via LocalStorage)**:
  - Header notice icon inspects `data/notices.json`.
  - An "unread" indicator (badge dot or counter) is displayed if:
    1. A notice was published within the last 7 days (`date >= now - 7 days`).
    2. The notice `id` is NOT found in browser `localStorage.getItem("read_notice_ids")`.
  - When the user visits the notice page or closes a notice modal, the viewed notice IDs are saved to `localStorage`, clearing the unread badge immediately.

---

### 2.4 Historical Archive Explorer (과거 브리핑 탐색 전용 페이지)
- **R-ARC-01 (Archive Manifest Generation `data/archive/manifest.json`)**:
  - Pipeline automatically maintains an archive manifest index listing all generated historical briefings:
    - Date string (`YYYY-MM-DD`).
    - Top headline summary / keywords.
    - Total article count.
- **R-ARC-02 (Archive Explorer Page `archive.html`)**:
  - Dedicated historical exploration page.
  - Interactive calendar / date picker component: dates with available briefings are highlighted and clickable.
  - Date cards grid: browse past dates with preview cards showing Top 3 headlines.
  - Seamless navigation to view that date's full briefing (`index.html?date=YYYY-MM-DD`).

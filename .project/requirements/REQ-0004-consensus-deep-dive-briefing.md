# REQ-0004: Legally Compliant Cross-Outlet Consensus & Category-Specific Deep-Dive Briefing

Status: captured
Origin: User request (2026-10-31)

## 1. Overview & Objectives
Portal frontpages (e.g., Daum News) prioritize clickbait and sensationalism over genuinely significant news, while raw RSS `<description>` snippets lack sufficient article body text for deep analysis. Furthermore, applying a uniform summary prompt across all news categories produces generic, superficial commentary.

This requirement establishes a complete end-to-end architecture that:
1. Ingests metadata strictly from legally permissible (`bot: true`) news outlets across diverse perspectives.
2. Extracts genuinely major news via **Cross-Outlet Consensus Clustering** and fetches full article bodies via `BeautifulSoup4` only for selected top clusters (used transiently in memory for synthesis, never stored or redistributed).
3. Executes Gemini synthesis in **category-grouped batches** to prevent GitHub Actions timeouts and token truncation.
4. Keeps the clean main card layout (`headline` + `summary` + `impact`) on `index.html`, while navigating on click to a dedicated **Detail Page (`detail.html`)** featuring **Category-Specific Deep-Dive Lenses (`deepDive`)** and an always-expanded related articles list (`links`) at the bottom.

---

## 2. Requirements Catalog

### 2.1 Legally Compliant Multi-Outlet Feed Catalog (`data/feeds.json`, `src/ingest/sources.py`)
- **R-FEED-01 (`bot: true` Enforcement)**:
  - Exclude outlets marked `"bot": false` in `data/presslist.json` (e.g., 조선일보, 경향신문, 블로터).
  - Populate `data/feeds.json` and `DEFAULT_FALLBACK_FEEDS` with verified `"bot": true` outlets across all 10 categories so each category has multiple independent outlets for cross-validation.

### 2.2 Two-Stage Hybrid Ingestion: Cross-Outlet Consensus & BS4 Body Extraction (`src/ingest/filter.py`, `src/ingest/body_extractor.py`)
- **R-INGEST-01 (Cross-Outlet Topic Clustering)**:
  - Group candidate articles discussing the same event/topic within each category using keyword/token similarity.
  - Rank clusters by **Distinct Outlets Count** (Cross-Outlet Consensus) combined with recency so topics covered simultaneously by multiple outlets take top priority over single-outlet clickbait.
  - Preserve sibling article titles and URLs on the representative cluster/article so all cross-validated source links are passed to the summarizer.
- **R-INGEST-02 (Targeted Full-Text Body Extraction via BeautifulSoup4)**:
  - For the top selected candidate articles (approx. 25–30 articles across categories), fetch the original article HTML via `urllib.request` and extract clean body paragraphs using `BeautifulSoup4` (`src/ingest/body_extractor.py`).
  - Truncate extracted body text to a concise factual window (e.g., 800–1,000 chars) in memory for LLM grounding, and never persist raw full-text article bodies to output JSON files.
  - Gracefully fall back to the RSS summary snippet if fetching or parsing fails or times out.

### 2.3 Batched Gemini Synthesis & Category-Specific Lenses (`src/llm/prompts.py`, `src/llm/summarizer.py`, `src/pipeline.py`)
- **R-LLM-01 (Category-Specific Deep-Dive Schema)**:
  - Retain `headline` (de-clickbaited factual title), `summary` (핵심, 1–2 sentences in 해요체), and `impact` (파급, 1–2 sentences in 해요체).
  - Add `deepDive` object per briefing item containing `lensTitle` and `sections: [{"label": str, "content": str}, ...]` tailored to each category's analytical lens:
    1. **정치**: 의도와 실현 가능성 (`왜 지금 나왔나 (숨은 셈법)` / `실제 통과·시행 가능성과 효력`)
    2. **경제·금융**: 착시 제거 & 내 지갑 타격 (`지표·발표 이면의 맹점` / `금리·물가·내 지갑에 미치는 영향`)
    3. **산업·기업**: 보도자료 판독 & 승패 해부 (`홍보 거품 걷어낸 실제 현황` / `웃는 기업(수혜) vs 우는 기업(피해)`)
    4. **사회**: 배경 맥락 & 행동 지침 (`사안의 구조적 배경` / `시민이 챙겨야 할 실질적 체크포인트`)
    5. **국제·글로벌**: 한국에 튀는 불똥 (`글로벌 갈등·사건의 본질` / `한국 수출·환율·산업에 미칠 손익`)
    6. **AI·빅테크**: 거품 vs 진짜 기술 변곡점 (`마케팅 빼고 진짜 바뀐 기술 본질` / `개발자·실무·생태계 판도 변화`)
    7. **IT·통신**: 기술 실효성 & 시장 판도 (`기존 서비스 대비 핵심 차이점` / `소비자·통신·IT 업계 체감 변화`)
    8. **문화·콘텐츠**: 흥행 맥락 & 관전 포인트 (`기록·트렌드의 산업적 의미` / `향후 일정 및 핵심 관전 포인트`)
    9. **스포츠**: 승부처 분석 & 향후 일정 (`결정적 승부처와 기록의 의미` / `다음 경기 일정 및 관전 포인트`)
    10. **라이프스타일**: 일상의 행동 법칙 (`트렌드·연구 결과의 팩트 체크` / `일상에서 바로 적용할 행동 요령`)
- **R-LLM-02 (Batched Category Execution & Timeout Safety)**:
  - Split summarization into manageable category batches (e.g., 3–4 categories per Gemini call) instead of a single monolithic call to avoid output token truncation and timeouts.
  - Isolate batch failures so a single failed batch falls back deterministically without aborting other batches.
  - Configure `.github/workflows/daily-briefing.yml` with explicit job/step timeout protection.

### 2.4 Two-Tier Frontend UI: Main Cards to Detail Page (`index.html`, `archive.html`, `detail.html`)
- **R-UI-01 (Main Briefing Cards)**:
  - Keep `headline`, `summary` (핵심), and `impact` (파급) on each card in `index.html`.
  - Remove the in-card `관련 기사 (N)` toggle button and hidden article list view from main cards.
  - Make cards clickable to navigate to `detail.html?id=<id>` (or `detail.html?archive=<archive>&id=<id>` when viewing an archive).
- **R-UI-02 (Dedicated Detail Page `detail.html`)**:
  - Render the selected article's category badge, briefing timestamp, factual headline, core summary (`summary`), impact (`impact`), and the category-specific `deepDive` analysis sections.
  - Render the `links` (related source articles) at the bottom of `detail.html` in a fully visible, non-collapsible list (no accordion/toggle required).
  - Gracefully handle legacy archive JSON items that lack `deepDive`.

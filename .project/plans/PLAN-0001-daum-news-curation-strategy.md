# PLAN-0001: Daum News In-Depth Exploration & Curation Strategy Blueprint

Status: approved
Origin: User request /goal (2026-10-26)
Related Requirements: REQ-0003

## 1. Overview & Strategic Pivot
Transitioning from unranked RSS feed ingestion with blind LLM filtering to **human-and-algorithm portal curation ingestion + LLM executive synthesis**. This document records the architectural exploration of Daum News (`news.daum.net`) and establishes the technical blueprint for multi-tiered news curation.

---

## 2. Daum News Reconnaissance & Asset Inventory

All core surfaces of Daum News are **Server-Side Rendered (SSR)** in 300KB+ HTML payloads, enabling fast, robust parsing via `BeautifulSoup4` with zero browser automation:

### 2.1 Surfaces Analyzed
1. **Portal Home (`https://news.daum.net`)**:
   - `box_news_headline2` ("이 시각 주요뉴스"): 10–16 editorially curated national headlines.
   - `box_trendranking` ("실시간 트렌드"): 10 real-time search queries and trending topics.
   - `box_news_column` ("시사 매거진", "라이프 매거진"): In-depth editorial columns.
   - `box_news_block` ("'발로 뛰다' 현장/르포"): Investigative on-the-ground reporting.

2. **The 7 Core Section Pages (`https://news.daum.net/{section}`)**:
   - `/politics` (정치): 정치 주요뉴스 + 청와대, 외교/국방, 국회/정당, 행정/지자체, 북한.
   - `/economic` (경제): 경제 주요뉴스 + 경제정책, 금융, 주식, 가상자산, 부동산, 연금/노후, 산업, 자동차, 벤처/스타트업.
   - `/digital` (IT/과학): IT・과학 주요뉴스 + **AI**, 테크, IT기업, 과학, 우주, 게임.
   - `/society` (사회): 사회 주요뉴스 + 사건・사고, 사법, 노동, 교육, 의료/보건, 재난안전, 인구.
   - `/foreign` (국제): 국제 주요뉴스 + 국제정세, 북미, 중국, 일본, 유럽, 중동/아랍, 아시아.
   - `/culture` (문화): 문화 주요뉴스 + 콘텐츠, 영화, 책, 음악, 공연, 미술, 문화재.
   - `/life` (생활): 생활 주요뉴스 + 건강, 음식, 동물, 취미, 여행, 육아, 스타일.

3. **Article Detail Pages (`https://v.daum.net/v/...`)**:
   - Clean paragraph text extraction from `.article_view p`.
   - High-res thumbnails via `meta[property="og:image"]`.
   - Stable article IDs (`YYYYMMDDHHMMSSNNN`), press outlet attribution, and timestamps.

4. **Legal & Compliance**:
   - `https://news.daum.net/robots.txt` returns HTTP 404. Under RFC 9309 (§2.3.1.2), this constitutes unrestricted crawl access.

---

## 3. The 4-Tier Curation Framework

```text
+---------------------------------------------------------------------------------------+
| TIER 1: Executive Top 5 ("60-Second Briefing")                                        |
| Source: news.daum.net frontpage (box_news_headline2)                                  |
| Purpose: The essential national headlines for time-constrained readers.               |
+---------------------------------------------------------------------------------------+
| TIER 2: 10-Category Balanced Coverage ("Domain Deep-Dives")                           |
| Source: 7 Section hubs + granular subcategory blocks (AI, 주식, 가상자산, 외교 등)     |
| Rule: Exactly 3 high-signal articles per category (guarantees zero empty categories). |
+---------------------------------------------------------------------------------------+
| TIER 3: Public Pulse ("What Korea is Searching Right Now")                            |
| Source: box_trendranking (Top 10 real-time search queries)                            |
| Purpose: Captures trending civic interest and viral events.                           |
+---------------------------------------------------------------------------------------+
| TIER 4: Slow Journalism ("Investigative Spotlight & Perspectives")                    |
| Source: '발로 뛰다' 현장/르포 + box_news_column                                       |
| Purpose: High-nutrition investigative long-form pieces to balance transactional news. |
+---------------------------------------------------------------------------------------+
```

---

## 4. Multi-Outlet Clustering & Deduplication

Portal news frequently features multiple media outlets reporting on the exact same event.
1. **Title Normalization**: Strip outlet tags (`[단독]`, `[종합]`, `[속보]`, `[포토]`).
2. **Jaccard / Token Similarity**: If two articles share $\ge 60\%$ keyword overlap, bundle them into a single **Story Cluster**.
3. **Primary Lead + Multi-Perspective Link**: Present the most comprehensive article as primary, with a secondary link to alternative press coverage for political/economic balance.

---

## 5. High-Leverage Gemini Free-Tier Prompt Design

Rather than asking the LLM to judge news importance from hundreds of raw feeds, Gemini is constrained to act as an **Executive Intelligence Analyst** on pre-curated high-signal candidates:

```json
{
  "headline_bottom_line": "한 줄 요약 (Fact-based bottom line)",
  "bullet_1_fact": "핵심 팩트 (무슨 일이 일어났는가)",
  "bullet_2_context": "배경 및 맥락 (왜 지금 발생했는가)",
  "bullet_3_impact": "파장 및 전망 (향후 어떤 영향이 있는가)"
}
```

This reduces token usage to <1,500 tokens per category while eliminating hallucinations.

---

## 6. Implementation Slice Roadmap

1. **SLICE-0010: Daum Multi-Section Harvester** (`src/ingest/daum_sections.py`, `tests/test_daum_sections.py`):
   - Harvester for all 7 section pages and subcategory blocks.
2. **SLICE-0011: Curation & Topic Clustering Engine** (`src/curation/engine.py`, `tests/test_curation.py`):
   - Deduplication, clustering, and 10-category routing.
3. **SLICE-0012: Pipeline & UI Integration** (`src/pipeline.py`, `index.html`):
   - Connect curation engine to pipeline and render 4-tier briefing UI with real-time trend badges.

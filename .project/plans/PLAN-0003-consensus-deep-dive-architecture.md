# PLAN-0003: Cross-Outlet Consensus, BS4 Body Extraction & Category Deep-Dive Architecture

Status: approved
Origin: User request /plan & /flow-router (2026-10-31)
Related Requirements: REQ-0004

## 1. Architectural Overview

1. **Stage 1: Legally Safe Multi-Outlet RSS Ingestion (`data/feeds.json`, `src/ingest/sources.py`)**
   - Strictly use outlets tagged `"bot": true` in `data/presslist.json` (removing 조선일보, 경향신문, 블로터).
   - Configure 3–4 independent outlets per category across all 10 categories (e.g., 연합뉴스, 동아일보, 한국경제, 매일경제, 한겨레, 국민일보, 노컷뉴스, MBN, 전자신문, SBS, AI타임스, GeekNews).

2. **Stage 1.5: Cross-Outlet Consensus Clustering & BS4 Body Extraction (`src/ingest/filter.py`, `src/ingest/body_extractor.py`)**
   - **Consensus Clustering**: Tokenize article titles & snippets inside each category, cluster articles covering the same event by token overlap, and score clusters by **Distinct Outlets Count** + recency. Attach sibling article links (`related_links` on `Article`) to the cluster representative.
   - **Targeted Body Extraction**: For the retained top candidate articles (~25–30 articles), fetch the target URL concurrently with `urllib.request` + `BeautifulSoup4` (`ArticleBodyExtractor`) to extract main article paragraphs (truncated to ~900 chars). Pass this enriched context to Gemini in memory and never persist raw article bodies to disk.

3. **Stage 2: Batched Gemini Summarization with Category-Specific Lenses (`src/llm/prompts.py`, `src/llm/summarizer.py`, `src/pipeline.py`)**
   - Partition categories into batches (e.g., 3–4 categories per batch) so each Gemini API call stays well within output token limits and completes quickly without timeout.
   - Generate `headline` (de-clickbaited fact), `summary` (핵심), `impact` (파급), and `deepDive` (`lensTitle` + 2 category-tailored `sections`) in polite informal Korean (`해요체`).

4. **Stage 3: Two-Tier Frontend (`index.html`, `archive.html`, `detail.html`)**
   - `index.html`: Clean cards displaying `headline`, `summary`, and `impact` (in-card link toggle removed). Clicking a card navigates to `detail.html?id=<id>` (or `detail.html?archive=<archive>&id=<id>`).
   - `detail.html`: Full view displaying category badge, timestamp, `headline`, `summary`, `impact`, the category-specific `deepDive` sections, and an always-visible (non-collapsed) list of source `links` at the bottom.

---

## 2. Task Partitioning for `subagent-flow` (SLICE-0010)

- **Batch 1 (Parallel Independent Modules - Disjoint File Locks)**:
  - `TASK-01`: Legally compliant multi-outlet feed catalog (`data/feeds.json`, `src/ingest/sources.py`, `tests/test_rss.py`)
  - `TASK-02`: Cross-outlet consensus clustering & BS4 body extractor (`src/ingest/models.py`, `src/ingest/filter.py`, `src/ingest/body_extractor.py`, `tests/test_filter.py`)
  - `TASK-03`: Category-specific deep-dive prompts & batched summarizer (`src/llm/prompts.py`, `src/llm/summarizer.py`, `tests/test_summarizer.py`)
  - `TASK-04`: Main card click navigation & `detail.html` deep-dive UI (`index.html`, `archive.html`, `detail.html`, `tests/test_archive_ui.py`)
- **Batch 2 (Pipeline & Workflow Integration)**:
  - `TASK-05`: End-to-end pipeline body enrichment, batch orchestration & workflow timeout protection (`src/pipeline.py`, `.github/workflows/daily-briefing.yml`, `tests/test_pipeline.py`, `tests/test_workflow.py`)

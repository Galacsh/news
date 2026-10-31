# REQ-0005: Rich Multi-Outlet Consensus Clustering & Exact 3-Article Category Quota

Status: captured
Origin: User request (2026-10-31)

## 1. Overview & Objectives
Analysis of production briefing outputs revealed two major issues:
1. Briefing items predominantly contained only 1 source link despite widespread multi-outlet reporting, caused by:
   - Premature cross-outlet pruning in `deduplicate_articles` prior to clustering.
   - An overly strict Jaccard threshold (0.35) diluted by noisy summary text.
   - Missing or inactive feed URLs (e.g. DongA global feed yielding 0 articles, and absent feeds for Hankyoreh, SBS, MBN, NocutNews).
2. Several categories contained only 1 or 2 briefing items instead of a reliable 3-item depth.

This requirement establishes:
1. Expansion and repair of `bot: true` RSS feeds (DongA international fix, Hankyoreh, SBS, MBN, NocutNews) across categories.
2. Reform of `deduplicate_articles` and `cluster_articles_by_topic` so same-topic articles across multiple outlets are clustered with title keyword overlap (>= 2 common significant tokens or token overlap ratio >= 0.30), attaching 2 to 5 distinct outlet links to each representative.
3. Strict enforcement of **EXACTLY 3 articles per category** in Gemini prompts, candidate feeding, and fallback synthesis.

---

## 2. Requirements Catalog

### 2.1 Feed Expansion & Repair (`data/feeds.json`, `src/ingest/sources.py`)
- **R-FEED-02**: Repair DongA international feed URL to `https://rss.donga.com/international.xml`.
- **R-FEED-03**: Add verified `bot: true` feeds for Hankyoreh (politics, economy, society, international, culture), SBS (politics, economy, society, international, sports, culture), MBN (politics, economy), and NocutNews, expanding total feeds to 50+.

### 2.2 Consensus Clustering & De-duplication Reform (`src/ingest/filter.py`)
- **R-CLUSTER-01**: Ensure `deduplicate_articles` only prunes identical article IDs and normalized URLs, preserving same-topic articles from different outlets for clustering.
- **R-CLUSTER-02**: Improve topic matching in `cluster_articles_by_topic` using title token overlap (>= 2 common keywords or token overlap >= 0.30 or Jaccard >= 0.20), aggregating sibling links across all cluster members.

### 2.3 Strict 3-Article Category Quota (`src/llm/prompts.py`, `src/llm/summarizer.py`, `src/ingest/filter.py`)
- **R-QUOTA-01**: In `src/ingest/filter.py`, retain 7–8 candidate articles per category to ensure ample candidates for synthesis.
- **R-QUOTA-02**: In `src/llm/prompts.py`, mandate `EXACTLY 3 distinct stories per category`.
- **R-QUOTA-03**: In `src/llm/summarizer.py`, ensure fallback synthesis and payload normalization enforce exactly 3 articles per category.

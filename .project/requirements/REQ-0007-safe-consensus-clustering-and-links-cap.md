# REQ-0007: Safe Category-Isolated Consensus Clustering & Strict 5-Link Source Cap

Status: captured
Origin: User request / Pipeline Incident (2026-10-31)

## 1. Overview & Objectives
During the automated pipeline execution on 2026-10-31, an incident occurred where Article 15 ([지디넷코리아] *인간 중심 사이버보안 한계…AI 기반 침해 사고 급증*) was populated with 1,266 unrelated source links, inflating `data/latest.json`, `manifest.json`, and archive payloads.

The root causes identified:
1. `are_articles_same_topic` permitted single-token overlap when `min_len <= 3` due to `overlap_ratio = len(common) / min_len >= 0.30` (e.g. 1/1 = 1.0, 1/2 = 0.50, 1/3 = 0.33), causing common words like '포커스', '단독', '속보', '대통령', '한국', '1위' to link unrelated articles.
2. Union-Find transitive clustering was executed across all 2,600+ articles globally without category boundaries, causing a massive percolation event (giant connected component) that merged 1,222 articles across politics, economy, sports, obituaries, etc.
3. Neither `cluster_articles_by_topic`, `src/pipeline.py`, nor `src/llm/summarizer.py` enforced a maximum cap on `related_links` or `links`, allowing unlimited accumulation.

This requirement establishes:
1. **Category Isolation**: Clustering must be strictly partitioned by category (`category_id` or `category`). Articles from different categories must NEVER be clustered together.
2. **Safe & High-Precision Topic Similarity**:
   - Single-token matches are strictly prohibited (`len(common_tokens) >= 2` mandatory).
   - Require token Jaccard similarity >= 0.35 OR SequenceMatcher ratio >= 0.60 OR at least 2 common tokens with `overlap_ratio >= 0.40` (and `min_len >= 3`).
3. **Hard Cap on Source Links**:
   - `cluster_articles_by_topic`: Cap `rep.related_links` to at most 4 distinct outlets (`[:4]`).
   - `pipeline.py` & `summarizer.py`: Cap `item["links"]` to at most 5 total links (`[:5]`).
4. **Data Sanitization**: Cleanse contaminated `data/latest.json`, `data/archive/2026-10-31_070001.json`, and `data/archive/manifest.json`.

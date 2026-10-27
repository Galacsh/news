# PLAN-0002: Value-Added Intelligence Curation Blueprint

Status: approved
Origin: User request /goal (2026-10-26)
Related Requirements: REQ-0003, PLAN-0001

## 1. Core Problem: The Portal Mirroring Trap
Displaying raw scraped headlines from Daum News creates no differentiated value; users can simply visit Daum News directly.
The platform's value proposition must come from **transforming raw news items into structured executive intelligence** that portals intentionally do not provide.

---

## 2. The 5 Core Value-Add Pillars

1. **Multi-Perspective Matrix (시각 비교 & 팩트 분리)**:
   - For contentious national topics, group 2–3 media outlets across the spectrum.
   - Separate undisputed facts from conservative/business vs. progressive/civic framing.
2. **"So What?" 3-Point Impact Analysis (영향도 분석)**:
   - *Citizen / Pocketbook*: Impact on everyday spending, taxes, loans, living costs.
   - *Industry / Market*: Impact on corporate policy, real estate, stocks, regulation.
   - *Next Watch*: Critical upcoming dates, court rulings, or legislative votes.
3. **3-Step Context Timeline (어쩌다 여기까지 왔나?)**:
   - Provide a 3-bullet historical context explaining how the current issue originated.
4. **Jargon & Keyword Explainer (용어 1줄 친절 해설)**:
   - Hoverable/clickable plain-language definitions for complex terms (DSR, MDL, 낙찰가율 등).
5. **60-Second Executive Morning Narrative (종합 모닝 브리핑)**:
   - A single 3-paragraph executive narrative tying the day's top 5 events together into a coherent national summary.

---

## 3. Gemini Free-Tier Pipeline Integration

- Input: Pre-curated top 3 articles per category (title, press, summary, first 2 paragraphs).
- Prompt: Structured JSON output requesting:
  - `one_line_takeaway`
  - `core_facts`
  - `impact_analysis` (`citizen`, `market`, `next_watch`)
  - `perspectives` (`framing_a`, `framing_b`)
  - `jargon_explainer` (`term`, `definition`)
- Token budget: <1,500 tokens per category, staying comfortably under the 15 RPM / 1M TPM free tier limit.

---

## 4. Implementation Slice Roadmap

- **SLICE-0010**: Daum Multi-Section Scraper (`src/ingest/daum_sections.py`)
- **SLICE-0011**: Cross-Outlet Topic Clustering Engine (`src/curation/engine.py`)
- **SLICE-0012**: Value-Add Intelligence Synthesizer (`src/llm/intelligence_synthesizer.py`)
- **SLICE-0013**: Executive Intelligence Dashboard UI (`index.html`)

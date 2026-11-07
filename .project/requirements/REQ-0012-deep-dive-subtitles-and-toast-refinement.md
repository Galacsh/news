# REQ-0012: Deep Dive Subtitle Simplification & Toast Copy Refinement

Status: captured
Origin: User request (2026-11-08)

## 1. Overview & Objectives
1. **Detail Page Deep-Dive Subtitles**:
   On the article detail page (`detail.html`), deep-dive analytical sections previously used descriptive sentence-style headings (e.g., `"마케팅 빼고 진짜 바뀐 기술 본질"`, `"개발자·실무·생태계 판도 변화"`, `"왜 지금 나왔나 (숨은 셈법)"`).
   The user requested simplifying all section subheadings into concise, punchy terms across categories (e.g. `"본질"`, `"판도 변화"`).
2. **Main Page Toast Notification**:
   On the main briefing page (`index.html`), the toast notification for no new briefing data currently states:
   `"새로운 변경 사항이 없습니다. (최신 상태 유지 중)"`.
   The user requested shortening this to:
   `"새로운 변경 사항이 없습니다."`.

This requirement establishes:
1. Shorten the toast message in `index.html` to `"새로운 변경 사항이 없습니다."`.
2. Update category lens definitions in `src/llm/prompts.py` so future AI briefings generate concise section subheadings across all 10 categories.
3. In `detail.html`, add label normalization for deep dive sections so both historical archives and future articles display concise subheadings.
4. Update tests in `tests/test_archive_ui.py` and `tests/test_summarizer.py` and verify all tests pass with zero regressions.

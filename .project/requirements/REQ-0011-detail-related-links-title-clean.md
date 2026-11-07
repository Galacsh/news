# REQ-0011: Clean Related Link Titles in Detail Page

Status: captured
Origin: User request (2026-11-08)

## 1. Overview & Objectives
On the article detail page (`detail.html`), under the "언론사별 관련 보도" (Related Coverage by Press) section, each source article link displays an outlet badge (`<span class="...">${outlet}</span>`) alongside the article title.
However, because RSS feed titles and ingested links often already contain leading bracketed outlet/topic tags (e.g. `[한겨레] ...`, `[한국경제 - 라이프] ...`, `[속보] ...`), the rendered list displayed redundant and cluttered labels:
```text
[한겨레] [한겨레] 홍익표 정무수석 사의…
[한국경제] [한국경제 - 라이프] '오디세이...'
```
The user requested either hiding the outlet badge tag or removing the `[...]` prefix from the article title. The user explicitly chose Option 1: keep the outlet badge tag (`${outlet}`) and remove leading bracketed prefixes `[...]` from the article title text.

This requirement establishes:
1. In `detail.html`, strip leading bracketed prefixes (e.g., `^\[[^\]]+\]\s*`) from related link titles so that the outlet badge tag is displayed cleanly beside the actual article title.
2. In `detail.html`, improve `getOutletName` to prioritize URL hostname over generic title bracket tags (such as `[속보]`, `[단독]`, etc.) to avoid displaying non-outlet words as outlet badges.
3. Update UI tests in `tests/test_archive_ui.py` to assert that leading bracketed tags are stripped when rendering related link titles.
4. Verify all tests pass with zero regressions.

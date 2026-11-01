# REQ-0009: Detail Page Deep-Dive Section UI Copy Refinement & Tag Removal

Status: captured
Origin: User request (2026-11-01)

## 1. Overview & Objectives
In `detail.html`, the deep-dive section header currently displays:
- Title: "분야별 심층 분석"
- Subtitle: "단순 사실을 넘어 행간과 구조적 파급을 해부합니다."
- Analytical lens badge tag: `<div id="lensBadgeContainer"><span id="lensTitleBadge">...</span></div>`

The user requested refining the copy and simplifying the UI:
1. Change title "분야별 심층 분석" to "심층 분석".
2. Change subtitle "단순 사실을 넘어 행간과 구조적 파급을 해부합니다." to "분야별로 심층적으로 분석했어요.".
3. Completely remove the analytical lens badge tag (`#lensBadgeContainer` / `#lensTitleBadge`).

This requirement establishes:
1. Update `detail.html` header copy and remove the lens badge tag markup.
2. Clean up JavaScript in `detail.html` removing `#lensTitleText` manipulation.
3. Update `tests/test_archive_ui.py` assertions to ensure all tests pass.

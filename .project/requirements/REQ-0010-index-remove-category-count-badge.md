# REQ-0010: Remove Article Count Badge from Category Selection Area in Main Page

Status: captured
Origin: User request (2026-11-01)

## 1. Overview & Objectives
On the main page (`index.html`), inside the sticky category navigation bar, an article count badge (`#articleCountBadge`, e.g. "0건", "3건") is displayed next to the category title:
```text
[■] 분야별 핵심 브리핑    [3건]
[정치] [경제·금융] [산업·기업] ...
```
The user requested removing the "N건" count display from the category selection menu area on the main screen to keep the category navigation clean and consistent with the detail page.

This requirement establishes:
1. Remove `#articleCountBadge` from the sticky category header in `index.html`.
2. Clean up corresponding JavaScript code in `index.html` that updates the badge text.
3. Verify all tests pass with zero regressions.

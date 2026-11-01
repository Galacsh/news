# REQ-0008: Remove Article Count Badge from Related Articles Section in Detail Page

Status: captured
Origin: User request (2026-11-01)

## 1. Overview & Objectives
In `detail.html`, under the "언론사별 관련 보도" (Related Outlets Coverage) section, a badge displaying "총 N건" (`#articlesCountBadge`) is currently positioned on the right side of the section header:
```text
언론사별 관련 보도
다양한 언론사의 보도 원문을 직접 확인하실 수 있습니다.    [총 2건]
```
The user requested removing the "총 N건" indicator to keep the section header minimal and clean.

This requirement establishes:
1. Remove `#articlesCountBadge` from the section header in `detail.html`.
2. Clean up corresponding JavaScript code in `detail.html` that updates the badge text.
3. Update `tests/test_archive_ui.py` to ensure all DOM structure unit tests pass.

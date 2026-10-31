# REQ-0006: Mobile Header & Non-Content Responsive UI Polish

Status: captured
Origin: User request (2026-10-31)

## 1. Overview & Objectives
On mobile viewports (<= 375px), several non-content UI elements across the web pages (`index.html`, `detail.html`, `archive.html`, `notices.html`, `monitoring.html`) suffer from awkward line wraps and misaligned flex containers:
1. Header titles wrap into 3–4 broken lines or split Korean compound words awkwardly.
2. Back buttons, action buttons, category tabs, and metadata badges wrap vertically or get squished against right action button clusters.
3. Notification banners and status badges lack `whitespace-nowrap` or `shrink-0`, causing text to break mid-sentence or buttons to stack unevenly.

This requirement establishes:
1. Universal responsive header styling across all pages:
   - Font sizes scaled from mobile to desktop (`text-lg sm:text-2xl` or `text-base sm:text-xl`).
   - Korean title word-breaking prevention via `break-keep`.
   - Right action button clusters protected with `shrink-0` and fixed touch target sizes.
2. Responsive navigation and back buttons:
   - Ensuring back links and action links do not wrap awkwardly (`whitespace-nowrap`, `shrink-0`).
   - Using responsive text labels (e.g. `뉴스 브리핑` on `sm:`, `메인` on mobile) or compact labels while preserving full accessibility and test compatibility.
3. Banners, badges, and card action headers:
   - `index.html` archive banner buttons made `whitespace-nowrap shrink-0`.
   - `buildCardHTML()` category badges and "자세히 보기" action links marked with `whitespace-nowrap shrink-0`.
   - `detail.html` header category badge and back button protected from vertical collapse.
4. Full backward compatibility and zero test regressions across all test suites.

---

## 2. Requirements Catalog

### 2.1 Main Briefing UI (`index.html`)
- **R-UI-01**: In top header, apply `break-keep` and `text-lg sm:text-2xl` to `h1`, `truncate` or `break-keep` to `todayDate`, and keep action button cluster `shrink-0 gap-2`.
- **R-UI-02**: In archive notice banner, add `whitespace-nowrap shrink-0` to action links so banner text and buttons wrap cleanly as whole blocks if needed.
- **R-UI-03**: In `buildCardHTML()`, ensure category badge and "자세히 보기" action link have `whitespace-nowrap shrink-0`, and headline `h3` has `break-keep`.

### 2.2 Archive Explorer UI (`archive.html`)
- **R-UI-04**: In top header, prevent title from colliding with back button by using responsive text or abbreviation on small screens while retaining required keywords (`아카이브 탐색`), `break-keep`, and `whitespace-nowrap`.
- **R-UI-05**: Ensure right action buttons (notices, monitoring, refresh) remain `shrink-0` inline.

### 2.3 Briefing Detail UI (`detail.html`)
- **R-UI-06**: In top header, guarantee back button (`#backToMainLink`) and category badge (`#categoryBadge`) have `whitespace-nowrap shrink-0`, preventing text wrap on <=375px screens.

### 2.4 Notice Center & Monitoring Dashboard (`notices.html`, `monitoring.html`)
- **R-UI-07**: In `notices.html`, ensure back link and header title have `whitespace-nowrap shrink-0` and clean mobile layout without word breaks.
- **R-UI-08**: In `monitoring.html`, apply `break-keep` to header title and `whitespace-nowrap shrink-0` to navigation link and status badges.

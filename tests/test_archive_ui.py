"""Unit and DOM structure tests for the archive explorer page (archive.html) and index.html integration."""

import html.parser
import re
from pathlib import Path

import pytest

ARCHIVE_HTML_PATH = Path("archive.html")
INDEX_HTML_PATH = Path("index.html")


class DOMIdParser(html.parser.HTMLParser):
    """HTMLParser that collects element IDs, classes, tag names, link targets, and script contents."""

    def __init__(self) -> None:
        super().__init__()
        self.ids: set[str] = set()
        self.classes: set[str] = set()
        self.tags: set[str] = set()
        self.links: list[dict[str, str]] = []
        self.scripts: list[str] = []
        self.meta_tags: list[dict[str, str]] = []
        self._current_tag: str | None = None
        self._current_script_buffer: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.tags.add(tag)
        self._current_tag = tag
        attr_dict = {k: v or "" for k, v in attrs}

        if "id" in attr_dict:
            self.ids.add(attr_dict["id"])

        if "class" in attr_dict:
            for cls_name in attr_dict["class"].split():
                self.classes.add(cls_name)

        if tag == "a" and "href" in attr_dict:
            self.links.append(attr_dict)

        if tag == "meta":
            self.meta_tags.append(attr_dict)

        if tag == "script":
            if "src" in attr_dict:
                self.scripts.append(f"<script src='{attr_dict['src']}'>")
            self._current_script_buffer = []

    def handle_data(self, data: str) -> None:
        if self._current_tag == "script":
            self._current_script_buffer.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag == "script" and self._current_script_buffer:
            self.scripts.append("".join(self._current_script_buffer))
            self._current_script_buffer = []
        self._current_tag = None


@pytest.fixture(scope="module")
def archive_html_content() -> str:
    """Fixture to load archive.html content."""
    assert ARCHIVE_HTML_PATH.exists(), f"{ARCHIVE_HTML_PATH} does not exist."
    return ARCHIVE_HTML_PATH.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def archive_dom(archive_html_content: str) -> DOMIdParser:
    """Fixture to parse archive.html into DOM structures."""
    parser = DOMIdParser()
    parser.feed(archive_html_content)
    return parser


@pytest.fixture(scope="module")
def index_html_content() -> str:
    """Fixture to load index.html content."""
    assert INDEX_HTML_PATH.exists(), f"{INDEX_HTML_PATH} does not exist."
    return INDEX_HTML_PATH.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def index_dom(index_html_content: str) -> DOMIdParser:
    """Fixture to parse index.html into DOM structures."""
    parser = DOMIdParser()
    parser.feed(index_html_content)
    return parser


def test_archive_html_exists(archive_html_content: str):
    """Verify archive.html exists, has content, and starts with <!doctype html>."""
    assert len(archive_html_content.strip()) > 0
    assert archive_html_content.strip().lower().startswith("<!doctype html>")


def test_archive_html_head_and_cdns(archive_dom: DOMIdParser, archive_html_content: str):
    """Verify HTML5 standards, viewport meta, Tailwind CSS, and Phosphor Icons CDNs."""
    # Viewport meta tag
    has_viewport = any(
        m.get("name") == "viewport" and "width=device-width" in m.get("content", "")
        for m in archive_dom.meta_tags
    )
    assert has_viewport, "Missing standard viewport meta tag in archive.html"

    # Charset meta tag
    has_charset = any("charset" in m for m in archive_dom.meta_tags)
    assert has_charset, "Missing charset meta tag in archive.html"

    # Tailwind CSS CDN
    has_tailwind = any("cdn.tailwindcss.com" in s for s in archive_dom.scripts)
    assert has_tailwind, "Missing Tailwind CSS CDN script tag in archive.html"

    # Phosphor Icons CDN
    has_phosphor = any("@phosphor-icons/web" in s for s in archive_dom.scripts)
    assert has_phosphor, "Missing Phosphor Icons CDN script tag in archive.html"

    # Pretendard font extension in Tailwind configuration
    assert "Pretendard" in archive_html_content

    # Dark slate theme classes
    assert "bg-slate-950" in archive_dom.classes
    assert "text-slate-100" in archive_dom.classes


def test_archive_html_header_and_navigation(archive_dom: DOMIdParser, archive_html_content: str):
    """Verify header title, back link to index.html, refresh button, notices, and monitoring links."""
    assert "아카이브 탐색" in archive_html_content

    # Back to index.html link
    assert "backToLatestLink" in archive_dom.ids
    back_links = [l for l in archive_dom.links if l.get("id") == "backToLatestLink"]
    assert len(back_links) == 1
    assert back_links[0].get("href") == "index.html"

    # Refresh button
    assert "refreshBtn" in archive_dom.ids

    # Notice center and monitoring navigation links
    has_notices_link = any(l.get("href") == "notices.html" for l in archive_dom.links)
    assert has_notices_link, "archive.html must include link to notices.html"

    has_monitoring_link = any(l.get("href") == "monitoring.html" for l in archive_dom.links)
    assert has_monitoring_link, "archive.html must include link to monitoring.html"


def test_archive_html_calendar_components(archive_dom: DOMIdParser, archive_html_content: str):
    """Verify calendar container, month navigation buttons, month label, and grid container."""
    assert "calendarContainer" in archive_dom.ids or "calendarView" in archive_dom.ids
    assert "prevMonthBtn" in archive_dom.ids
    assert "nextMonthBtn" in archive_dom.ids
    assert "currentMonthLabel" in archive_dom.ids
    assert "calendarGrid" in archive_dom.ids

    # Weekday labels present
    for day_label in ["일", "월", "화", "수", "목", "금", "토"]:
        assert day_label in archive_html_content


def test_archive_html_briefings_and_intra_day_elements(archive_dom: DOMIdParser):
    """Verify briefings container, runsList, selected date heading, reset filter button, and states."""
    assert "briefingsContainer" in archive_dom.ids
    assert "runsList" in archive_dom.ids
    assert "selectedDateHeading" in archive_dom.ids
    assert "resetFilterBtn" in archive_dom.ids
    assert "loadingState" in archive_dom.ids
    assert "emptyState" in archive_dom.ids


def test_archive_html_javascript_logic(archive_html_content: str):
    """Verify JS handles data/archive/manifest.json, grouping, intra-day multiple runs, and index navigation."""
    # Manifest endpoint
    assert "data/archive/manifest.json" in archive_html_content

    # Cache busting logic
    assert "Date.now()" in archive_html_content or "_t=" in archive_html_content

    # Key functions
    assert "loadManifest" in archive_html_content
    assert "renderCalendar" in archive_html_content
    assert "renderBriefings" in archive_html_content
    assert "selectDate" in archive_html_content
    assert "resetDateFilter" in archive_html_content

    # Target briefing link to index.html?archive=
    assert "index.html?archive=" in archive_html_content

    # URL query param support for date and archive
    assert "URLSearchParams" in archive_html_content
    assert 'urlParams.get("date")' in archive_html_content or "urlParams.get('date')" in archive_html_content
    assert 'urlParams.get("archive")' in archive_html_content or "urlParams.get('archive')" in archive_html_content


def test_index_html_archive_link(index_dom: DOMIdParser, index_html_content: str):
    """Verify that index.html contains archive link pointing to archive.html with calendar icon."""
    assert "archiveLink" in index_dom.ids

    archive_links = [l for l in index_dom.links if l.get("id") == "archiveLink"]
    assert len(archive_links) == 1
    assert archive_links[0].get("href") == "archive.html"

    # Header section contains archiveLink
    header_match = re.search(r"<header.*?</header>", index_html_content, re.DOTALL)
    assert header_match, "index.html must have <header>"
    assert 'id="archiveLink"' in header_match.group(0)

    # Contains calendar icon
    assert "ph-calendar" in index_html_content


def test_index_html_fetch_latest_data_archive_support(index_html_content: str):
    """Verify fetchLatestData in index.html checks both archive and date query params."""
    assert "fetchLatestData" in index_html_content

    # Checks archive parameter
    assert 'urlParams.get("archive")' in index_html_content or "urlParams.get('archive')" in index_html_content

    # Checks date parameter
    assert 'urlParams.get("date")' in index_html_content or "urlParams.get('date')" in index_html_content

    # Formats target URL into data/archive/
    assert "data/archive/" in index_html_content


def test_index_html_archive_banner(index_dom: DOMIdParser, index_html_content: str):
    """Verify index.html contains archiveNoticeBanner with default hidden state and link to index.html."""
    assert "archiveNoticeBanner" in index_dom.ids

    # Banner default hidden
    assert re.search(r'id=["\']archiveNoticeBanner["\'][^>]*class=["\'][^"\']*hidden', index_html_content) or \
           re.search(r'class=["\'][^"\']*hidden[^"\']*["\'][^>]*id=["\']archiveNoticeBanner["\']', index_html_content)

    # Link back to latest briefing (index.html)
    assert 'href="index.html"' in index_html_content
    assert "최신 브리핑 보기" in index_html_content


def test_intra_day_runs_simulation():
    """Unit test simulating grouping and filtering multiple runs on the same date."""
    manifest_archives = [
        {
            "filename": "2026-10-25_180000.json",
            "date": "2026-10-25",
            "time": "18:00:00",
            "briefingDate": "2026-10-25T18:00:00+00:00",
            "topHeadlines": [{"headline": "저녁 긴급 속보"}],
            "totalArticles": 12,
        },
        {
            "filename": "2026-10-25_090000.json",
            "date": "2026-10-25",
            "time": "09:00:00",
            "briefingDate": "2026-10-25T09:00:00+00:00",
            "topHeadlines": [{"headline": "아침 브리핑"}],
            "totalArticles": 10,
        },
        {
            "filename": "2026-10-24.json",
            "date": "2026-10-24",
            "time": "",
            "briefingDate": "2026-10-24T10:00:00+00:00",
            "topHeadlines": [{"headline": "전일 브리핑"}],
            "totalArticles": 8,
        },
    ]

    # Group by date
    grouped: dict[str, list] = {}
    for entry in manifest_archives:
        grouped.setdefault(entry["date"], []).append(entry)

    # Verify intra-day grouping: 2026-10-25 has 2 runs
    assert len(grouped["2026-10-25"]) == 2
    assert grouped["2026-10-25"][0]["time"] == "18:00:00"
    assert grouped["2026-10-25"][1]["time"] == "09:00:00"

    # Single run on 2026-10-24
    assert len(grouped["2026-10-24"]) == 1
    assert grouped["2026-10-24"][0]["filename"] == "2026-10-24.json"

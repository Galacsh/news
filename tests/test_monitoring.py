"""Tests for pipeline telemetry & collection reporting dashboard (monitoring.html)."""

import html.parser
import re
from pathlib import Path

import pytest

MONITORING_HTML_PATH = Path("monitoring.html")


class DOMIdParser(html.parser.HTMLParser):
    """HTMLParser that collects element IDs, tag names, link targets, and script contents."""

    def __init__(self) -> None:
        super().__init__()
        self.ids: set[str] = set()
        self.classes: set[str] = set()
        self.tags: set[str] = set()
        self.links: list[dict[str, str]] = []
        self.scripts: list[str] = []
        self.meta_tags: list[dict[str, str]] = []
        self.elements_by_id: dict[str, dict[str, str]] = {}
        self._current_tag: str | None = None
        self._current_script_buffer: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.tags.add(tag)
        self._current_tag = tag
        attr_dict = {k: v or "" for k, v in attrs}

        if "id" in attr_dict:
            self.ids.add(attr_dict["id"])
            self.elements_by_id[attr_dict["id"]] = attr_dict

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
def html_content() -> str:
    """Fixture to load monitoring.html content."""
    assert MONITORING_HTML_PATH.exists(), f"{MONITORING_HTML_PATH} does not exist."
    return MONITORING_HTML_PATH.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def parsed_dom(html_content: str) -> DOMIdParser:
    """Fixture to parse monitoring.html into DOM structures."""
    parser = DOMIdParser()
    parser.feed(html_content)
    return parser


def test_monitoring_html_exists(html_content: str):
    """Verify monitoring.html exists and is not empty."""
    assert len(html_content.strip()) > 0
    assert html_content.strip().lower().startswith("<!doctype html>")


def test_html5_meta_and_cdn_assets(parsed_dom: DOMIdParser, html_content: str):
    """Verify HTML5 document standards, viewport meta, Tailwind CSS and Phosphor Icons CDNs."""
    # Viewport meta tag
    has_viewport = any(
        m.get("name") == "viewport" and "width=device-width" in m.get("content", "")
        for m in parsed_dom.meta_tags
    )
    assert has_viewport, "Missing standard viewport meta tag in monitoring.html"

    # Charset meta tag
    has_charset = any("charset" in m for m in parsed_dom.meta_tags)
    assert has_charset, "Missing charset meta tag in monitoring.html"

    # Tailwind CSS CDN
    has_tailwind = any("cdn.tailwindcss.com" in s for s in parsed_dom.scripts)
    assert has_tailwind, "Missing Tailwind CSS CDN script tag"

    # Phosphor Icons CDN
    has_phosphor = any("@phosphor-icons/web" in s for s in parsed_dom.scripts)
    assert has_phosphor, "Missing Phosphor Icons CDN script tag"

    # Slate dark theme styling classes
    assert "bg-slate-950" in parsed_dom.classes
    assert "text-slate-100" in parsed_dom.classes


def test_header_and_navigation(parsed_dom: DOMIdParser, html_content: str):
    """Verify header title, timestamp display, status badge, index.html navigation, and refresh button."""
    assert "파이프라인 모니터링 & 수집 현황 대시보드" in html_content

    # Header h1 contains break-keep
    h1_match = re.search(r"<h1[^>]*class=['\"]([^'\"]*)['\"][^>]*>", html_content)
    assert h1_match, "monitoring.html must contain an <h1> tag"
    assert "break-keep" in h1_match.group(1).split(), "monitoring.html <h1> must contain break-keep class"

    # Essential Header DOM element IDs
    assert "telemetryTimestamp" in parsed_dom.ids
    assert "overallStatusBadge" in parsed_dom.ids
    assert "refreshBtn" in parsed_dom.ids

    # #overallStatusBadge contains whitespace-nowrap
    badge_el = parsed_dom.elements_by_id.get("overallStatusBadge", {})
    badge_classes = badge_el.get("class", "").split()
    assert "whitespace-nowrap" in badge_classes, "#overallStatusBadge must contain whitespace-nowrap class"

    # Navigation back to index.html with whitespace-nowrap
    index_links = [link for link in parsed_dom.links if link.get("href") == "index.html"]
    assert len(index_links) >= 1, "Missing navigation link with href='index.html'"
    index_nav_classes = index_links[0].get("class", "").split()
    assert "whitespace-nowrap" in index_nav_classes, "index.html navigation button must contain whitespace-nowrap class"


def test_summary_metric_cards(parsed_dom: DOMIdParser):
    """Verify the 4 required ingestion funnel and metric summary cards exist."""
    assert "feedsSummary" in parsed_dom.ids
    assert "funnelSummary" in parsed_dom.ids
    assert "geminiSummary" in parsed_dom.ids
    assert "pipelineLatencySummary" in parsed_dom.ids


def test_category_breakdown_visualizer(parsed_dom: DOMIdParser, html_content: str):
    """Verify category breakdown container exists and includes default categories."""
    assert "categoryBreakdown" in parsed_dom.ids
    for category in ["정치", "경제·금융", "IT·과학", "사회", "문화·생활", "국제", "기타"]:
        assert category in html_content


def test_feed_status_table_structure(parsed_dom: DOMIdParser, html_content: str):
    """Verify per-feed collection status table and required column headers."""
    assert "feedStatusTable" in parsed_dom.ids
    assert "feedTableBody" in parsed_dom.ids

    headers = ["언론사", "카테고리", "피드 URL", "상태", "수집 건수", "응답 시간", "오류"]
    for header in headers:
        assert header in html_content, f"Missing expected table column header: {header}"


def test_error_and_loading_states(parsed_dom: DOMIdParser):
    """Verify loading indicator and error container for graceful degradation."""
    assert "loadingState" in parsed_dom.ids
    assert "errorMessage" in parsed_dom.ids


def test_javascript_telemetry_fetch_and_render_logic(html_content: str):
    """Verify JS script block contains fetch logic for latest.json and telemetry fields processing."""
    # Fetch endpoint
    assert "data/telemetry/latest.json" in html_content

    # Error handling in fetch
    assert "catch" in html_content
    assert "response.ok" in html_content or "status" in html_content

    # Telemetry fields rendered
    expected_fields = [
        "timestamp",
        "date",
        "feeds_attempted",
        "feeds_failed",
        "raw_articles_count",
        "filtered_count",
        "gemini_latency_ms",
        "gemini_fallback_used",
        "category_breakdown",
        "feed_status",
        "pipeline_latency_ms",
    ]
    for field in expected_fields:
        assert field in html_content, f"Missing telemetry field processing in JS: {field}"

    # Overall health badge logic
    assert "정상 가동 (Healthy)" in html_content
    assert "주의 / 오류 (Degraded)" in html_content

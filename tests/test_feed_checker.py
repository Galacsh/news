"""Unit tests for automated RSS feed health checker utility."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import io
import json
import socket
from typing import Any
import urllib.error
import urllib.request
from unittest.mock import MagicMock, patch

import pytest

from src.ingest.models import Article, FeedSource
from src.tools.feed_checker import FeedHealthChecker, FeedHealthResult, main


# Sample RSS XML fixtures
SAMPLE_HEALTHY_RSS = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>테크 데일리</title>
    <link>https://tech.example.com</link>
    <description>최신 기술 뉴스 피드</description>
    <item>
      <title>인공지능 모델 혁신 발표</title>
      <link>https://tech.example.com/articles/101</link>
      <description>새로운 LLM 아키텍처 공개</description>
      <pubDate>{pub_date}</pubDate>
      <category>AI·빅테크</category>
    </item>
    <item>
      <title>차세대 반도체 공정 양산</title>
      <link>https://tech.example.com/articles/102</link>
      <description>2나노 파운드리 가동 시작</description>
      <pubDate>{pub_date_old}</pubDate>
      <category>반도체</category>
    </item>
  </channel>
</rss>
"""

SAMPLE_EMPTY_RSS = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>빈 피드</title>
    <link>https://empty.example.com</link>
    <description>항목이 없는 피드</description>
  </channel>
</rss>
"""

SAMPLE_NO_DATES_RSS = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>날짜 없는 피드</title>
    <link>https://nodates.example.com</link>
    <item>
      <title>기사 제목 1</title>
      <link>https://nodates.example.com/1</link>
      <description>기사 본문 1</description>
    </item>
  </channel>
</rss>
"""


def _make_mock_response(content: str | bytes, status: int = 200) -> MagicMock:
    """Helper to create a mock urllib response context manager."""
    data = content.encode("utf-8") if isinstance(content, str) else content
    mock_resp = MagicMock()
    mock_resp.read.return_value = data
    mock_resp.status = status
    mock_resp.getcode.return_value = status
    mock_resp.__enter__.return_value = mock_resp
    mock_resp.__exit__.return_value = None
    return mock_resp


# ============================================================================
# 1. FeedHealthResult Dataclass Unit Tests
# ============================================================================


def test_feed_health_result_dataclass_and_to_dict():
    """Verify FeedHealthResult fields, defaults, and dictionary export."""
    res = FeedHealthResult(
        url="https://example.com/rss.xml",
        name="연합뉴스 - 정치",
        outlet="연합뉴스",
        category="정치",
        category_id=1,
        status="healthy",
        http_code=200,
        latency_ms=120.5,
        item_count=15,
        latest_published_at="2026-10-25T12:00:00+00:00",
        error=None,
        is_recommended=True,
    )

    assert res.url == "https://example.com/rss.xml"
    assert res.name == "연합뉴스 - 정치"
    assert res.outlet == "연합뉴스"
    assert res.category == "정치"
    assert res.category_id == 1
    assert res.status == "healthy"
    assert res.http_code == 200
    assert res.latency_ms == 120.5
    assert res.item_count == 15
    assert res.latest_published_at == "2026-10-25T12:00:00+00:00"
    assert res.error is None
    assert res.is_recommended is True

    d = res.to_dict()
    assert isinstance(d, dict)
    assert d["url"] == "https://example.com/rss.xml"
    assert d["category_id"] == 1
    assert d["status"] == "healthy"
    assert d["is_recommended"] is True


# ============================================================================
# 2. FeedHealthChecker Single Feed Check Tests
# ============================================================================


def test_check_feed_healthy_success():
    """Verify healthy feed with 200 OK, valid XML, and fresh articles."""
    now = datetime.now(timezone.utc)
    recent_date = (now - timedelta(hours=2)).strftime("%a, %d %b %Y %H:%M:%S +0000")
    older_date = (now - timedelta(days=1)).strftime("%a, %d %b %Y %H:%M:%S +0000")
    xml_content = SAMPLE_HEALTHY_RSS.format(pub_date=recent_date, pub_date_old=older_date)

    mock_resp = _make_mock_response(xml_content, status=200)

    checker = FeedHealthChecker(timeout=5.0, max_age_days=30)

    # Test with dict input
    feed_dict = {
        "name": "테크 데일리 - AI",
        "url": "https://tech.example.com/rss.xml",
        "category": "AI·빅테크",
        "categoryId": 7,
    }

    with patch("urllib.request.urlopen", return_value=mock_resp):
        res = checker.check_feed(feed_dict)

    assert res.status == "healthy"
    assert res.http_code == 200
    assert res.item_count == 2
    assert res.is_recommended is True
    assert res.error is None
    assert res.category == "AI·빅테크"
    assert res.category_id == 7
    assert res.outlet == "테크 데일리"
    assert res.latest_published_at is not None


def test_check_feed_inputs_feed_source_and_string():
    """Verify input normalization with FeedSource object and raw string URL."""
    now = datetime.now(timezone.utc)
    recent_date = now.strftime("%a, %d %b %Y %H:%M:%S +0000")
    xml_content = SAMPLE_HEALTHY_RSS.format(pub_date=recent_date, pub_date_old=recent_date)

    checker = FeedHealthChecker(timeout=5.0)

    # FeedSource input
    feed_source = FeedSource(
        name="동아일보 - IT",
        url="https://donga.com/rss/it.xml",
        category="IT·통신",
        category_id=4,
    )
    with patch("urllib.request.urlopen", return_value=_make_mock_response(xml_content)):
        res_source = checker.check_feed(feed_source)
    assert res_source.status == "healthy"
    assert res_source.name == "동아일보 - IT"
    assert res_source.outlet == "동아일보"
    assert res_source.category_id == 4

    # String URL input
    with patch("urllib.request.urlopen", return_value=_make_mock_response(xml_content)):
        res_str = checker.check_feed("https://donga.com/rss/it.xml")
    assert res_str.status == "healthy"
    assert res_str.url == "https://donga.com/rss/it.xml"


def test_check_feed_missing_or_empty_url():
    """Verify empty or missing URL returns unhealthy status immediately without network call."""
    checker = FeedHealthChecker()

    res_empty_str = checker.check_feed("")
    assert res_empty_str.status == "unhealthy"
    assert res_empty_str.error == "Missing or empty feed URL"
    assert res_empty_str.is_recommended is False

    res_empty_dict = checker.check_feed({"url": "   ", "name": "No URL"})
    assert res_empty_dict.status == "unhealthy"
    assert res_empty_dict.error == "Missing or empty feed URL"


def test_check_feed_http_error_handling():
    """Verify HTTP errors (404 Not Found, 500 Server Error) produce unhealthy results."""
    checker = FeedHealthChecker()
    url = "https://example.com/missing.xml"

    # 404 Not Found
    http_404 = urllib.error.HTTPError(url, 404, "Not Found", {}, None)  # type: ignore[arg-type]
    with patch("urllib.request.urlopen", side_effect=http_404):
        res_404 = checker.check_feed(url)

    assert res_404.status == "unhealthy"
    assert res_404.http_code == 404
    assert res_404.is_recommended is False
    assert "HTTP 404" in (res_404.error or "")

    # 500 Internal Server Error
    http_500 = urllib.error.HTTPError(url, 500, "Internal Server Error", {}, None)  # type: ignore[arg-type]
    with patch("urllib.request.urlopen", side_effect=http_500):
        res_500 = checker.check_feed(url)

    assert res_500.status == "unhealthy"
    assert res_500.http_code == 500
    assert "HTTP 500" in (res_500.error or "")


def test_check_feed_network_and_timeout_errors():
    """Verify network connectivity issues and socket timeouts are cleanly handled."""
    checker = FeedHealthChecker()
    url = "https://example.com/unreachable.xml"

    # URLError
    url_err = urllib.error.URLError("Connection refused")
    with patch("urllib.request.urlopen", side_effect=url_err):
        res_url = checker.check_feed(url)
    assert res_url.status == "unhealthy"
    assert "Connection refused" in (res_url.error or "")

    # TimeoutError
    with patch("urllib.request.urlopen", side_effect=TimeoutError("timed out")):
        res_timeout = checker.check_feed(url)
    assert res_timeout.status == "unhealthy"
    assert "Timeout" in (res_timeout.error or "")

    # socket.timeout
    with patch("urllib.request.urlopen", side_effect=socket.timeout("socket read timeout")):
        res_socket = checker.check_feed(url)
    assert res_socket.status == "unhealthy"
    assert "Timeout" in (res_socket.error or "")

    # Generic Exception
    with patch("urllib.request.urlopen", side_effect=RuntimeError("Unexpected boom")):
        res_gen = checker.check_feed(url)
    assert res_gen.status == "unhealthy"
    assert "Unexpected boom" in (res_gen.error or "")


def test_check_feed_empty_or_malformed_xml():
    """Verify empty feeds or malformed XML without items produce unhealthy status."""
    checker = FeedHealthChecker()

    # Valid XML structure but 0 items
    mock_empty = _make_mock_response(SAMPLE_EMPTY_RSS, status=200)
    with patch("urllib.request.urlopen", return_value=mock_empty):
        res_empty = checker.check_feed("https://example.com/empty.xml")

    assert res_empty.status == "unhealthy"
    assert res_empty.item_count == 0
    assert res_empty.is_recommended is False
    assert "Empty feed items" in (res_empty.error or "")

    # Corrupt XML payload
    mock_corrupt = _make_mock_response(b"<invalid<<>xml>>", status=200)
    with patch("urllib.request.urlopen", return_value=mock_corrupt):
        res_corrupt = checker.check_feed("https://example.com/corrupt.xml")

    assert res_corrupt.status == "unhealthy"
    assert res_corrupt.item_count == 0


def test_check_feed_stale_dates_detection():
    """Verify stale dates trigger warning or unhealthy status based on threshold."""
    now = datetime.now(timezone.utc)
    checker = FeedHealthChecker(max_age_days=30)

    # 1. Moderately stale: 45 days old (> 30 days, <= 90 days) -> warning
    stale_45 = (now - timedelta(days=45)).strftime("%a, %d %b %Y %H:%M:%S +0000")
    xml_stale = SAMPLE_HEALTHY_RSS.format(pub_date=stale_45, pub_date_old=stale_45)
    with patch("urllib.request.urlopen", return_value=_make_mock_response(xml_stale)):
        res_warning = checker.check_feed("https://example.com/stale.xml")

    assert res_warning.status == "warning"
    assert res_warning.is_recommended is False
    assert "Stale feed" in (res_warning.error or "")

    # 2. Severely stale: 150 days old (> 3 * 30 days) -> unhealthy
    stale_150 = (now - timedelta(days=150)).strftime("%a, %d %b %Y %H:%M:%S +0000")
    xml_severely_stale = SAMPLE_HEALTHY_RSS.format(pub_date=stale_150, pub_date_old=stale_150)
    with patch("urllib.request.urlopen", return_value=_make_mock_response(xml_severely_stale)):
        res_unhealthy = checker.check_feed("https://example.com/ancient.xml")

    assert res_unhealthy.status == "unhealthy"
    assert res_unhealthy.is_recommended is False
    assert "Severely stale" in (res_unhealthy.error or "")

    # 3. Missing explicit publication dates -> warning
    with patch("urllib.request.urlopen", return_value=_make_mock_response(SAMPLE_NO_DATES_RSS)):
        res_nodates = checker.check_feed("https://example.com/nodates.xml")

    assert res_nodates.status == "warning"
    assert res_nodates.is_recommended is False
    assert "lack explicit publication dates" in (res_nodates.error or "")


def test_check_feed_high_latency_warning():
    """Verify high response latency (>5000ms) marks feed as warning."""
    now = datetime.now(timezone.utc)
    recent_date = now.strftime("%a, %d %b %Y %H:%M:%S +0000")
    xml_content = SAMPLE_HEALTHY_RSS.format(pub_date=recent_date, pub_date_old=recent_date)

    checker = FeedHealthChecker(timeout=10.0)

    # Simulate latency > 5000ms via time.perf_counter progression
    counter_values = [10.0, 15.2]  # delta = 5.2s = 5200ms
    with (
        patch("time.perf_counter", side_effect=counter_values),
        patch("urllib.request.urlopen", return_value=_make_mock_response(xml_content)),
    ):
        res = checker.check_feed("https://example.com/slow.xml")

    assert res.status == "warning"
    assert res.latency_ms >= 5000.0
    assert res.is_recommended is False
    assert "High latency" in (res.error or "")


# ============================================================================
# 3. Batch Catalog & Concurrency Tests
# ============================================================================


def test_check_feed_catalog_batch():
    """Verify check_feed_catalog processes multiple feeds concurrently while preserving order."""
    checker = FeedHealthChecker()

    feed_list = [
        {"name": f"Feed {i}", "url": f"https://example.com/{i}.xml"}
        for i in range(5)
    ]

    mock_result_map = {
        f["url"]: FeedHealthResult(
            url=f["url"],
            name=f["name"],
            status="healthy" if i % 2 == 0 else "unhealthy",
            item_count=10 if i % 2 == 0 else 0,
            is_recommended=i % 2 == 0,
        )
        for i, f in enumerate(feed_list)
    }

    with patch.object(checker, "check_feed", side_effect=lambda f: mock_result_map[f["url"]]):
        results = checker.check_feed_catalog(feed_list, max_workers=3)

    assert len(results) == 5
    for i, res in enumerate(results):
        assert res.url == f"https://example.com/{i}.xml"
        assert res.name == f"Feed {i}"

    # Empty catalog returns empty list
    assert checker.check_feed_catalog([]) == []

    # Single item catalog
    with patch.object(checker, "check_feed", side_effect=lambda f: mock_result_map[f["url"]]):
        single_res = checker.check_feed_catalog([feed_list[0]], max_workers=1)
    assert len(single_res) == 1


# ============================================================================
# 4. Recommendation & Filtering Tests
# ============================================================================


def test_recommend_feeds_filtering_and_ranking():
    """Verify recommendation logic filters by health, min items, category, and ranks by items/latency."""
    results = [
        FeedHealthResult(
            url="https://example.com/ai_low.xml",
            name="AI Low Activity",
            category="AI·빅테크",
            status="healthy",
            item_count=3,
            latency_ms=100.0,
            is_recommended=True,
        ),
        FeedHealthResult(
            url="https://example.com/ai_high.xml",
            name="AI High Activity",
            category="AI·빅테크",
            status="healthy",
            item_count=20,
            latency_ms=250.0,
            is_recommended=True,
        ),
        FeedHealthResult(
            url="https://example.com/it.xml",
            name="IT Daily",
            category="IT·통신",
            status="healthy",
            item_count=10,
            latency_ms=150.0,
            is_recommended=True,
        ),
        FeedHealthResult(
            url="https://example.com/stale.xml",
            name="Stale Feed",
            category="AI·빅테크",
            status="warning",
            item_count=5,
            latency_ms=80.0,
            is_recommended=False,
        ),
        FeedHealthResult(
            url="https://example.com/broken.xml",
            name="Broken Feed",
            category="AI·빅테크",
            status="unhealthy",
            item_count=0,
            latency_ms=0.0,
            is_recommended=False,
        ),
        FeedHealthResult(
            url="https://example.com/empty_healthy.xml",
            name="Zero Items Healthy",
            category="IT·통신",
            status="healthy",
            item_count=0,
            latency_ms=90.0,
            is_recommended=False,
        ),
    ]

    # Global recommendations (min_items=1)
    all_recs = FeedHealthChecker.recommend_feeds(results, min_items=1)
    assert len(all_recs) == 3
    # Top ranked should have highest item count
    assert all_recs[0].name == "AI High Activity"
    assert all_recs[1].name == "IT Daily"
    assert all_recs[2].name == "AI Low Activity"

    # Category filtered recommendations
    ai_recs = FeedHealthChecker.recommend_feeds(results, category="AI·빅테크", min_items=1)
    assert len(ai_recs) == 2
    assert ai_recs[0].name == "AI High Activity"
    assert ai_recs[1].name == "AI Low Activity"

    # Non-existent category
    assert FeedHealthChecker.recommend_feeds(results, category="문화·예술") == []

    # High min_items threshold
    strict_recs = FeedHealthChecker.recommend_feeds(results, min_items=15)
    assert len(strict_recs) == 1
    assert strict_recs[0].name == "AI High Activity"


# ============================================================================
# 5. CLI Entrypoint Tests
# ============================================================================


def test_main_cli_execution_and_file_io(tmp_path):
    """Verify CLI main entrypoint arguments, file reading, limit, output writing, and exit codes."""
    candidate_catalog = {
        "description": "Candidate Feeds",
        "feeds": [
            {
                "name": "연합뉴스 - 정치",
                "outlet": "연합뉴스",
                "title": "정치",
                "url": "https://example.com/pol.xml",
                "category": "정치",
            },
            {
                "name": "전자신문 - IT",
                "outlet": "전자신문",
                "title": "IT",
                "url": "https://example.com/it.xml",
                "category": "IT·통신",
            },
            {
                "name": "매일경제 - 경제",
                "outlet": "매일경제",
                "title": "경제",
                "url": "https://example.com/eco.xml",
                "category": "경제·금융",
            },
        ],
    }

    input_file = tmp_path / "candidates.json"
    input_file.write_text(json.dumps(candidate_catalog, ensure_ascii=False), encoding="utf-8")

    output_file = tmp_path / "results.json"

    # Mock check_feed to avoid live network calls
    def mock_check(feed):
        url = feed.get("url", "")
        return FeedHealthResult(
            url=url,
            name=feed.get("name", ""),
            category=feed.get("category", ""),
            status="healthy",
            item_count=5,
            is_recommended=True,
        )

    with patch.object(FeedHealthChecker, "check_feed", side_effect=mock_check):
        exit_code = main([
            "--input", str(input_file),
            "--output", str(output_file),
            "--limit", "2",
        ])

    assert exit_code == 0
    assert output_file.exists()

    saved_data = json.loads(output_file.read_text(encoding="utf-8"))
    assert len(saved_data) == 2
    assert saved_data[0]["url"] == "https://example.com/pol.xml"
    assert saved_data[1]["url"] == "https://example.com/it.xml"


def test_main_cli_category_filter_and_recommend_only(tmp_path):
    """Verify CLI category pre-filtering and --recommend-only flag."""
    candidates = [
        {"name": "IT Feed 1", "url": "https://example.com/it1.xml", "category": "IT·통신"},
        {"name": "Econ Feed 1", "url": "https://example.com/eco1.xml", "category": "경제·금융"},
    ]
    input_file = tmp_path / "feeds_list.json"
    input_file.write_text(json.dumps(candidates, ensure_ascii=False), encoding="utf-8")
    output_file = tmp_path / "recs.json"

    def mock_check(feed):
        return FeedHealthResult(
            url=feed["url"],
            name=feed["name"],
            category=feed["category"],
            status="healthy",
            item_count=10,
            is_recommended=True,
        )

    with patch.object(FeedHealthChecker, "check_feed", side_effect=mock_check):
        exit_code = main([
            "--input", str(input_file),
            "--output", str(output_file),
            "--category", "IT",
            "--recommend-only",
        ])

    assert exit_code == 0
    saved_data = json.loads(output_file.read_text(encoding="utf-8"))
    assert len(saved_data) == 1
    assert saved_data[0]["name"] == "IT Feed 1"


def test_main_cli_nonexistent_input_error(tmp_path):
    """Verify non-existent input file gracefully returns exit code 1."""
    nonexistent = tmp_path / "does_not_exist.json"
    exit_code = main(["--input", str(nonexistent)])
    assert exit_code == 1

"""Unit tests for Daum News scraper, parsing, article conversion, and CLI."""

from __future__ import annotations

import io
import json
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest

from src.ingest.daum import (
    DEFAULT_DAUM_URL,
    KST,
    DaumNewsScraper,
    DaumScrapeError,
    format_json_output,
    format_text_output,
    main,
    parse_relative_time,
)
from src.ingest.models import Article

SAMPLE_DAUM_HTML = """
<!DOCTYPE html>
<html lang="ko">
<head><meta charset="utf-8"><title>다음 뉴스</title></head>
<body>
<div class="box_headline">
  <!-- Headline 2 Item with picture and description -->
  <a class="item_newsheadline2" href="https://v.daum.net/v/20261025224200955" data-title="%EB%8C%80%ED%91%9C%ED%97%A4%EB%93%9C%EB%9D%BC%EC%9D%B8">
    <div class="wrap_thumb">
      <picture>
        <source srcset="//img1.daumcdn.net/thumb/S686x440.jpg?fname=https%3A%2F%2Fexample.com%2Fpic1.jpg 1x, //img1.daumcdn.net/thumb/pic1_2x.jpg 2x">
        <img alt="" class="img_g">
      </picture>
    </div>
    <div class="cont_thumb">
      <strong class="tit_txt">“북한 자주포 최전방 포착”…접경지 긴장 고조</strong>
      <p class="desc_txt">서부전선 접경지역에 북한군 자주포가 불과 1.5㎞ 거리에 전진 배치된 모습이 포착됐다.</p>
      <span class="info_txt">
        <span class="con_txt">
          <span class="txt_info">매일경제</span>
          <span class="txt_info">1시간 전</span>
        </span>
      </span>
    </div>
  </a>

  <!-- Basic Item with data-title fallback and img thumbnail -->
  <a class="item_newsbasic" href="https://v.daum.net/v/20261025191222025" data-title="%EC%86%90%EC%84%9D%ED%9D%AC%20%EC%A0%80%EB%84%90%EB%A6%AC%EC%A6%98%20%EA%B0%80%EC%B9%98%20%EC%97%AC%EC%A0%84">
    <div class="wrap_thumb">
      <img src="//img2.daumcdn.net/thumb/basic_thumb.png" alt="썸네일" class="img_g">
    </div>
    <div class="cont_thumb">
      <strong class="tit_txt">손석희 저널리즘 가치 여전</strong>
      <p class="desc_txt">저널리즘의 가치와 언론의 역할에 대한 심층 인터뷰가 공개됐다.</p>
      <span class="info_txt">
        <span class="txt_info">오마이뉴스</span>
        <span class="txt_info">5분 전</span>
      </span>
    </div>
  </a>

  <!-- Item without tit_txt: relies on data-title -->
  <a class="item_newsbasic" href="https://v.daum.net/v/20261025150000123" data-title="%EA%B0%80%EC%83%81%EC%9E%90%EC%82%B0%20%EA%B3%BC%EC%84%B8%20%EC%9C%A0%EC%98%88">
    <div class="cont_thumb">
      <span class="info_txt">
        <span class="txt_info">연합뉴스</span>
        <span class="txt_info">어제</span>
      </span>
    </div>
  </a>

  <!-- Duplicate of the first article to test deduplication -->
  <a class="item_newsheadline2" href="https://v.daum.net/v/20261025224200955">
    <div class="cont_thumb">
      <strong class="tit_txt">“북한 자주포 최전방 포착”…접경지 긴장 고조</strong>
      <span class="info_txt">
        <span class="txt_info">매일경제</span>
        <span class="txt_info">1시간 전</span>
      </span>
    </div>
  </a>

  <!-- Unrelated anchor that should NOT be parsed as headline -->
  <a class="link_nav" href="https://news.daum.net/politics">정치</a>
</div>
</body>
</html>
"""


# ============================================================================
# 1. Relative Time Parsing Tests
# ============================================================================


def test_parse_relative_time_units():
    """Verify relative time parser with fixed now anchor."""
    fixed_now = datetime(2026, 10, 25, 12, 0, 0, tzinfo=KST)

    # Seconds
    res = parse_relative_time("30초 전", now=fixed_now)
    assert res == "2026-10-25T11:59:30+09:00"

    # Minutes
    res = parse_relative_time("5분 전", now=fixed_now)
    assert res == "2026-10-25T11:55:00+09:00"

    # Hours
    res = parse_relative_time("1시간 전", now=fixed_now)
    assert res == "2026-10-25T11:00:00+09:00"
    res = parse_relative_time("2시간 전", now=fixed_now)
    assert res == "2026-10-25T10:00:00+09:00"

    # Days
    res = parse_relative_time("3일 전", now=fixed_now)
    assert res == "2026-10-22T12:00:00+09:00"

    # Weeks
    res = parse_relative_time("1주 전", now=fixed_now)
    assert res == "2026-10-18T12:00:00+09:00"

    # Yesterday
    res = parse_relative_time("어제", now=fixed_now)
    assert res == "2026-10-24T12:00:00+09:00"

    res = parse_relative_time("어제 14:30", now=fixed_now)
    assert res == "2026-10-24T14:30:00+09:00"

    # Day before yesterday
    res = parse_relative_time("그저께", now=fixed_now)
    assert res == "2026-10-23T12:00:00+09:00"

    # Just now
    res = parse_relative_time("방금", now=fixed_now)
    assert res == fixed_now.isoformat()
    res = parse_relative_time("방금 전", now=fixed_now)
    assert res == fixed_now.isoformat()


def test_parse_relative_time_dates_and_fallbacks():
    """Verify parsing ISO strings, formatted date strings, and fallbacks."""
    fixed_now = datetime(2026, 10, 25, 12, 0, 0, tzinfo=KST)

    # ISO format string
    iso_input = "2026-10-25T08:30:00+09:00"
    assert parse_relative_time(iso_input, now=fixed_now) == iso_input

    # Formatted date strings
    res = parse_relative_time("2026.10.25 09:00", now=fixed_now)
    assert res == "2026-10-25T09:00:00+09:00"

    res = parse_relative_time("2026-10-25", now=fixed_now)
    assert res == "2026-10-25T00:00:00+09:00"

    # Empty and invalid fallback
    assert parse_relative_time("", now=fixed_now) == fixed_now.isoformat()
    assert parse_relative_time(None, now=fixed_now) == fixed_now.isoformat()
    assert parse_relative_time("알수없는형식", now=fixed_now) == fixed_now.isoformat()


# ============================================================================
# 2. Headline Parsing Tests
# ============================================================================


def test_parse_headlines_from_fixture():
    """Verify parsing items from Daum News HTML fixture."""
    scraper = DaumNewsScraper()
    items = scraper.parse_headlines(SAMPLE_DAUM_HTML)

    # 4 headline anchors in fixture (one is duplicate, unrelated link_nav excluded)
    assert len(items) == 4

    # Item 1: headline2 with picture
    item1 = items[0]
    assert item1["article_id"] == "20261025224200955"
    assert "북한 자주포" in item1["title"]
    assert item1["url"] == "https://v.daum.net/v/20261025224200955"
    assert "서부전선 접경지역" in item1["summary"]
    assert item1["outlet"] == "매일경제"
    assert item1["relative_time"] == "1시간 전"
    assert item1["thumbnail_url"] == "https://img1.daumcdn.net/thumb/S686x440.jpg?fname=https%3A%2F%2Fexample.com%2Fpic1.jpg"

    # Item 2: basic with img thumbnail
    item2 = items[1]
    assert item2["article_id"] == "20261025191222025"
    assert item2["title"] == "손석희 저널리즘 가치 여전"
    assert item2["outlet"] == "오마이뉴스"
    assert item2["relative_time"] == "5분 전"
    assert item2["thumbnail_url"] == "https://img2.daumcdn.net/thumb/basic_thumb.png"

    # Item 3: basic relying on data-title
    item3 = items[2]
    assert item3["article_id"] == "20261025150000123"
    assert item3["title"] == "가상자산 과세 유예"
    assert item3["outlet"] == "연합뉴스"
    assert item3["relative_time"] == "어제"
    assert item3["summary"] == ""
    assert item3["thumbnail_url"] is None


def test_parse_headlines_empty_and_malformed():
    """Verify parse_headlines returns empty list on invalid input."""
    scraper = DaumNewsScraper()
    assert scraper.parse_headlines("") == []
    assert scraper.parse_headlines("<div><p>No headlines here</p></div>") == []
    assert scraper.parse_headlines(None) == []


# ============================================================================
# 3. Model Normalization Tests
# ============================================================================


def test_to_article_conversion():
    """Verify item dictionary conversion to Article model."""
    scraper = DaumNewsScraper()
    fixed_now = datetime(2026, 10, 25, 12, 0, 0, tzinfo=KST)

    raw_item = {
        "title": "경제 성장률 2.5% 전망",
        "url": "https://v.daum.net/v/20261025100000999",
        "article_id": "20261025100000999",
        "summary": "한국은행 경제전망 보고서 요약.",
        "outlet": "한국경제",
        "relative_time": "30분 전",
        "thumbnail_url": "https://img1.daumcdn.net/thumb/eco.jpg",
    }

    article = scraper.to_article(raw_item, now=fixed_now)

    assert isinstance(article, Article)
    assert article.id == "daum:20261025100000999"
    assert article.title == "경제 성장률 2.5% 전망"
    assert article.summary == "한국은행 경제전망 보고서 요약."
    assert article.url == "https://v.daum.net/v/20261025100000999"
    assert article.outlet == "한국경제"
    assert article.published_at == "2026-10-25T11:30:00+09:00"
    assert article.category == "주요뉴스"
    assert article.raw_data == {
        "is_major": True,
        "thumbnail_url": "https://img1.daumcdn.net/thumb/eco.jpg",
        "outlet": "한국경제",
        "relative_time": "30분 전",
    }

    # Verify as dict
    d = article.to_dict()
    assert d["id"] == "daum:20261025100000999"
    assert d["raw_data"]["is_major"] is True


def test_to_article_missing_id_fallback():
    """Verify fallback article ID generation when article_id is missing."""
    scraper = DaumNewsScraper()
    item = {
        "title": "속보 뉴스",
        "url": "https://v.daum.net/v/20261025777777777",
        "outlet": "SBS",
    }
    article = scraper.to_article(item)
    assert article.id == "daum:20261025777777777"

    # URL without digits falls back to hash
    item_no_id = {
        "title": "기타 뉴스",
        "url": "https://example.com/custom-post",
        "outlet": "KBS",
    }
    article2 = scraper.to_article(item_no_id)
    assert article2.id.startswith("daum:")
    assert len(article2.id) > 5


# ============================================================================
# 4. Fetch HTML & Error Handling Tests
# ============================================================================


def test_fetch_html_success():
    """Verify successful HTML fetch with mocked urlopen."""
    scraper = DaumNewsScraper()

    mock_resp = MagicMock()
    mock_resp.status = 200
    mock_resp.headers.get_content_charset.return_value = "utf-8"
    mock_resp.read.return_value = "<html><body>Daum News</body></html>".encode("utf-8")
    mock_resp.__enter__.return_value = mock_resp

    with patch("urllib.request.urlopen", return_value=mock_resp) as mock_open:
        content = scraper.fetch_html("https://news.daum.net", timeout=5)
        assert "Daum News" in content
        # Verify custom User-Agent in request
        called_req = mock_open.call_args[0][0]
        ua = called_req.get_header("User-agent") or called_req.headers.get("User-agent")
        assert ua is not None
        assert "Mozilla/5.0" in ua


def test_fetch_html_http_500_error():
    """Verify HTTP 500 error raises DaumScrapeError."""
    scraper = DaumNewsScraper()

    err = urllib.error.HTTPError(
        url="https://news.daum.net",
        code=500,
        msg="Internal Server Error",
        hdrs={},  # type: ignore[arg-type]
        fp=io.BytesIO(b"error"),
    )
    with patch("urllib.request.urlopen", side_effect=err):
        with pytest.raises(DaumScrapeError) as exc_info:
            scraper.fetch_html()
        assert "HTTP error 500" in str(exc_info.value)


def test_fetch_html_network_url_error():
    """Verify URLError raises DaumScrapeError."""
    scraper = DaumNewsScraper()
    err = urllib.error.URLError(reason="Connection refused")

    with patch("urllib.request.urlopen", side_effect=err):
        with pytest.raises(DaumScrapeError) as exc_info:
            scraper.fetch_html()
        assert "Network error" in str(exc_info.value)


def test_fetch_html_timeout_error():
    """Verify TimeoutError raises DaumScrapeError."""
    scraper = DaumNewsScraper()
    with patch("urllib.request.urlopen", side_effect=TimeoutError("Connection timed out")):
        with pytest.raises(DaumScrapeError) as exc_info:
            scraper.fetch_html()
        assert "Request timed out" in str(exc_info.value)


def test_fetch_html_non_200_status():
    """Verify non-200 status raises DaumScrapeError."""
    scraper = DaumNewsScraper()
    mock_resp = MagicMock()
    mock_resp.status = 503
    mock_resp.__enter__.return_value = mock_resp

    with patch("urllib.request.urlopen", return_value=mock_resp):
        with pytest.raises(DaumScrapeError) as exc_info:
            scraper.fetch_html()
        assert "status code 503" in str(exc_info.value)


# ============================================================================
# 5. Major News Scraper Integration & Deduplication Tests
# ============================================================================


def test_get_major_news_deduplication_and_limit():
    """Verify get_major_news deduplicates articles and respects limit."""
    scraper = DaumNewsScraper()

    with patch.object(scraper, "fetch_html", return_value=SAMPLE_DAUM_HTML):
        # Full list deduplicated (4 items in fixture, 1 is duplicate -> 3 unique)
        articles = scraper.get_major_news(limit=20)
        assert len(articles) == 3
        ids = [a.id for a in articles]
        assert len(ids) == len(set(ids))

        # Respect limit parameter
        limited = scraper.get_major_news(limit=2)
        assert len(limited) == 2


def test_fetch_major_news_alias():
    """Verify fetch_major_news alias method works per AC-1 specification."""
    scraper = DaumNewsScraper()

    with patch.object(scraper, "fetch_html", return_value=SAMPLE_DAUM_HTML):
        articles = scraper.fetch_major_news(limit=5)
        assert len(articles) == 3
        assert all(isinstance(a, Article) for a in articles)
        assert articles[0].id == "daum:20261025224200955"


def test_parse_headlines_nested_tags_and_relative_urls():
    """Verify tag backreference matching for nested child tags and urljoin resolution."""
    scraper = DaumNewsScraper()
    html_sample = """
    <a class="item_newsheadline2" href="/v/20261025888888888">
      <div class="cont_thumb">
        <strong class="tit_txt"><span class="ico_badge">[단독]</span> 차세대 AI 엔진 공개</strong>
        <p class="desc_txt"><em>[요약]</em> 오픈소스 기반의 신규 인공지능 모델이 발표되었습니다.</p>
        <span class="info_txt">
          <span class="con_txt">
            <span class="txt_info">IT타임스</span>
            <span class="txt_info">10분 전</span>
          </span>
        </span>
      </div>
    </a>
    <a class="item_newsbasic" href="https://v.daum.net/v/20261025777777777">
      <div class="cont_thumb">
        <strong class="tit_txt">두 번째 뉴스</strong>
        <div class="info_txt">
          <span class="txt_info">전자신문</span>
          <span class="txt_info">20분 전</span>
        </div>
      </div>
    </a>
    """
    items = scraper.parse_headlines(html_sample)
    assert len(items) == 2

    # Root-relative URL resolved to full URL via urljoin
    assert items[0]["url"] == "https://news.daum.net/v/20261025888888888"
    assert items[0]["article_id"] == "20261025888888888"
    # Nested span inside strong is preserved in title without truncation
    assert items[0]["title"] == "[단독] 차세대 AI 엔진 공개"
    # Nested em inside p is preserved in summary
    assert items[0]["summary"] == "[요약] 오픈소스 기반의 신규 인공지능 모델이 발표되었습니다."
    assert items[0]["outlet"] == "IT타임스"
    assert items[0]["relative_time"] == "10분 전"

    # Second item with <div class="info_txt">
    assert items[1]["outlet"] == "전자신문"
    assert items[1]["relative_time"] == "20분 전"


# ============================================================================
# 6. CLI Output Format Tests
# ============================================================================


def test_cli_text_format(capsys):
    """Verify CLI text output format: [<index>] <title> (<outlet>) - <url>."""
    articles = [
        Article(
            id="daum:1",
            title="헤드라인 뉴스 1",
            summary="뉴스 요약 내용입니다.",
            url="https://v.daum.net/v/1",
            outlet="언론사A",
            published_at="2026-10-25T10:00:00+09:00",
        ),
        Article(
            id="daum:2",
            title="헤드라인 뉴스 2",
            summary="",
            url="https://v.daum.net/v/2",
            outlet="언론사B",
            published_at="2026-10-25T10:05:00+09:00",
        ),
    ]

    with patch.object(DaumNewsScraper, "get_major_news", return_value=articles):
        ret = main(["--format", "text", "--limit", "2"])
        assert ret == 0

    captured = capsys.readouterr().out
    assert "[1] 헤드라인 뉴스 1 (언론사A) - https://v.daum.net/v/1" in captured
    assert "    뉴스 요약 내용입니다." in captured
    assert "[2] 헤드라인 뉴스 2 (언론사B) - https://v.daum.net/v/2" in captured


def test_cli_json_format(capsys):
    """Verify CLI JSON output format dumps valid array of article dictionaries."""
    articles = [
        Article(
            id="daum:100",
            title="JSON 뉴스 1",
            summary="요약 1",
            url="https://v.daum.net/v/100",
            outlet="중앙일보",
            published_at="2026-10-25T10:00:00+09:00",
        )
    ]

    with patch.object(DaumNewsScraper, "get_major_news", return_value=articles):
        ret = main(["--format", "json", "--limit", "1"])
        assert ret == 0

    captured = capsys.readouterr().out
    data = json.loads(captured)
    assert isinstance(data, list)
    assert len(data) == 1
    assert data[0]["id"] == "daum:100"
    assert data[0]["title"] == "JSON 뉴스 1"
    assert data[0]["outlet"] == "중앙일보"


def test_cli_error_exit_code(capsys):
    """Verify CLI exits with code 1 on scraping error."""
    with patch.object(DaumNewsScraper, "get_major_news", side_effect=DaumScrapeError("Network failure")):
        ret = main([])
        assert ret == 1

    err_captured = capsys.readouterr().err
    assert "Error scraping Daum News: Network failure" in err_captured

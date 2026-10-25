"""Comprehensive unit tests for feed sources, verification, deduplication, recency, and filtering."""

from __future__ import annotations

import io
import json
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.ingest.filter import (
    ArticleFilterPipeline,
    apply_adaptive_lookback,
    deduplicate_articles,
    filter_by_recency,
    group_and_trim_by_category,
    normalize_article_url,
    normalize_title,
    parse_iso_datetime,
)
from src.ingest.models import Article, FeedSource
from src.ingest.sources import (
    DEFAULT_FALLBACK_FEEDS,
    TARGET_CATEGORIES,
    clean_feed_url,
    filter_sources_by_categories,
    infer_category,
    load_verified_feeds,
    parse_unverified_file,
    probe_feeds,
    resolve_category_name,
    save_verified_feeds,
    validate_feed,
)


# ============================================================================
# 1. URL and Title Normalization Unit Tests
# ============================================================================


def test_normalize_article_url():
    """Verify that tracking query parameters and trailing slashes are removed."""
    url1 = "https://news.example.com/tech/123/?utm_source=rss&utm_medium=feed"
    assert normalize_article_url(url1) == "https://news.example.com/tech/123"

    url2 = "http://NEWS.EXAMPLE.COM/article/abc/"
    assert normalize_article_url(url2) == "http://news.example.com/article/abc"

    url_with_valid_query = "https://example.com/view?id=999&utm_campaign=daily"
    assert normalize_article_url(url_with_valid_query) == "https://example.com/view?id=999"

    assert normalize_article_url("") == ""
    assert normalize_article_url(None) == ""


def test_normalize_title():
    """Verify stripping of brackets, media suffixes, and special punctuation."""
    t1 = "[속보] 한국은행, 기준금리 동결 결정"
    assert normalize_title(t1) == "한국은행 기준금리 동결 결정"

    t2 = "(단독) 정부, 반도체 특별법 추진 - 연합뉴스"
    assert normalize_title(t2) == "정부 반도체 특별법 추진"

    t3 = "[포토] 활짝 핀 벚꽃길 | 매일경제"
    assert normalize_title(t3) == "활짝 핀 벚꽃길"

    assert normalize_title("") == ""
    assert normalize_title(None) == ""


# ============================================================================
# 2. Article Deduplication Unit Tests
# ============================================================================


def test_deduplicate_articles_by_url():
    """Verify articles with identical or tracking-parameter-differing URLs are pruned."""
    a1 = Article(
        id="art-1",
        title="First Article",
        summary="Summary",
        url="https://example.com/news/100?utm_source=rss",
        outlet="Outlet A",
        published_at="2026-10-25T08:00:00+00:00",
        category="정치",
    )
    a2 = Article(
        id="art-2",
        title="Duplicate URL Article",
        summary="Different summary",
        url="https://example.com/news/100",  # Same canonical URL
        outlet="Outlet B",
        published_at="2026-10-25T08:05:00+00:00",
        category="정치",
    )
    a3 = Article(
        id="art-3",
        title="Distinct Article",
        summary="Summary",
        url="https://example.com/news/200",
        outlet="Outlet A",
        published_at="2026-10-25T08:10:00+00:00",
        category="정치",
    )

    deduped = deduplicate_articles([a1, a2, a3])
    assert len(deduped) == 2
    assert [a.id for a in deduped] == ["art-1", "art-3"]


def test_deduplicate_articles_by_id():
    """Verify duplicate IDs are pruned."""
    a1 = Article(
        id="same-id",
        title="Article 1",
        summary="Summary",
        url="https://example.com/1",
        outlet="Outlet A",
        published_at="2026-10-25T08:00:00+00:00",
        category="정치",
    )
    a2 = Article(
        id="same-id",
        title="Article 2",
        summary="Summary",
        url="https://example.com/2",
        outlet="Outlet B",
        published_at="2026-10-25T08:00:00+00:00",
        category="정치",
    )
    assert len(deduplicate_articles([a1, a2])) == 1


def test_deduplicate_articles_by_title_similarity():
    """Verify articles with highly similar titles across outlets are pruned."""
    a1 = Article(
        id="art-1",
        title="[속보] 한국은행, 기준금리 연 3.5% 동결 결정",
        summary="Summary A",
        url="https://yna.co.kr/1",
        outlet="연합뉴스",
        published_at="2026-10-25T08:00:00+00:00",
        category="경제·금융",
    )
    a2 = Article(
        id="art-2",
        title="한국은행, 기준금리 연 3.5% 동결 결정 - 한국경제",
        summary="Summary B",
        url="https://hankyung.com/2",
        outlet="한국경제",
        published_at="2026-10-25T08:02:00+00:00",
        category="경제·금융",
    )
    a3 = Article(
        id="art-3",
        title="뉴욕증시, 나스닥 최고치 경신 마감",
        summary="Summary C",
        url="https://hankyung.com/3",
        outlet="한국경제",
        published_at="2026-10-25T08:10:00+00:00",
        category="경제·금융",
    )

    deduped = deduplicate_articles([a1, a2, a3], title_similarity_threshold=0.8)
    assert len(deduped) == 2
    assert [a.id for a in deduped] == ["art-1", "art-3"]


def test_deduplicate_articles_empty():
    """Verify handling of empty list."""
    assert deduplicate_articles([]) == []


# ============================================================================
# 3. Recency Filtering Unit Tests
# ============================================================================


def test_filter_by_recency():
    """Verify articles within max_hours are retained and older articles are excluded."""
    now = datetime(2026, 10, 25, 12, 0, 0, tzinfo=timezone.utc)

    # 2 hours old
    a_recent = Article(
        id="1",
        title="Recent",
        summary="",
        url="https://a.com/1",
        outlet="",
        published_at=(now - timedelta(hours=2)).isoformat(),
        category="정치",
    )
    # 47 hours old
    a_boundary = Article(
        id="2",
        title="Boundary",
        summary="",
        url="https://a.com/2",
        outlet="",
        published_at=(now - timedelta(hours=47)).isoformat(),
        category="정치",
    )
    # 50 hours old (> 48h)
    a_old = Article(
        id="3",
        title="Old",
        summary="",
        url="https://a.com/3",
        outlet="",
        published_at=(now - timedelta(hours=50)).isoformat(),
        category="정치",
    )
    # 1 hour into future (within 2h tolerance)
    a_future_slight = Article(
        id="4",
        title="Future Slight",
        summary="",
        url="https://a.com/4",
        outlet="",
        published_at=(now + timedelta(hours=1)).isoformat(),
        category="정치",
    )
    # 5 hours into future (beyond tolerance)
    a_future_excessive = Article(
        id="5",
        title="Future Excessive",
        summary="",
        url="https://a.com/5",
        outlet="",
        published_at=(now + timedelta(hours=5)).isoformat(),
        category="정치",
    )
    # Invalid date string
    a_invalid_date = Article(
        id="6",
        title="Invalid Date",
        summary="",
        url="https://a.com/6",
        outlet="",
        published_at="invalid-date-string",
        category="정치",
    )

    articles = [a_recent, a_boundary, a_old, a_future_slight, a_future_excessive, a_invalid_date]
    filtered = filter_by_recency(articles, max_hours=48.0, reference_time=now)

    assert [a.id for a in filtered] == ["1", "2", "4"]


def test_filter_by_recency_with_timezone_offsets():
    """Verify recency filtering properly accounts for KST (+09:00) vs UTC."""
    # 2026-10-25 12:00:00 UTC = 2026-10-25 21:00:00 KST (+09:00)
    ref_time = datetime(2026, 10, 25, 12, 0, 0, tzinfo=timezone.utc)

    # Published at 20:00:00 KST (+09:00), which is 1 hour before ref_time
    a_kst = Article(
        id="kst",
        title="KST Article",
        summary="",
        url="https://a.com/kst",
        outlet="",
        published_at="2026-10-25T20:00:00+09:00",
        category="사회",
    )

    filtered = filter_by_recency([a_kst], max_hours=24.0, reference_time=ref_time)
    assert len(filtered) == 1
    assert filtered[0].id == "kst"


# ============================================================================
# 4. Category Grouping and Quota Trimming Unit Tests
# ============================================================================


def test_group_and_trim_by_category():
    """Verify articles are grouped by category, sorted descending by published date, and trimmed to quota."""
    now = datetime(2026, 10, 25, 12, 0, 0, tzinfo=timezone.utc)

    articles: list[Article] = []
    # Create 8 articles for 정치
    for i in range(8):
        articles.append(
            Article(
                id=f"pol-{i}",
                title=f"Pol Article {i}",
                summary="",
                url=f"https://a.com/pol/{i}",
                outlet="",
                published_at=(now - timedelta(hours=i)).isoformat(),
                category="정치",
            )
        )
    # Create 3 articles for AI·빅테크
    for i in range(3):
        articles.append(
            Article(
                id=f"ai-{i}",
                title=f"AI Article {i}",
                summary="",
                url=f"https://a.com/ai/{i}",
                outlet="",
                published_at=(now - timedelta(hours=i)).isoformat(),
                category="AI·빅테크",
            )
        )

    categories = ["정치", "AI·빅테크", "스포츠"]
    result = group_and_trim_by_category(articles, categories=categories, max_per_category=5)

    # 1. Quota limit of 5 respected for 정치
    assert len(result["정치"]) == 5
    # 2. Sorted newest first: pol-0 was published at now - 0h
    assert result["정치"][0].id == "pol-0"
    assert result["정치"][4].id == "pol-4"

    # 3. AI·빅테크 has 3 articles
    assert len(result["AI·빅테크"]) == 3
    assert result["AI·빅테크"][0].id == "ai-0"

    # 4. 스포츠 has 0 articles but key exists
    assert result["스포츠"] == []


def test_group_and_trim_with_category_alias():
    """Verify alias mapping like 'AI' matches 'AI·빅테크'."""
    art = Article(
        id="ai-1",
        title="AI Breakthrough",
        summary="",
        url="https://a.com/ai",
        outlet="",
        published_at="2026-10-25T10:00:00+00:00",
        category="AI",
    )
    result = group_and_trim_by_category([art], categories=["AI·빅테크"], max_per_category=5)
    assert len(result["AI·빅테크"]) == 1


# ============================================================================
# 5. Article Filter Pipeline Unit Tests
# ============================================================================


def test_article_filter_pipeline_process():
    """Verify pipeline executes recency, deduplication, and trimming in sequence."""
    ref_time = datetime(2026, 10, 25, 12, 0, 0, tzinfo=timezone.utc)
    pipeline = ArticleFilterPipeline(
        categories=["정치", "IT·통신"],
        max_hours=24.0,
        max_per_category=2,
        title_similarity_threshold=0.8,
        reference_time=ref_time,
    )

    raw_articles = [
        # Recent & unique
        Article(
            id="1",
            title="정부, 신규 민생 경제 대책 발표",
            summary="",
            url="https://news.com/p1",
            outlet="O1",
            published_at=(ref_time - timedelta(hours=1)).isoformat(),
            category="정치",
        ),
        # Recent & unique
        Article(
            id="2",
            title="여야 원내대표, 정기국회 일정 합의",
            summary="",
            url="https://news.com/p2",
            outlet="O1",
            published_at=(ref_time - timedelta(hours=2)).isoformat(),
            category="정치",
        ),
        # Recent but quota exceeds (3rd in category)
        Article(
            id="3",
            title="대통령실, 신임 수석비서관 임명 발표",
            summary="",
            url="https://news.com/p3",
            outlet="O1",
            published_at=(ref_time - timedelta(hours=3)).isoformat(),
            category="정치",
        ),
        # Duplicate URL of 1
        Article(
            id="4",
            title="정부 민생 경제 대책 발표 요약",
            summary="",
            url="https://news.com/p1?utm_source=rss",
            outlet="O2",
            published_at=(ref_time - timedelta(hours=1)).isoformat(),
            category="정치",
        ),
        # Too old (30 hours ago)
        Article(
            id="5",
            title="통신 3사 6G 통신망 투자 계획 공개",
            summary="",
            url="https://news.com/it1",
            outlet="O1",
            published_at=(ref_time - timedelta(hours=30)).isoformat(),
            category="IT·통신",
        ),
        # Valid IT article
        Article(
            id="6",
            title="국내 연구진 차세대 양자 암호통신 기술 개발",
            summary="",
            url="https://news.com/it2",
            outlet="O1",
            published_at=(ref_time - timedelta(hours=5)).isoformat(),
            category="IT·통신",
        ),
    ]

    grouped = pipeline.process(raw_articles)
    assert len(grouped["정치"]) == 2
    assert [a.id for a in grouped["정치"]] == ["1", "2"]
    assert len(grouped["IT·통신"]) == 1
    assert [a.id for a in grouped["IT·통신"]] == ["6"]

    # Flat export check
    flat = pipeline.process_flat(raw_articles)
    assert len(flat) == 3
    # Sorted newest first: 1 (1h ago), 2 (2h ago), 6 (5h ago)
    assert [a.id for a in flat] == ["1", "2", "6"]


# ============================================================================
# 6. Unverified Feeds Parsing Unit Tests
# ============================================================================


def test_clean_feed_url():
    """Verify URL cleaning trims adhered Korean characters and delimiters."""
    assert clean_feed_url("http://example.com/rss.xml시사") == "http://example.com/rss.xml"
    assert clean_feed_url("http://example.com/feed.php?part=1||") == "http://example.com/feed.php?part=1"
    assert clean_feed_url("https://example.com/feed.xml,") == "https://example.com/feed.xml"
    assert clean_feed_url("  https://example.com/feed  ") == "https://example.com/feed"


def test_infer_category():
    """Verify category inference across keywords."""
    assert infer_category("연합뉴스 - 정치", "https://yna.co.kr/rss/politics.xml") == "정치"
    assert infer_category("한국경제 - 금융증권", "https://hankyung.com/finance") == "경제·금융"
    assert infer_category("AI타임스 - 생성형 AI 소식", "https://aitimes.com/feed") == "AI·빅테크"
    assert infer_category("전자신문 - 모바일 통신", "https://etnews.com/it") == "IT·통신"
    assert infer_category("동아일보 - 스포츠전체", "https://donga.com/sports") == "스포츠"
    assert infer_category("경향신문 - 건강 라이프", "https://khan.co.kr/health") == "라이프스타일"
    assert infer_category("알 수 없는 피드", "https://example.com/misc.xml") == "종합"


def test_parse_unverified_file_mock(tmp_path: Path):
    """Verify unverified feeds parsing, outlet extraction, URL cleaning, and duplicate removal."""
    sample_file = tmp_path / "sample_unverified.txt"
    sample_content = (
        "경향닷컴\n"
        "[경향신문]정치 http://www.khan.co.kr/rss/rssdata/politic.xml시사\n"
        "[경향신문]경제 http://www.khan.co.kr/rss/rssdata/economy.xml\n"
        "[경향신문]정치 http://www.khan.co.kr/rss/rssdata/politic.xml\n"  # Duplicate URL
        "\n"
        "지디넷코리아\n"
        "AI http://zdnet.co.kr/rss/ai.xml\n"
        "# http://zdnet.co.kr/rss/ai.xml\n"  # Duplicate URL with comment
    )
    sample_file.write_text(sample_content, encoding="utf-8")

    sources = parse_unverified_file(sample_file)
    assert len(sources) == 3

    assert sources[0].name == "경향신문 - 정치"
    assert sources[0].url == "http://www.khan.co.kr/rss/rssdata/politic.xml"
    assert sources[0].category == "정치"

    assert sources[1].name == "경향신문 - 경제"
    assert sources[1].url == "http://www.khan.co.kr/rss/rssdata/economy.xml"
    assert sources[1].category == "경제·금융"

    assert sources[2].name == "지디넷코리아 - AI"
    assert sources[2].url == "http://zdnet.co.kr/rss/ai.xml"
    assert sources[2].category == "AI·빅테크"


def test_parse_unverified_file_real_workspace():
    """Verify parsing the real workspace rss-unverified.txt file."""
    real_file = Path("rss-unverified.txt")
    if not real_file.exists():
        pytest.skip("rss-unverified.txt not found in workspace")

    sources = parse_unverified_file(real_file)
    assert len(sources) > 500  # Over 800 unique feeds expected
    # Verify no duplicate URLs exist
    urls = [s.url for s in sources]
    assert len(urls) == len(set(urls))

    # Verify all categories are non-empty
    for s in sources:
        assert s.category
        assert s.url.startswith("http")


def test_parse_unverified_file_not_found():
    """Verify FileNotFoundError is raised when file does not exist."""
    with pytest.raises(FileNotFoundError):
        parse_unverified_file("non_existent_file.txt")


# ============================================================================
# 7. Feed Validation and Probing Unit Tests
# ============================================================================


def test_validate_feed_success():
    """Verify validate_feed returns True on 200 OK with RSS XML."""
    mock_response = MagicMock()
    mock_response.status = 200
    mock_response.read.return_value = b'<?xml version="1.0"?><rss version="2.0"><channel></channel></rss>'
    mock_response.__enter__.return_value = mock_response

    with patch("urllib.request.urlopen", return_value=mock_response):
        assert validate_feed("https://example.com/rss.xml") is True


def test_validate_feed_non_xml_failure():
    """Verify validate_feed returns False when content is regular HTML without RSS tags."""
    mock_response = MagicMock()
    mock_response.status = 200
    mock_response.read.return_value = b"<!DOCTYPE html><html><body>Error 404</body></html>"
    mock_response.__enter__.return_value = mock_response

    with patch("urllib.request.urlopen", return_value=mock_response):
        assert validate_feed("https://example.com/rss.xml") is False


def test_validate_feed_http_error():
    """Verify validate_feed returns False on HTTP 404/500 errors."""
    with patch(
        "urllib.request.urlopen",
        side_effect=urllib.error.HTTPError("url", 404, "Not Found", {}, None),
    ):
        assert validate_feed("https://example.com/404.xml") is False


def test_validate_feed_invalid_url():
    """Verify validate_feed returns False for empty or malformed URLs."""
    assert validate_feed("") is False
    assert validate_feed("not-a-url") is False


def test_probe_feeds_concurrency():
    """Verify probe_feeds concurrently marks active/inactive statuses."""
    sources = [
        FeedSource(name="Valid Feed", url="https://example.com/good.xml", category="정치"),
        FeedSource(name="Broken Feed", url="https://example.com/bad.xml", category="사회"),
    ]

    def mock_validator(url: str, timeout: float = 3.0) -> bool:
        return "good" in url

    with patch("src.ingest.sources.validate_feed", side_effect=mock_validator):
        probed = probe_feeds(sources, max_workers=2, timeout=1.0)
        assert len(probed) == 2
        assert probed[0].is_active is True
        assert probed[1].is_active is False


# ============================================================================
# 8. Category Filter Logic Unit Tests
# ============================================================================


def test_filter_sources_by_categories():
    """Verify source selection based on interested categories and aliases."""
    sources = [
        FeedSource("YNA Politics", "https://yna.co.kr/pol", "정치", is_active=True),
        FeedSource("YNA Economy", "https://yna.co.kr/eco", "경제·금융", is_active=True),
        FeedSource("AI Times", "https://aitimes.com/rss", "AI·빅테크", is_active=True),
        FeedSource("ETNews IT", "https://etnews.com/it", "IT·통신", is_active=False),
    ]

    # 1. Direct and alias category matching
    selected = filter_sources_by_categories(sources, interested_categories=["정치", "AI"])
    assert len(selected) == 2
    assert [s.name for s in selected] == ["YNA Politics", "AI Times"]

    # 2. Active only flag
    selected_active = filter_sources_by_categories(
        sources, interested_categories=["IT·통신"], active_only=True
    )
    assert len(selected_active) == 0

    # 3. Empty interested categories returns all
    all_selected = filter_sources_by_categories(sources, interested_categories=[])
    assert len(all_selected) == 4


# ============================================================================
# 9. Verified Feeds Catalog Persistence Unit Tests
# ============================================================================


def test_save_and_load_verified_feeds(tmp_path: Path):
    """Verify saving to and loading from verified feeds JSON storage."""
    catalog_path = tmp_path / "feeds" / "verified_feeds.json"

    sources = [
        FeedSource("연합뉴스 정치", "https://yna.co.kr/pol.xml", "정치", is_active=True),
        FeedSource("AI 타임스", "https://aitimes.com/ai.xml", "AI·빅테크", is_active=True),
    ]

    save_verified_feeds(sources, catalog_path)
    assert catalog_path.exists()

    loaded = load_verified_feeds(catalog_path)
    assert len(loaded) == 2
    assert loaded[0].name == "연합뉴스 정치"
    assert loaded[0].url == "https://yna.co.kr/pol.xml"
    assert loaded[0].category == "정치"
    assert loaded[0].is_active is True
    assert loaded[1].name == "AI 타임스"


def test_load_verified_feeds_not_found(tmp_path: Path):
    """Verify FileNotFoundError on missing catalog."""
    with pytest.raises(FileNotFoundError):
        load_verified_feeds(tmp_path / "does_not_exist.json")


def test_load_verified_feeds_corrupted(tmp_path: Path):
    """Verify ValueError on corrupted format."""
    bad_file = tmp_path / "bad.json"
    bad_file.write_text('{"not": "a list"}', encoding="utf-8")
    with pytest.raises(ValueError):
        load_verified_feeds(bad_file)


# ============================================================================
# 10. Pre-curated Fallback Feeds Unit Tests
# ============================================================================


def test_fallback_feeds_coverage():
    """Verify DEFAULT_FALLBACK_FEEDS covers all 10 target categories."""
    assert len(DEFAULT_FALLBACK_FEEDS) >= 10

    covered_categories = {s.category for s in DEFAULT_FALLBACK_FEEDS}
    for target in TARGET_CATEGORIES:
        assert target in covered_categories, f"Target category {target} missing in fallback feeds"


def test_load_feed_sources_from_data_feeds():
    """Verify load_feed_sources loads valid sources from data/feeds.json."""
    from src.ingest.sources import DEFAULT_FEEDS_PATH, load_feed_sources

    assert DEFAULT_FEEDS_PATH.exists()
    sources = load_feed_sources(DEFAULT_FEEDS_PATH)
    assert len(sources) >= 10
    categories = {s.category for s in sources}
    for target in TARGET_CATEGORIES:
        assert target in categories


def test_load_feed_sources_missing_fallback(tmp_path: Path):
    """Verify load_feed_sources falls back to default list on missing file."""
    from src.ingest.sources import load_feed_sources

    sources = load_feed_sources(tmp_path / "nonexistent_feeds.json")
    assert len(sources) >= 10


# ============================================================================
# 11. Adaptive Category Lookback Unit Tests
# ============================================================================


def test_adaptive_lookback_sufficient_recent_no_fallback():
    """Verify category with >= min_per_category recent articles uses standard window with no fallback."""
    ref_time = datetime(2026, 10, 25, 12, 0, 0, tzinfo=timezone.utc)
    pipeline = ArticleFilterPipeline(
        categories=["정치"],
        max_hours=24.0,
        max_lookback_hours=72.0,
        min_per_category=2,
        adaptive_lookback=True,
        reference_time=ref_time,
    )

    articles = [
        Article(
            id="p-1",
            title="여야 원내대표 정기국회 일정 전격 합의",
            summary="",
            url="https://news.com/p1",
            outlet="O1",
            published_at=(ref_time - timedelta(hours=2)).isoformat(),
            category="정치",
        ),
        Article(
            id="p-2",
            title="정부 신규 민생 경제 대책 국무회의 의결",
            summary="",
            url="https://news.com/p2",
            outlet="O1",
            published_at=(ref_time - timedelta(hours=4)).isoformat(),
            category="정치",
        ),
        Article(
            id="p-3",
            title="대통령실 신임 수석비서관 임명 단행",
            summary="",
            url="https://news.com/p3",
            outlet="O1",
            published_at=(ref_time - timedelta(hours=6)).isoformat(),
            category="정치",
        ),
        Article(
            id="p-old-1",
            title="국회 예결위 내년도 예산안 종합 심사 돌입",
            summary="",
            url="https://news.com/p_old1",
            outlet="O1",
            published_at=(ref_time - timedelta(hours=35)).isoformat(),
            category="정치",
        ),
        Article(
            id="p-old-2",
            title="중앙선관위 재보궐선거 투표율 잠정 집계 발표",
            summary="",
            url="https://news.com/p_old2",
            outlet="O1",
            published_at=(ref_time - timedelta(hours=50)).isoformat(),
            category="정치",
        ),
    ]

    grouped = pipeline.process(articles)
    assert len(grouped["정치"]) == 3
    assert [a.id for a in grouped["정치"]] == ["p-1", "p-2", "p-3"]


def test_adaptive_lookback_backfills_deficient_categories():
    """Verify deficient categories (0 or 1 recent) backfill from 72h window up to min_per_category."""
    ref_time = datetime(2026, 10, 25, 12, 0, 0, tzinfo=timezone.utc)
    pipeline = ArticleFilterPipeline(
        categories=["AI·빅테크", "문화·콘텐츠"],
        max_hours=24.0,
        max_lookback_hours=72.0,
        min_per_category=2,
        adaptive_lookback=True,
        reference_time=ref_time,
    )

    articles = [
        # AI: 1 recent (5h ago), 2 older within 72h (30h, 48h ago), 1 even older (60h ago)
        Article(
            id="ai-1",
            title="신규 LLM 모델 출시",
            summary="",
            url="https://news.com/ai1",
            outlet="O1",
            published_at=(ref_time - timedelta(hours=5)).isoformat(),
            category="AI·빅테크",
        ),
        Article(
            id="ai-2",
            title="빅테크 AI 데이터센터 구축 계획",
            summary="",
            url="https://news.com/ai2",
            outlet="O1",
            published_at=(ref_time - timedelta(hours=30)).isoformat(),
            category="AI·빅테크",
        ),
        Article(
            id="ai-3",
            title="생성형 AI 오픈소스 라이브러리 공개",
            summary="",
            url="https://news.com/ai3",
            outlet="O1",
            published_at=(ref_time - timedelta(hours=48)).isoformat(),
            category="AI·빅테크",
        ),
        Article(
            id="ai-4",
            title="차세대 GPU 아키텍처 세미나 개최",
            summary="",
            url="https://news.com/ai4",
            outlet="O1",
            published_at=(ref_time - timedelta(hours=60)).isoformat(),
            category="AI·빅테크",
        ),
        # 문화: 0 recent, 3 older within 72h (32h, 45h, 65h ago)
        Article(
            id="cul-1",
            title="국립중앙박물관 특별 전시 개막",
            summary="",
            url="https://news.com/cul1",
            outlet="O1",
            published_at=(ref_time - timedelta(hours=32)).isoformat(),
            category="문화·콘텐츠",
        ),
        Article(
            id="cul-2",
            title="K-웹툰 글로벌 어워즈 성황리 개최",
            summary="",
            url="https://news.com/cul2",
            outlet="O1",
            published_at=(ref_time - timedelta(hours=45)).isoformat(),
            category="문화·콘텐츠",
        ),
        Article(
            id="cul-3",
            title="전통 공예 현대화 기획전 발표",
            summary="",
            url="https://news.com/cul3",
            outlet="O1",
            published_at=(ref_time - timedelta(hours=65)).isoformat(),
            category="문화·콘텐츠",
        ),
    ]

    grouped = pipeline.process(articles)

    # AI: had 1 recent, backfills 1 from 30h ago to reach 2
    assert len(grouped["AI·빅테크"]) == 2
    assert [a.id for a in grouped["AI·빅테크"]] == ["ai-1", "ai-2"]

    # Culture: had 0 recent, backfills 2 (32h and 45h) to reach 2
    assert len(grouped["문화·콘텐츠"]) == 2
    assert [a.id for a in grouped["문화·콘텐츠"]] == ["cul-1", "cul-2"]

    # Verify order is descending by published_at
    for cat in ["AI·빅테크", "문화·콘텐츠"]:
        times = [parse_iso_datetime(a.published_at) for a in grouped[cat]]
        assert times[0] > times[1]


def test_adaptive_lookback_excludes_articles_beyond_max_lookback():
    """Verify articles older than max_lookback_hours are not backfilled even if quota is deficient."""
    ref_time = datetime(2026, 10, 25, 12, 0, 0, tzinfo=timezone.utc)
    pipeline = ArticleFilterPipeline(
        categories=["라이프스타일"],
        max_hours=24.0,
        max_lookback_hours=72.0,
        min_per_category=2,
        adaptive_lookback=True,
        reference_time=ref_time,
    )

    articles = [
        # 1 article within 72h (50h ago)
        Article(
            id="life-1",
            title="가을철 건강 관리 수칙",
            summary="",
            url="https://news.com/life1",
            outlet="O1",
            published_at=(ref_time - timedelta(hours=50)).isoformat(),
            category="라이프스타일",
        ),
        # 2 articles older than 72h (80h and 100h ago)
        Article(
            id="life-old-80",
            title="수면 패턴과 면역력 관계",
            summary="",
            url="https://news.com/life_old80",
            outlet="O1",
            published_at=(ref_time - timedelta(hours=80)).isoformat(),
            category="라이프스타일",
        ),
        Article(
            id="life-old-100",
            title="환절기 피부 보습 팁",
            summary="",
            url="https://news.com/life_old100",
            outlet="O1",
            published_at=(ref_time - timedelta(hours=100)).isoformat(),
            category="라이프스타일",
        ),
    ]

    grouped = pipeline.process(articles)
    # Only life-1 should be retained, 80h and 100h must be excluded
    assert len(grouped["라이프스타일"]) == 1
    assert grouped["라이프스타일"][0].id == "life-1"


def test_adaptive_lookback_preserves_deduplication():
    """Verify deduplication (URL, ID, title similarity) across primary and backfilled articles."""
    ref_time = datetime(2026, 10, 25, 12, 0, 0, tzinfo=timezone.utc)
    pipeline = ArticleFilterPipeline(
        categories=["IT·통신"],
        max_hours=24.0,
        max_lookback_hours=72.0,
        min_per_category=2,
        adaptive_lookback=True,
        title_similarity_threshold=0.8,
        reference_time=ref_time,
    )

    articles = [
        # 1 recent article
        Article(
            id="it-recent",
            title="통신 3사 6G 표준화 공동 협의체 출범",
            summary="",
            url="https://news.com/it_recent",
            outlet="O1",
            published_at=(ref_time - timedelta(hours=3)).isoformat(),
            category="IT·통신",
        ),
        # Candidate 1: Same ID as recent
        Article(
            id="it-recent",
            title="다른 제목의 기사",
            summary="",
            url="https://news.com/it_other1",
            outlet="O2",
            published_at=(ref_time - timedelta(hours=30)).isoformat(),
            category="IT·통신",
        ),
        # Candidate 2: Same URL (with tracking params) as recent
        Article(
            id="it-cand-2",
            title="또 다른 제목의 기사",
            summary="",
            url="https://news.com/it_recent?utm_source=feed",
            outlet="O2",
            published_at=(ref_time - timedelta(hours=35)).isoformat(),
            category="IT·통신",
        ),
        # Candidate 3: Similar title to recent
        Article(
            id="it-cand-3",
            title="통신3사 6G 표준화 공동 협의체 출범 발표",
            summary="",
            url="https://news.com/it_cand3",
            outlet="O3",
            published_at=(ref_time - timedelta(hours=40)).isoformat(),
            category="IT·통신",
        ),
        # Candidate 4: Truly distinct article
        Article(
            id="it-valid-backfill",
            title="차세대 반도체 공정 양산 시작",
            summary="",
            url="https://news.com/it_semiconductor",
            outlet="O1",
            published_at=(ref_time - timedelta(hours=45)).isoformat(),
            category="IT·통신",
        ),
    ]

    grouped = pipeline.process(articles)
    assert len(grouped["IT·통신"]) == 2
    assert [a.id for a in grouped["IT·통신"]] == ["it-recent", "it-valid-backfill"]


def test_apply_adaptive_lookback_standalone():
    """Verify apply_adaptive_lookback works directly as a standalone helper function."""
    ref_time = datetime(2026, 10, 25, 12, 0, 0, tzinfo=timezone.utc)
    articles = [
        Article(
            id="1",
            title="정부 긴급 민생대책 회의 주재",
            summary="",
            url="https://news.com/p1",
            outlet="O1",
            published_at=(ref_time - timedelta(hours=1)).isoformat(),
            category="정치",
        ),
        Article(
            id="2",
            title="통신 3사 차세대 양자 암호통신망 기술 개발",
            summary="",
            url="https://news.com/it1",
            outlet="O1",
            published_at=(ref_time - timedelta(hours=36)).isoformat(),
            category="IT·통신",
        ),
        Article(
            id="3",
            title="인공지능 가속기 국산화 반도체 로드맵 공개",
            summary="",
            url="https://news.com/it2",
            outlet="O1",
            published_at=(ref_time - timedelta(hours=48)).isoformat(),
            category="IT·통신",
        ),
    ]

    result = apply_adaptive_lookback(
        articles=articles,
        categories=["정치", "IT·통신"],
        min_per_category=2,
        max_hours=24.0,
        max_lookback_hours=72.0,
        reference_time=ref_time,
    )

    # 정치: 1 article (only 1 available in dataset)
    assert len(result["정치"]) == 1
    assert result["정치"][0].id == "1"

    # IT·통신: 0 in 24h, backfills 2 from 72h window
    assert len(result["IT·통신"]) == 2
    assert [a.id for a in result["IT·통신"]] == ["2", "3"]

    # Empty articles check
    empty_result = apply_adaptive_lookback(
        articles=[],
        categories=["정치", "IT·통신"],
    )
    assert empty_result == {"정치": [], "IT·통신": []}


def test_article_filter_pipeline_process_flat_with_lookback():
    """Verify process_flat flattens backfilled articles in descending published_at order."""
    ref_time = datetime(2026, 10, 25, 12, 0, 0, tzinfo=timezone.utc)
    pipeline = ArticleFilterPipeline(
        categories=["정치", "문화·콘텐츠"],
        max_hours=24.0,
        max_lookback_hours=72.0,
        min_per_category=1,
        adaptive_lookback=True,
        reference_time=ref_time,
    )

    articles = [
        Article(
            id="p-1",
            title="정치 뉴스",
            summary="",
            url="https://news.com/p1",
            outlet="O1",
            published_at=(ref_time - timedelta(hours=2)).isoformat(),
            category="정치",
        ),
        Article(
            id="cul-1",
            title="문화 뉴스 (40h 전)",
            summary="",
            url="https://news.com/c1",
            outlet="O1",
            published_at=(ref_time - timedelta(hours=40)).isoformat(),
            category="문화·콘텐츠",
        ),
    ]

    flat = pipeline.process_flat(articles)
    assert len(flat) == 2
    assert [a.id for a in flat] == ["p-1", "cul-1"]
    assert parse_iso_datetime(flat[0].published_at) > parse_iso_datetime(flat[1].published_at)

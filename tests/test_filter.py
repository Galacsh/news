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

from src.ingest.body_extractor import ArticleBodyExtractor, enrich_articles_with_body
from src.ingest.filter import (
    ArticleFilterPipeline,
    apply_adaptive_lookback,
    cluster_articles_by_topic,
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


# ============================================================================
# 8. Cross-Outlet Consensus Clustering and Body Extractor Tests
# ============================================================================


def test_article_model_related_links_and_body_serialization():
    """Verify Article correctly handles related_links and excludes transient body on serialization."""
    art = Article(
        id="art-100",
        title="테스트 기사 제목",
        summary="기사 요약문",
        url="https://news.example.com/art1",
        outlet="테스트언론사",
        published_at="2026-10-31T10:00:00+00:00",
        category="정치",
        related_links=[{"title": "관련 기사 1", "url": "https://news.example.com/rel1"}],
        body="이것은 메모리 상의 임시 본문 텍스트입니다.",
    )

    d = art.to_dict()
    assert "related_links" in d
    assert len(d["related_links"]) == 1
    assert d["related_links"][0]["title"] == "관련 기사 1"
    # body must NOT be serialized in to_dict()
    assert "body" not in d

    # from_dict reconstruction
    reconstructed = Article.from_dict(d)
    assert reconstructed.id == "art-100"
    assert reconstructed.related_links == [{"title": "관련 기사 1", "url": "https://news.example.com/rel1"}]
    assert reconstructed.body == ""


def test_cluster_articles_by_topic_empty_and_single():
    """Verify cluster_articles_by_topic handles empty list and single article correctly."""
    assert cluster_articles_by_topic([]) == []

    art = Article(
        id="s-1",
        title="단독 속보 기사",
        summary="요약문 내용",
        url="https://news.com/s1",
        outlet="A언론",
        published_at="2026-10-31T10:00:00+00:00",
    )
    result = cluster_articles_by_topic([art])
    assert len(result) == 1
    assert result[0].id == "s-1"
    assert (result[0].raw_data or {}).get("consensus_score") == 11.0


def test_cluster_articles_by_topic_cross_outlet_consensus():
    """Verify that multiple outlets covering the same breaking story cluster and attach related links."""
    ref_time = datetime(2026, 10, 31, 12, 0, 0, tzinfo=timezone.utc)

    # 3 articles from 3 outlets covering the exact same event
    art1 = Article(
        id="cluster-1",
        title="정부, 유류세 인하 2개월 추가 연장 결정",
        summary="정부가 이달 말 종료 예정이던 유류세 한시 인하 조치를 10월 말까지 2개월 추가 연장하기로 했다.",
        url="https://yonhap.com/news/101",
        outlet="연합뉴스",
        published_at=(ref_time - timedelta(minutes=30)).isoformat(),
        category="경제·금융",
    )
    art2 = Article(
        id="cluster-2",
        title="유류세 인하 조치 10월까지 2개월 연장... 중동 불안 감안",
        summary="정부가 유류세 한시 인하 조치를 10월 말까지 2개월 더 연장한다.",
        url="https://chosun.com/news/202",
        outlet="조선일보",
        published_at=(ref_time - timedelta(minutes=20)).isoformat(),
        category="경제·금융",
    )
    art3 = Article(
        id="cluster-3",
        title="기재부, 유류세 인하 2개월 연장 발표... 10월까지 유지",
        summary="기획재정부가 종료 예정이던 유류세 인하 조치를 10월 말까지 2개월 추가 연장한다고 밝혔다.",
        url="https://mk.co.kr/news/303",
        outlet="매일경제",
        published_at=(ref_time - timedelta(minutes=10)).isoformat(),
        category="경제·금융",
    )

    # 1 independent story from single outlet
    art_other = Article(
        id="other-1",
        title="한국은행 총재, 국제결제은행 연례총회 참석차 출국",
        summary="한국은행 총재가 스위스 바젤에서 열리는 BIS 연례총회에 참석하기 위해 출국했다.",
        url="https://yonhap.com/news/999",
        outlet="연합뉴스",
        published_at=(ref_time - timedelta(minutes=5)).isoformat(),
        category="경제·금융",
    )

    clusters = cluster_articles_by_topic([art1, art2, art3, art_other])

    # Should have 2 clusters: the consensus story and the independent story
    assert len(clusters) == 2

    consensus_rep = clusters[0]
    single_rep = clusters[1]

    assert (consensus_rep.raw_data or {}).get("consensus_score") > 30.0
    assert (single_rep.raw_data or {}).get("consensus_score") < 20.0
    assert (consensus_rep.raw_data or {}).get("distinct_outlets_count") == 3

    # Check related_links attached to consensus representative
    assert len(consensus_rep.related_links) == 2
    related_urls = [link["url"] for link in consensus_rep.related_links]
    assert consensus_rep.url not in related_urls
    for other_url in [art1.url, art2.url, art3.url]:
        if other_url != consensus_rep.url:
            assert other_url in related_urls


def test_cluster_articles_by_topic_prioritizes_consensus_over_freshness():
    """Verify that a story with 2 independent outlets ranks higher than a newer story with only 1 outlet."""
    ref_time = datetime(2026, 10, 31, 12, 0, 0, tzinfo=timezone.utc)

    # Multi-outlet story (published 6 hours ago)
    c1 = Article(
        id="m-1",
        title="삼성전자 3분기 잠정 영업이익 9조원 달성 반도체 부진",
        summary="삼성전자가 3분기 잠정 영업이익 9조 1천억원을 기록했다고 공시했다.",
        url="https://o1.com/1",
        outlet="언론사A",
        published_at=(ref_time - timedelta(hours=6)).isoformat(),
    )
    c2 = Article(
        id="m-2",
        title="삼성전자, 3분기 잠정 영업이익 9조원 기록... 시장 기대치 하회",
        summary="삼성전자 3분기 잠정 실적 집계 결과 영업이익 9조 1000억원으로 집계됐다.",
        url="https://o2.com/2",
        outlet="언론사B",
        published_at=(ref_time - timedelta(hours=6)).isoformat(),
    )

    # Fresh single-outlet story (published 10 minutes ago)
    single_fresh = Article(
        id="s-fresh",
        title="우주항공청, 차세대 중형위성 발사 성공 발표",
        summary="우주항공청이 나로우주센터에서 차세대 중형위성을 성공적으로 발사했다고 밝혔다.",
        url="https://o3.com/3",
        outlet="언론사C",
        published_at=(ref_time - timedelta(minutes=10)).isoformat(),
    )

    ranked = cluster_articles_by_topic([single_fresh, c1, c2])

    assert len(ranked) == 2
    # The multi-outlet story MUST rank first despite being older
    assert ranked[0].id in ("m-1", "m-2")
    assert ranked[1].id == "s-fresh"
    assert (ranked[0].raw_data or {}).get("consensus_score") >= 20.0
    assert (ranked[1].raw_data or {}).get("consensus_score") < 15.0


def test_cluster_articles_by_topic_representative_selection():
    """Verify representative selection prefers longest title/summary, breaking ties with recency."""
    ref_time = datetime(2026, 10, 31, 12, 0, 0, tzinfo=timezone.utc)

    # Short title & summary
    short_art = Article(
        id="short",
        title="한국은행 기준금리 0.25%p 인하 단행",
        summary="한은이 기준금리를 0.25%포인트 인하했다.",
        url="https://news.com/short",
        outlet="A",
        published_at=(ref_time - timedelta(hours=1)).isoformat(),
    )
    # Long descriptive title & summary (older)
    long_art = Article(
        id="long",
        title="한국은행 금융통화위원회 기준금리 0.25%포인트 전격 인하 단행",
        summary="한국은행 금융통화위원회가 오늘 본회의를 열고 기준금리를 연 3.5%에서 3.25%로 0.25%포인트 인하하며 통화정책 피벗에 나섰다.",
        url="https://news.com/long",
        outlet="B",
        published_at=(ref_time - timedelta(hours=2)).isoformat(),
    )

    ranked = cluster_articles_by_topic([short_art, long_art])
    assert len(ranked) == 1
    # Long descriptive article should be picked as representative
    assert ranked[0].id == "long"
    assert len(ranked[0].related_links) == 1
    assert ranked[0].related_links[0]["url"] == short_art.url


def test_pipeline_integration_with_consensus_clustering():
    """Verify ArticleFilterPipeline processes consensus clusters in category grouping and process_flat."""
    ref_time = datetime(2026, 10, 31, 12, 0, 0, tzinfo=timezone.utc)
    pipeline = ArticleFilterPipeline(
        categories=["경제·금융"],
        max_hours=24.0,
        max_per_category=5,
        enable_clustering=True,
        reference_time=ref_time,
    )

    art_cons1 = Article(
        id="c-1",
        title="코스피 외국인 대규모 순매수에 2600선 탈환 성공",
        summary="외국인 투자자들의 집중 매수세에 힘입어 코스피 지수가 2600선을 회복했다.",
        url="https://news.com/c1",
        outlet="언론1",
        published_at=(ref_time - timedelta(hours=3)).isoformat(),
        category="경제·금융",
    )
    art_cons2 = Article(
        id="c-2",
        title="코스피, 외국인 순매수 힘입어 2600선 단숨에 회복",
        summary="코스피가 외국인 순매수세로 2600선을 재탈환했다.",
        url="https://news.com/c2",
        outlet="언론2",
        published_at=(ref_time - timedelta(hours=3)).isoformat(),
        category="경제·금융",
    )
    art_single = Article(
        id="single-1",
        title="국고채 3년물 금리 연 2.9%로 하락 마감",
        summary="채권시장에서 국고채 3년 만기 금리가 하락세를 보였다.",
        url="https://news.com/s1",
        outlet="언론1",
        published_at=(ref_time - timedelta(hours=1)).isoformat(),
        category="경제·금융",
    )

    grouped = pipeline.process([art_cons1, art_cons2, art_single])
    assert len(grouped["경제·금융"]) == 2
    # The 2-outlet consensus story should be first
    assert grouped["경제·금융"][0].id in ("c-1", "c-2")
    assert grouped["경제·금융"][1].id == "single-1"

    flat = pipeline.process_flat([art_cons1, art_cons2, art_single])
    assert len(flat) == 2
    assert flat[0].id in ("c-1", "c-2")
    assert flat[1].id == "single-1"


def test_article_body_extractor_html_parsing():
    """Verify ArticleBodyExtractor cleans script/style tags and extracts from various selectors."""
    extractor = ArticleBodyExtractor(max_chars=900)

    # 1. <article> selector
    html_article = """
    <html><body>
    <article>
        <h1>기사 헤드라인</h1>
        <script>var x = 1;</script>
        <p>첫 번째 문단 내용입니다.</p>
        <style>.ad { display: none; }</style>
        <p>두 번째 문단 내용입니다.</p>
    </article>
    </body></html>
    """
    body1 = extractor.extract_text_from_html(html_article)
    assert "첫 번째 문단 내용입니다." in body1
    assert "두 번째 문단 내용입니다." in body1
    assert "var x = 1" not in body1
    assert "display: none" not in body1

    # 2. <div class="article_view"> selector (Daum/Kakao)
    html_div_class = """
    <html><body>
    <div class="article_view">
        <p>다음 뉴스 본문 단락입니다.</p>
        <p>상세 설명 단락입니다.</p>
    </div>
    </body></html>
    """
    body2 = extractor.extract_text_from_html(html_div_class)
    assert "다음 뉴스 본문 단락입니다." in body2
    assert "상세 설명 단락입니다." in body2

    # 3. <div id="articleBody"> selector (Naver)
    html_div_id = """
    <html><body>
    <div id="articleBody">
        <p>네이버 뉴스 본문 단락 1입니다.</p>
        <p>네이버 뉴스 본문 단락 2입니다.</p>
    </div>
    </body></html>
    """
    body3 = extractor.extract_text_from_html(html_div_id)
    assert "네이버 뉴스 본문 단락 1입니다." in body3

    # 4. Fallback <p> tags
    html_p = """
    <html><body>
    <nav>네비게이션 메뉴</nav>
    <p>일반 문단 텍스트입니다.</p>
    <footer>하단 저작권 정보</footer>
    </body></html>
    """
    body4 = extractor.extract_text_from_html(html_p)
    assert "일반 문단 텍스트입니다." in body4
    assert "네비게이션 메뉴" not in body4
    assert "하단 저작권 정보" not in body4


def test_article_body_extractor_truncation():
    """Verify extracted body text is truncated to ~900 characters."""
    extractor = ArticleBodyExtractor(max_chars=900)
    long_content = "<article><p>" + ("가나다라마바사 " * 150) + "</p></article>"
    extracted = extractor.extract_text_from_html(long_content)
    assert len(extracted) <= 900
    assert len(extracted) > 850


def test_article_body_extractor_network_mocking():
    """Verify ArticleBodyExtractor fetches and enriches article with mocked HTTP response."""
    extractor = ArticleBodyExtractor()
    mock_html = b"<html><body><article><p>\xed\x95\x9c\xea\xb5\xad\xec\x9d\x80\xed\x96\x89 \xea\xb8\x88\xeb\xa6\xac \xec\x9d\xb8\xed\x95\x98 \xeb\xb3\xb8\xeb\xac\xb8</p></article></body></html>"

    mock_resp = MagicMock()
    mock_resp.headers = {"Content-Type": "text/html; charset=utf-8"}
    mock_resp.read.return_value = mock_html
    mock_resp.__enter__.return_value = mock_resp
    mock_resp.__exit__.return_value = None

    with patch("urllib.request.urlopen", return_value=mock_resp):
        art = Article(
            id="mock-1",
            title="한국은행 금리 인하",
            summary="기본 요약",
            url="https://news.example.com/mock-1",
            outlet="언론사",
            published_at="2026-10-31T00:00:00Z",
        )
        enriched = extractor.enrich_article(art)
        assert "한국은행 금리 인하 본문" in enriched.body


def test_article_body_extractor_network_error_fallback():
    """Verify ArticleBodyExtractor falls back to article.summary when network request fails."""
    extractor = ArticleBodyExtractor()

    with patch("urllib.request.urlopen", side_effect=urllib.error.URLError("Connection refused")):
        art = Article(
            id="fail-1",
            title="네트워크 실패 기사",
            summary="네트워크 실패 시 사용되는 안전한 요약문입니다.",
            url="https://invalid.example.com/fail",
            outlet="언론사",
            published_at="2026-10-31T00:00:00Z",
        )
        enriched = extractor.enrich_article(art)
        assert enriched.body == "네트워크 실패 시 사용되는 안전한 요약문입니다."


def test_enrich_articles_with_body_concurrent():
    """Verify enrich_articles_with_body concurrently enriches multiple articles."""
    mock_html = b"<html><body><article><p>\xec\x84\xb1\xea\xb3\xb5\xec\xa0\x81\xec\x9c\xbc\xeb\xa1\x9c \xec\xb6\x94\xec\xb6\x9c\xeb\x90\x9c \xeb\xb3\xb8\xeb\xac\xb8 \xed\x85\x8d\xec\x8a\xa4\xed\x8a\xb8\xec\x9e\x85\xeb\x8b\x88\xeb\x8b\xa4.</p></article></body></html>"

    mock_resp = MagicMock()
    mock_resp.headers = {"Content-Type": "text/html; charset=utf-8"}
    mock_resp.read.return_value = mock_html
    mock_resp.__enter__.return_value = mock_resp
    mock_resp.__exit__.return_value = None

    articles = [
        Article(
            id=f"c-{i}",
            title=f"동시 처리 기사 {i}",
            summary=f"요약 {i}",
            url=f"https://news.com/{i}",
            outlet="언론사",
            published_at="2026-10-31T00:00:00Z",
        )
        for i in range(5)
    ]

    with patch("urllib.request.urlopen", return_value=mock_resp):
        enriched_list = enrich_articles_with_body(articles, max_workers=3)

    assert len(enriched_list) == 5
    for idx, art in enumerate(enriched_list):
        assert art.id == f"c-{idx}"
        assert "성공적으로 추출된 본문 텍스트입니다." in art.body


"""Unit tests for NewsSummarizer, category clustering, schema formatting, and fallback logic."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest

from src.ingest.models import Article
from src.llm.client import GeminiAPIError, GeminiClient
from src.llm.summarizer import NewsSummarizer


@pytest.fixture
def sample_articles() -> list[Article]:
    """Provide a diverse list of sample candidate articles across categories."""
    return [
        Article(
            id="pol-001",
            title="국회 본회의 주요 민생 법안 처리 합의",
            summary="여야 원내대표가 정기국회 회기 내 주요 법안 처리에 합의했습니다.",
            url="https://news.example.com/pol/001",
            outlet="연합뉴스",
            published_at="2026-10-25T08:00:00+00:00",
            category="정치",
            category_id=1,
        ),
        Article(
            id="pol-002",
            title="선거제 개편 공청회 개최",
            summary="국회 정개특위에서 선거제 개편 방안에 대한 전문가 의견을 수렴했습니다.",
            url="https://news.example.com/pol/002",
            outlet="뉴시스",
            published_at="2026-10-25T08:10:00+00:00",
            category="정치",
            category_id=1,
        ),
        Article(
            id="econ-001",
            title="한국은행 기준금리 현행 연 3.50% 유지",
            summary="금융통화위원회가 가계부채 및 환율 변동성을 감안하여 금리를 동결했습니다.",
            url="https://news.example.com/econ/001",
            outlet="매일경제",
            published_at="2026-10-25T08:15:00+00:00",
            category="경제·금융",
            category_id=2,
        ),
        Article(
            id="tech-001",
            title="차세대 온디바이스 AI 칩셋 상용화 발표",
            summary="국내 테크 기업이 초경량 AI 추론 칩셋 양산에 돌입했습니다.",
            url="https://news.example.com/tech/001",
            outlet="전자신문",
            published_at="2026-10-25T08:30:00+00:00",
            category="AI·빅테크",
            category_id=6,
        ),
        Article(
            id="soc-001",
            title="가을철 교통안전 강화 종합 대책 시행",
            summary="경찰청이 행락철 주요 고속도로 음주운전 및 과속 단속을 강화합니다.",
            url="https://news.example.com/soc/001",
            outlet="YTN",
            published_at="2026-10-25T08:45:00+00:00",
            category="사회",
            category_id=4,
        ),
    ]


# ============================================================================
# 1. Category Grouping Tests
# ============================================================================

def test_group_articles_by_category_explicit_ids(sample_articles: list[Article]):
    """Verify articles with explicit category_id are correctly grouped."""
    summarizer = NewsSummarizer()
    grouped = summarizer.group_articles_by_category(sample_articles)

    assert set(grouped.keys()) == {1, 2, 4, 6}
    assert len(grouped[1]) == 2
    assert len(grouped[2]) == 1
    assert len(grouped[4]) == 1
    assert len(grouped[6]) == 1
    assert grouped[1][0].id == "pol-001"
    assert grouped[1][1].id == "pol-002"


def test_group_articles_by_category_alias_and_fallback():
    """Verify category name and alias mapping when category_id is missing."""
    summarizer = NewsSummarizer()
    articles = [
        Article(
            id="art-alias-1",
            title="경제 관련 기사",
            summary="요약",
            url="https://example.com/1",
            outlet="언론사",
            published_at="2026-10-25T08:00:00+00:00",
            category="경제",  # Alias for 경제·금융 (id 2)
            category_id=None,
        ),
        Article(
            id="art-alias-2",
            title="인공지능 뉴스",
            summary="요약",
            url="https://example.com/2",
            outlet="언론사",
            published_at="2026-10-25T08:00:00+00:00",
            category="인공지능",  # Alias for AI·빅테크 (id 6)
            category_id=None,
        ),
        Article(
            id="art-unknown",
            title="미분류 기사",
            summary="요약",
            url="https://example.com/3",
            outlet="언론사",
            published_at="2026-10-25T08:00:00+00:00",
            category="완전생소카테고리",
            category_id=None,
        ),
    ]

    grouped = summarizer.group_articles_by_category(articles)
    assert 2 in grouped
    assert grouped[2][0].id == "art-alias-1"
    assert 6 in grouped
    assert grouped[6][0].id == "art-alias-2"
    assert 1 in grouped  # Unknown defaults to category 1 (정치)
    assert grouped[1][0].id == "art-unknown"


# ============================================================================
# 2. Synthesis with Mock Gemini Client
# ============================================================================

def test_summarize_articles_successful_mock_client(sample_articles: list[Article]):
    """Verify end-to-end synthesis returning valid schema with exactly 3 headlines."""
    mock_client = MagicMock(spec=GeminiClient)
    mock_client.generate_json.return_value = {
        "topHeadlines": [
            {
                "id": "th-1",
                "categoryId": 1,
                "headline": "국회 민생 법안 합의 통과",
                "summary": "여야가 정기국회 주요 법안을 합의 처리했습니다.",
                "impact": "정치적 대치가 완화되고 민생 정책에 속도가 붙을 전망입니다.",
                "deepDive": {
                    "lensTitle": "의도와 실현 가능성",
                    "sections": [
                        {"label": "왜 지금 나왔나 (숨은 셈법)", "content": "정기국회 폐회를 앞두고 여야 지도부가 민생 법안 처리에 전격 합의했어요."},
                        {"label": "실제 통과·시행 가능성과 효력", "content": "본회의 의결 즉시 정부로 이송되어 즉각적인 법적 효력을 발휘할 예정이에요."},
                    ],
                },
                "links": [{"title": "연합뉴스 - 국회 합의", "url": "https://news.example.com/pol/001"}],
            },
            {
                "id": "th-2",
                "categoryId": 2,
                "headline": "한은 기준금리 동결 결정",
                "summary": "한국은행이 기준금리를 3.50%로 유지했습니다.",
                "impact": "금융 안정 기조를 유지하며 물가 추이를 주시합니다.",
                "deepDive": {
                    "lensTitle": "착시 제거 & 내 지갑 타격",
                    "sections": [
                        {"label": "지표·발표 이면의 맹점", "content": "물가 지표 안정세 이면에 경기 둔화 우려가 여전히 상존하고 있어요."},
                        {"label": "금리·물가·내 지갑에 미치는 영향", "content": "대출 금리 부담 완화까지는 시차가 발생할 것으로 보여요."},
                    ],
                },
                "links": [{"title": "매경 - 한은 발표", "url": "https://news.example.com/econ/001"}],
            },
            {
                "id": "th-3",
                "categoryId": 6,
                "headline": "온디바이스 AI 칩셋 양산",
                "summary": "국내 테크 기업이 초경량 AI 칩셋 양산에 들어갔습니다.",
                "impact": "온디바이스 AI 생태계 확장이 본격화될 것으로 보입니다.",
                "deepDive": {
                    "lensTitle": "거품 vs 진짜 기술 변곡점",
                    "sections": [
                        {"label": "마케팅 빼고 진짜 바뀐 기술 본질", "content": "네트워크 없이 기기 자체에서 고성능 LLM 추론이 가능해졌어요."},
                        {"label": "개발자·실무·생태계 판도 변화", "content": "모바일 및 엣지 디바이스용 AI 앱 개발 수요가 급증하고 있어요."},
                    ],
                },
                "links": [{"title": "전자신문 - 칩셋 양산", "url": "https://news.example.com/tech/001"}],
            },
        ],
        "articles": [
            {
                "id": "art-1",
                "categoryId": 4,
                "headline": "가을철 고속도로 단속 강화",
                "summary": "경찰청이 고속도로 특별 단속을 실시합니다.",
                "impact": "교통사고 예방과 안전 운전 문화 정착이 기대됩니다.",
                "deepDive": {
                    "lensTitle": "배경 맥락 & 행동 지침",
                    "sections": [
                        {"label": "사안의 구조적 배경", "content": "가을 행락철 이동량 증가에 따른 사고 위험 선제 대응 차원이에요."},
                        {"label": "시민이 챙겨야 할 실질적 체크포인트", "content": "장거리 운전 전 차량 점검과 휴게소 필수 휴식을 지켜야 해요."},
                    ],
                },
                "links": [{"title": "YTN - 단속 보도", "url": "https://news.example.com/soc/001"}],
            }
        ],
    }

    summarizer = NewsSummarizer(client=mock_client)
    briefing = summarizer.summarize_articles(sample_articles, briefing_date="2026-10-25T09:00:00+00:00")

    assert briefing["briefingDate"] == "2026-10-25T09:00:00+00:00"
    assert len(briefing["topHeadlines"]) == 3
    assert len(briefing["articles"]) == 1

    # Check topHeadlines properties
    for idx, hl in enumerate(briefing["topHeadlines"], start=1):
        assert isinstance(hl["id"], int)
        assert hl["id"] == idx
        assert isinstance(hl["categoryId"], int)
        assert isinstance(hl["headline"], str)
        assert isinstance(hl["summary"], str)
        assert isinstance(hl["impact"], str)
        assert "deepDive" in hl
        assert hl["deepDive"]["lensTitle"]
        assert len(hl["deepDive"]["sections"]) == 2
        for sec in hl["deepDive"]["sections"]:
            assert "label" in sec
            assert "content" in sec
        assert len(hl["links"]) > 0
        assert "url" in hl["links"][0]

    # Check article properties
    art = briefing["articles"][0]
    assert isinstance(art["id"], int)
    assert art["id"] == 4
    assert art["categoryId"] == 4
    assert art["headline"] == "가을철 고속도로 단속 강화"
    assert "deepDive" in art
    assert art["deepDive"]["lensTitle"] == "배경 맥락 & 행동 지침"
    assert len(art["deepDive"]["sections"]) == 2


def test_summarize_articles_in_mock_mode(sample_articles: list[Article]):
    """Verify execution with GeminiClient(mock_mode=True) without external network."""
    client = GeminiClient(mock_mode=True)
    summarizer = NewsSummarizer(client=client)

    briefing = summarizer.summarize_articles(sample_articles)

    assert "briefingDate" in briefing
    assert len(briefing["topHeadlines"]) == 3
    assert len(briefing["articles"]) >= 1
    for hl in briefing["topHeadlines"]:
        assert isinstance(hl["categoryId"], int)
        assert hl["headline"]
        assert hl["summary"]
        assert hl["impact"]
        assert "deepDive" in hl
        assert hl["deepDive"]["lensTitle"]
        assert len(hl["deepDive"]["sections"]) == 2
        assert hl["links"]

    for art in briefing["articles"]:
        assert "deepDive" in art
        assert art["deepDive"]["lensTitle"]
        assert len(art["deepDive"]["sections"]) == 2


# ============================================================================
# 3. Fallback and Error Handling Tests
# ============================================================================

def test_fallback_on_gemini_api_error(sample_articles: list[Article]):
    """Verify automatic fallback briefing generation when GeminiAPIError occurs."""
    failing_client = MagicMock(spec=GeminiClient)
    failing_client.generate_json.side_effect = GeminiAPIError(
        message="HTTP 429: Quota exceeded",
        status_code=429,
    )

    summarizer = NewsSummarizer(client=failing_client, fallback_on_error=True)
    briefing = summarizer.summarize_articles(sample_articles, briefing_date="2026-10-25T10:00:00+00:00")

    assert briefing["briefingDate"] == "2026-10-25T10:00:00+00:00"
    assert len(briefing["topHeadlines"]) == 3
    assert len(briefing["articles"]) > 0

    # Ensure all items conform to dashboard schema
    for hl in briefing["topHeadlines"]:
        assert isinstance(hl["categoryId"], int)
        assert hl["headline"]
        assert hl["summary"]
        assert hl["impact"]
        assert "deepDive" in hl
        assert hl["deepDive"]["lensTitle"]
        assert len(hl["deepDive"]["sections"]) == 2
        assert isinstance(hl["links"], list)
        assert len(hl["links"]) > 0

    for art in briefing["articles"]:
        assert "deepDive" in art
        assert art["deepDive"]["lensTitle"]
        assert len(art["deepDive"]["sections"]) == 2


def test_re_raise_error_when_fallback_disabled(sample_articles: list[Article]):
    """Verify exception is re-raised when fallback_on_error is False."""
    failing_client = MagicMock(spec=GeminiClient)
    failing_client.generate_json.side_effect = GeminiAPIError(
        message="HTTP 503: Unavailable",
        status_code=503,
    )

    summarizer = NewsSummarizer(client=failing_client, fallback_on_error=False)

    with pytest.raises(GeminiAPIError, match="503"):
        summarizer.summarize_articles(sample_articles)


# ============================================================================
# 4. Schema Normalization & Edge Cases
# ============================================================================

def test_normalize_missing_links(sample_articles: list[Article]):
    """Verify missing links in LLM output are filled with candidate article links."""
    mock_client = MagicMock(spec=GeminiClient)
    mock_client.generate_json.return_value = {
        "topHeadlines": [
            {
                "id": "th-1",
                "categoryId": 1,
                "headline": "국회 법안 통과",
                "summary": "법안 통과 요약",
                "impact": "법안 통과 파급",
                "links": [],  # Empty links from LLM
            },
            {
                "id": "th-2",
                "categoryId": 2,
                "headline": "금리 동결",
                "summary": "금리 요약",
                "impact": "금리 파급",
                "links": None,  # None links
            },
            {
                "id": "th-3",
                "categoryId": 6,
                "headline": "AI 칩셋",
                "summary": "AI 요약",
                "impact": "AI 파급",
                # Missing links key entirely
            },
        ],
        "articles": [
            {
                "id": "art-1",
                "categoryId": 4,
                "headline": "교통 대책",
                "summary": "교통 요약",
                "impact": "교통 파급",
                "links": [],
            }
        ],
    }

    summarizer = NewsSummarizer(client=mock_client)
    briefing = summarizer.summarize_articles(sample_articles)

    assert len(briefing["topHeadlines"]) == 3
    for hl in briefing["topHeadlines"]:
        assert isinstance(hl["links"], list)
        assert len(hl["links"]) > 0
        assert hl["links"][0]["url"]

    assert len(briefing["articles"][0]["links"]) > 0


def test_normalize_coerce_category_id_and_headline_count(sample_articles: list[Article]):
    """Verify string categoryId coercion and enforce exactly 3 topHeadlines."""
    mock_client = MagicMock(spec=GeminiClient)
    # LLM returns string categoryId and only 1 headline
    mock_client.generate_json.return_value = {
        "topHeadlines": [
            {
                "id": "th-single",
                "categoryId": "2",  # String instead of int
                "headline": "단일 헤드라인",
                "summary": "요약",
                "impact": "파급",
                "links": [{"title": "기사", "url": "https://example.com/1"}],
            }
        ],
        "articles": [],
    }

    summarizer = NewsSummarizer(client=mock_client)
    briefing = summarizer.summarize_articles(sample_articles)

    # Must be expanded to exactly 3 topHeadlines
    assert len(briefing["topHeadlines"]) == 3
    assert briefing["topHeadlines"][0]["categoryId"] == 2
    assert isinstance(briefing["topHeadlines"][0]["categoryId"], int)
    assert isinstance(briefing["topHeadlines"][1]["categoryId"], int)
    assert isinstance(briefing["topHeadlines"][2]["categoryId"], int)


def test_normalize_trims_excess_headlines(sample_articles: list[Article]):
    """Verify more than 3 topHeadlines are trimmed down to exactly 3."""
    mock_client = MagicMock(spec=GeminiClient)
    mock_client.generate_json.return_value = {
        "topHeadlines": [
            {"id": f"th-{i}", "categoryId": 1, "headline": f"헤드라인 {i}", "summary": "요약", "impact": "파급", "links": [{"title": "제목", "url": "https://example.com"}]}
            for i in range(5)
        ],
        "articles": [],
    }

    summarizer = NewsSummarizer(client=mock_client)
    briefing = summarizer.summarize_articles(sample_articles)

    assert len(briefing["topHeadlines"]) == 3


def test_empty_candidate_articles():
    """Verify summarize_articles handles empty input gracefully without dummy placeholders."""
    client = GeminiClient(mock_mode=True)
    summarizer = NewsSummarizer(client=client)

    briefing = summarizer.summarize_articles([])

    assert "briefingDate" in briefing
    assert len(briefing["topHeadlines"]) == 0
    assert len(briefing["articles"]) == 0


def test_briefing_date_datetime_and_string_handling(sample_articles: list[Article]):
    """Verify datetime object and custom ISO string formatting for briefingDate."""
    client = GeminiClient(mock_mode=True)
    summarizer = NewsSummarizer(client=client)

    # With datetime object
    dt = datetime(2026, 10, 25, 12, 30, tzinfo=timezone.utc)
    res_dt = summarizer.summarize_articles(sample_articles, briefing_date=dt)
    assert res_dt["briefingDate"] == "2026-10-25T12:30:00+00:00"

    # With ISO string
    iso_str = "2026-10-25T21:30:00+09:00"
    res_str = summarizer.summarize_articles(sample_articles, briefing_date=iso_str)
    assert res_str["briefingDate"] == "2026-10-25T21:30:00+09:00"


def test_extract_fallback_briefing_directly(sample_articles: list[Article]):
    """Verify direct call to extract_fallback_briefing produces valid dashboard schema."""
    summarizer = NewsSummarizer()
    grouped = summarizer.group_articles_by_category(sample_articles)

    briefing = summarizer.extract_fallback_briefing(grouped, briefing_date="2026-10-25T08:00:00Z")

    assert briefing["briefingDate"] == "2026-10-25T08:00:00Z"
    assert len(briefing["topHeadlines"]) == 3
    assert len(briefing["articles"]) >= 2

    # Check required schema keys
    for item in briefing["topHeadlines"] + briefing["articles"]:
        assert "id" in item
        assert "categoryId" in item
        assert isinstance(item["categoryId"], int)
        assert "headline" in item
        assert "summary" in item
        assert "impact" in item
        assert "deepDive" in item
        assert "lensTitle" in item["deepDive"]
        assert "sections" in item["deepDive"]
        assert len(item["deepDive"]["sections"]) == 2
        for sec in item["deepDive"]["sections"]:
            assert "label" in sec
            assert "content" in sec
            assert any(sec["content"].endswith(ending) for ending in ("요.", "있어요.", "돼요.", "해요."))
        assert "links" in item
        assert isinstance(item["links"], list)
        assert len(item["links"]) > 0


def test_sanitize_links_rejects_search_engine_queries(sample_articles: list[Article]):
    """Verify _sanitize_links filters out search engine query URLs and falls back to candidate URLs."""
    summarizer = NewsSummarizer()
    cat_links = {1: [{"title": "진짜 기사", "url": "https://www.yna.co.kr/view/123"}]}
    all_links = [{"title": "진짜 기사", "url": "https://www.yna.co.kr/view/123"}]

    polluted_links = [
        {"title": "네이버 검색", "url": "https://search.naver.com/search.naver?query=test"},
        {"title": "다음 검색", "url": "https://search.daum.net/search?q=test"},
        {"title": "구글 검색", "url": "https://www.google.com/search?q=test"},
    ]

    cleaned = summarizer._sanitize_links(polluted_links, cat_id=1, cat_links=cat_links, all_links=all_links)
    assert len(cleaned) == 1
    assert cleaned[0]["url"] == "https://www.yna.co.kr/view/123"


# ============================================================================
# 5. Category Batching, Partial Failure Fallback & DeepDive Lenses Tests
# ============================================================================

def test_category_batching_multiple_chunks():
    """Verify category batching partitions active categories and invokes Gemini in chunks."""
    articles = [
        Article(id=f"art-{cid}", title=f"제목 {cid}", summary="요약", url=f"https://example.com/{cid}", outlet="언론사", published_at="2026-10-25T08:00:00Z", category_id=cid)
        for cid in [1, 2, 4, 6, 7]  # 5 active categories
    ]

    mock_client = MagicMock(spec=GeminiClient)

    def fake_generate_json(contents, system_instruction, response_schema):
        if "[Category ID: 1]" in contents:
            return {
                "topHeadlines": [
                    {"id": 1, "categoryId": 1, "headline": "정치 톱뉴스", "summary": "정치 요약이에요.", "impact": "정치 파급이에요.", "links": [{"title": "기사1", "url": "https://example.com/1"}]},
                    {"id": 2, "categoryId": 2, "headline": "경제 톱뉴스", "summary": "경제 요약이에요.", "impact": "경제 파급이에요.", "links": [{"title": "기사2", "url": "https://example.com/2"}]},
                ],
                "articles": [
                    {"id": 3, "categoryId": 1, "headline": "정치 일반", "summary": "요약이에요.", "impact": "파급이에요.", "links": [{"title": "기사1", "url": "https://example.com/1"}]},
                ],
            }
        elif "[Category ID: 4]" in contents:
            return {
                "topHeadlines": [
                    {"id": 4, "categoryId": 4, "headline": "사회 톱뉴스", "summary": "사회 요약이에요.", "impact": "사회 파급이에요.", "links": [{"title": "기사4", "url": "https://example.com/4"}]},
                ],
                "articles": [
                    {"id": 5, "categoryId": 6, "headline": "빅테크 일반", "summary": "요약이에요.", "impact": "파급이에요.", "links": [{"title": "기사6", "url": "https://example.com/6"}]},
                ],
            }
        else:
            return {
                "topHeadlines": [
                    {"id": 6, "categoryId": 7, "headline": "통신 톱뉴스", "summary": "통신 요약이에요.", "impact": "통신 파급이에요.", "links": [{"title": "기사7", "url": "https://example.com/7"}]},
                ],
                "articles": [],
            }

    mock_client.generate_json.side_effect = fake_generate_json
    summarizer = NewsSummarizer(client=mock_client)

    # 5 categories with batch_size=2 should create 3 chunks: [1, 2], [4, 6], [7]
    briefing = summarizer.summarize_articles(articles, batch_size=2)

    assert mock_client.generate_json.call_count == 3
    assert len(briefing["topHeadlines"]) == 3
    assert len(briefing["articles"]) >= 2
    for item in briefing["topHeadlines"] + briefing["articles"]:
        assert "deepDive" in item
        assert "lensTitle" in item["deepDive"]
        assert len(item["deepDive"]["sections"]) == 2


def test_partial_batch_failure_fallback():
    """Verify that when one chunk fails, only that chunk falls back to extractive while others succeed."""
    articles = [
        Article(id=f"art-{cid}", title=f"제목 {cid}", summary=f"요약 {cid}", url=f"https://example.com/{cid}", outlet="언론사", published_at="2026-10-25T08:00:00Z", category_id=cid)
        for cid in [1, 2, 4, 6]  # 4 active categories
    ]

    mock_client = MagicMock(spec=GeminiClient)

    # Chunk 1 ([1, 2]) succeeds, Chunk 2 ([4, 6]) raises GeminiAPIError
    def fake_generate_json(contents, system_instruction, response_schema):
        if "[Category ID: 1]" in contents:
            return {
                "topHeadlines": [
                    {
                        "id": 1,
                        "categoryId": 1,
                        "headline": "LLM 성공 정치 헤드라인",
                        "summary": "정치 분석 요약이에요.",
                        "impact": "정치 파급이에요.",
                        "deepDive": {
                            "lensTitle": "의도와 실현 가능성",
                            "sections": [
                                {"label": "왜 지금 나왔나 (숨은 셈법)", "content": "선거 국면 전환을 위한 전략적 카드예요."},
                                {"label": "실제 통과·시행 가능성과 효력", "content": "여야 합의에 따라 통과 가능성이 매우 높아요."},
                            ],
                        },
                        "links": [{"title": "기사1", "url": "https://example.com/1"}],
                    },
                    {
                        "id": 2,
                        "categoryId": 2,
                        "headline": "LLM 성공 경제 헤드라인",
                        "summary": "경제 분석 요약이에요.",
                        "impact": "경제 파급이에요.",
                        "deepDive": {
                            "lensTitle": "착시 제거 & 내 지갑 타격",
                            "sections": [
                                {"label": "지표·발표 이면의 맹점", "content": "표면적 물가 안정 뒤에 실질 소득 정체가 숨어 있어요."},
                                {"label": "금리·물가·내 지갑에 미치는 영향", "content": "서민 가계의 이자 부담 완화가 기대돼요."},
                            ],
                        },
                        "links": [{"title": "기사2", "url": "https://example.com/2"}],
                    },
                ],
                "articles": [],
            }
        else:
            raise GeminiAPIError(message="HTTP 500: Internal Server Error", status_code=500)

    mock_client.generate_json.side_effect = fake_generate_json
    summarizer = NewsSummarizer(client=mock_client, fallback_on_error=True)

    # 4 categories with batch_size=2 -> 2 chunks
    briefing = summarizer.summarize_articles(articles, batch_size=2)

    assert mock_client.generate_json.call_count == 2
    assert len(briefing["topHeadlines"]) == 3

    # LLM items from chunk 1 are preserved
    headlines_text = [h["headline"] for h in briefing["topHeadlines"]]
    assert "LLM 성공 정치 헤드라인" in headlines_text
    assert "LLM 성공 경제 헤드라인" in headlines_text

    # Third headline comes from chunk 2 fallback (extractive fallback)
    assert any(h["categoryId"] in (4, 6) for h in briefing["topHeadlines"])

    # All items have compliant deepDive
    for item in briefing["topHeadlines"] + briefing["articles"]:
        assert "deepDive" in item
        assert "lensTitle" in item["deepDive"]
        assert len(item["deepDive"]["sections"]) == 2


def test_deep_dive_schema_compliance_all_10_categories():
    """Verify that all 10 category lenses conform to deepDive schema and style mandates."""
    from src.llm.prompts import CATEGORY_LENSES
    from src.llm.summarizer import make_default_deep_dive

    assert len(CATEGORY_LENSES) == 10

    for cat_id in range(1, 11):
        assert cat_id in CATEGORY_LENSES
        lens = CATEGORY_LENSES[cat_id]
        assert "lensTitle" in lens
        assert isinstance(lens["lensTitle"], str)
        assert len(lens["lensTitle"]) > 0
        assert "sections" in lens
        assert isinstance(lens["sections"], list)
        assert len(lens["sections"]) == 2

        # Check default deep dive generation
        dd = make_default_deep_dive(cat_id, headline="테스트 기사 제목")
        assert dd["lensTitle"] == lens["lensTitle"]
        assert len(dd["sections"]) == 2
        for idx, sec in enumerate(dd["sections"]):
            assert sec["label"] == lens["sections"][idx]
            assert isinstance(sec["content"], str)
            assert any(sec["content"].endswith(ending) for ending in ("요.", "있어요.", "돼요.", "해요."))


def test_build_briefing_prompt_includes_lenses_and_body_excerpt():
    """Verify build_briefing_prompt renders category lenses guide and article body excerpts."""
    from src.llm.prompts import build_briefing_prompt

    art = Article(
        id="art-body-1",
        title="본문 포함 기사",
        summary="요약 내용",
        url="https://example.com/art-body",
        outlet="테크뉴스",
        published_at="2026-10-25T08:00:00Z",
        category="AI·빅테크",
        category_id=6,
    )
    # Add body dynamically
    art.body = "기사의 상세 본문 내용으로 심층 팩트와 기술 배경 데이터가 풍부하게 포함되어 있습니다."

    grouped = {6: [art]}
    prompt = build_briefing_prompt(grouped)

    assert "Category DeepDive Analytical Lenses" in prompt
    assert "거품 vs 진짜 기술 변곡점" in prompt
    assert "Body Excerpt:" in prompt
    assert "기사의 상세 본문 내용" in prompt

"""Unit tests for Gemini client, prompt engineering, and retry resilience using google-genai SDK."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest
from google.genai import errors

from src.ingest.models import Article
from src.llm.client import GeminiAPIError, GeminiClient
from src.llm.prompts import (
    BRIEFING_RESPONSE_SCHEMA,
    DEFAULT_CATEGORIES,
    SYSTEM_PROMPT,
    build_briefing_prompt,
    load_default_categories,
)


# ============================================================================
# 1. Prompt and Schema Tests
# ============================================================================

def test_system_prompt_specifications():
    """Verify system prompt contains essential journalistic and schema rules."""
    assert "Editor-in-Chief" in SYSTEM_PROMPT
    assert "Korean" in SYSTEM_PROMPT
    assert "핵심" in SYSTEM_PROMPT
    assert "파급" in SYSTEM_PROMPT
    assert "bullet points" in SYSTEM_PROMPT
    assert "JSON" in SYSTEM_PROMPT


def test_briefing_response_schema_structure():
    """Verify briefing OpenAPI schema structure and required properties."""
    assert BRIEFING_RESPONSE_SCHEMA["type"] == "OBJECT"
    assert "topHeadlines" in BRIEFING_RESPONSE_SCHEMA["properties"]
    assert "articles" in BRIEFING_RESPONSE_SCHEMA["properties"]
    assert BRIEFING_RESPONSE_SCHEMA["required"] == ["topHeadlines", "articles"]

    th_props = BRIEFING_RESPONSE_SCHEMA["properties"]["topHeadlines"]["items"]["properties"]
    for req_field in ["id", "categoryId", "headline", "summary", "impact", "links"]:
        assert req_field in th_props

    assert th_props["id"]["type"] == "INTEGER"
    assert th_props["categoryId"]["type"] == "INTEGER"

    link_props = th_props["links"]["items"]["properties"]
    assert "title" in link_props
    assert "url" in link_props


def test_load_default_categories():
    """Verify loading default categories and fallback behavior."""
    cats = load_default_categories()
    assert isinstance(cats, list)
    assert len(cats) >= 5

    cat_map = {c["id"]: c["name"] for c in cats}
    assert cat_map.get(1) == "정치"
    assert cat_map.get(2) == "경제·금융"
    assert cat_map.get(6) == "AI·빅테크"


def test_build_briefing_prompt_formatting():
    """Verify prompt formatting compiles categorized articles into clean Markdown."""
    art1 = Article(
        id="art-1",
        title="국회 본회의 정치 개혁안 통과",
        url="https://news.example.com/pol/1",
        published_at="2026-10-25T10:00:00Z",
        outlet="연합뉴스",
        summary="여야 합의로 정치 개혁안이 가결되었습니다.",
        category="정치",
        category_id=1,
    )
    art2 = Article(
        id="art-2",
        title="반도체 수출 20% 증가",
        url="https://news.example.com/econ/1",
        published_at="2026-10-25T11:00:00Z",
        outlet="한국경제",
        summary="첨단 메모리 수요 폭증으로 수출이 반등했습니다.",
        category="경제·금융",
        category_id=2,
    )

    grouped = {1: [art1], 2: [art2]}
    prompt = build_briefing_prompt(grouped)

    assert "## Editorial & Synthesis Instructions" in prompt
    assert "## Ingested Candidate Articles (Total: 2 articles)" in prompt
    assert "[Category ID: 1] 정치 (1 articles)" in prompt
    assert "[연합뉴스] 국회 본회의 정치 개혁안 통과" in prompt
    assert "[Category ID: 2] 경제·금융 (1 articles)" in prompt
    assert "[한국경제] 반도체 수출 20% 증가" in prompt
    assert "Generate the briefing JSON adhering strictly to the response schema." in prompt


def test_build_briefing_prompt_empty_handling():
    """Verify prompt formatting when no articles are provided."""
    prompt = build_briefing_prompt({})
    assert "(No candidate articles provided)" in prompt


def test_build_briefing_prompt_custom_categories():
    """Verify prompt builder respects custom category metadata."""
    custom_cats = [
        {"id": 100, "name": "특수카테고리", "badgeColor": "gray"},
    ]
    art = Article(
        id="art-100",
        title="특수 이슈 발생",
        summary="특수 이슈 요약",
        url="https://news.example.com/special/1",
        outlet="특수언론",
        published_at="2026-10-25T12:00:00Z",
        category_id=100,
    )
    prompt = build_briefing_prompt({100: [art]}, categories=custom_cats)
    assert "[Category ID: 100] 특수카테고리 (1 articles)" in prompt


# ============================================================================
# 2. Client Initialization and Modes
# ============================================================================

def test_gemini_client_initialization_defaults(monkeypatch: pytest.MonkeyPatch):
    """Verify default parameters and environment variable resolution."""
    monkeypatch.setenv("GEMINI_API_KEY", "env-secret-key-1234")

    client = GeminiClient()
    assert client.api_key == "env-secret-key-1234"
    assert client.model == "gemini-2.0-flash"
    assert client.timeout == 30.0
    assert client.max_retries == 3
    assert client.base_backoff == 2.0
    assert not client.is_mock()


def test_gemini_client_custom_initialization():
    """Verify custom initialization options."""
    client = GeminiClient(
        api_key="custom-key-5678",
        model="gemini-2.5-pro",
        timeout=45.0,
        max_retries=5,
        base_backoff=1.5,
    )
    assert client.api_key == "custom-key-5678"
    assert client.model == "gemini-2.5-pro"
    assert client.timeout == 45.0
    assert client.max_retries == 5
    assert client.base_backoff == 1.5
    assert not client.is_mock()


def test_gemini_client_missing_api_key_raises_value_error(monkeypatch: pytest.MonkeyPatch):
    """Verify error raised when GEMINI_API_KEY is completely missing."""
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    with pytest.raises(ValueError, match="GEMINI_API_KEY must be provided"):
        GeminiClient(api_key=None)


def test_gemini_client_mock_key_enables_mock_mode(monkeypatch: pytest.MonkeyPatch):
    """Verify key with MOCK prefix automatically engages mock mode."""
    client = GeminiClient(api_key="MOCK_TEST_KEY")
    assert client.is_mock()

    res = client.generate_json("아무 프롬프트")
    assert "topHeadlines" in res
    assert "articles" in res
    assert len(res["topHeadlines"]) == 3
    assert res["topHeadlines"][0]["categoryId"] == 1
    assert "links" in res["topHeadlines"][0]


def test_gemini_client_dry_run_and_mock_mode_flags():
    """Verify dry_run and mock_mode flags bypass network calls without key."""
    client_dry = GeminiClient(dry_run=True)
    assert client_dry.is_mock()
    res_dry = client_dry.generate_json("프롬프트")
    assert len(res_dry["topHeadlines"]) == 3

    client_mock = GeminiClient(mock_mode=True)
    assert client_mock.is_mock()
    res_mock = client_mock.generate_json("프롬프트")
    assert len(res_mock["articles"]) >= 1


# ============================================================================
# 3. Successful Generation Tests
# ============================================================================

def test_generate_json_successful_call():
    """Verify successful call to google-genai Client and correct schema parsing."""
    client = GeminiClient(api_key="test-gemini-key", model="gemini-2.0-flash")

    mock_briefing = {
        "topHeadlines": [
            {
                "id": "th-1",
                "categoryId": 1,
                "headline": "정치 헤드라인",
                "summary": "정치 요약",
                "impact": "정치 파급",
                "links": [{"title": "기사 1", "url": "https://example.com/1"}],
            },
            {
                "id": "th-2",
                "categoryId": 2,
                "headline": "경제 헤드라인",
                "summary": "경제 요약",
                "impact": "경제 파급",
                "links": [{"title": "기사 2", "url": "https://example.com/2"}],
            },
            {
                "id": "th-3",
                "categoryId": 6,
                "headline": "IT 헤드라인",
                "summary": "IT 요약",
                "impact": "IT 파급",
                "links": [{"title": "기사 3", "url": "https://example.com/3"}],
            },
        ],
        "articles": [],
    }

    mock_resp = MagicMock()
    mock_resp.text = json.dumps(mock_briefing)

    with patch.object(client._genai_client.models, "generate_content", return_value=mock_resp) as mock_gen:
        result = client.generate_json(
            contents="기사 요약 프롬프트",
            system_instruction=SYSTEM_PROMPT,
            response_schema=BRIEFING_RESPONSE_SCHEMA,
        )

        assert mock_gen.call_count == 1
        call_kwargs = mock_gen.call_args[1]
        assert call_kwargs["model"] == "gemini-2.0-flash"
        assert call_kwargs["contents"] == "기사 요약 프롬프트"
        assert call_kwargs["config"].response_mime_type == "application/json"
        assert call_kwargs["config"].response_schema == BRIEFING_RESPONSE_SCHEMA

        assert len(result["topHeadlines"]) == 3
        assert result["topHeadlines"][0]["headline"] == "정치 헤드라인"


# ============================================================================
# 4. Retry and Backoff Logic Tests
# ============================================================================

def test_retry_on_429_exponential_backoff():
    """Verify HTTP 429 rate limit triggers exponential backoff and succeeds on retry."""
    client = GeminiClient(api_key="retry-key", max_retries=3, base_backoff=1.0)

    err_429 = errors.APIError(code=429, response_json={"error": "RESOURCE_EXHAUSTED"})
    mock_resp = MagicMock(text=json.dumps({"topHeadlines": [], "articles": []}))

    with patch.object(client._genai_client.models, "generate_content", side_effect=[err_429, mock_resp]) as mock_gen:
        with patch("time.sleep") as mock_sleep:
            res = client.generate_json("프롬프트")
            assert mock_gen.call_count == 2
            mock_sleep.assert_called_once_with(1.0)
            assert res == {"topHeadlines": [], "articles": []}


def test_retry_on_503_service_unavailable():
    """Verify HTTP 503 triggers backoff retries and succeeds on 3rd attempt."""
    client = GeminiClient(api_key="retry-key", max_retries=3, base_backoff=2.0)

    err_503 = errors.APIError(code=503, response_json={"error": "Service Unavailable"})
    mock_resp = MagicMock(text=json.dumps({"topHeadlines": [], "articles": []}))

    with patch.object(
        client._genai_client.models,
        "generate_content",
        side_effect=[err_503, err_503, mock_resp],
    ) as mock_gen:
        with patch("time.sleep") as mock_sleep:
            res = client.generate_json("프롬프트")
            assert mock_gen.call_count == 3
            assert mock_sleep.call_count == 2
            mock_sleep.assert_any_call(2.0)
            mock_sleep.assert_any_call(4.0)
            assert res == {"topHeadlines": [], "articles": []}


def test_retry_exhausted_raises_gemini_api_error():
    """Verify exhausting all retries on 429 raises GeminiAPIError."""
    client = GeminiClient(api_key="exhaust-key", max_retries=3, base_backoff=0.5)

    err_429 = errors.APIError(code=429, response_json={"error": "RESOURCE_EXHAUSTED"})

    with patch.object(client._genai_client.models, "generate_content", side_effect=err_429) as mock_gen:
        with patch("time.sleep"):
            with pytest.raises(GeminiAPIError) as exc_info:
                client.generate_json("프롬프트")
            assert exc_info.value.status_code == 429
            assert mock_gen.call_count == 3


def test_non_retryable_http_error_fails_immediately():
    """Verify non-retryable 400 Bad Request fails immediately without retry."""
    client = GeminiClient(api_key="fail-key", max_retries=3)

    err_400 = errors.APIError(code=400, response_json={"error": "INVALID_ARGUMENT"})

    with patch.object(client._genai_client.models, "generate_content", side_effect=err_400) as mock_gen:
        with patch("time.sleep") as mock_sleep:
            with pytest.raises(GeminiAPIError) as exc_info:
                client.generate_json("잘못된 요청")
            assert exc_info.value.status_code == 400
            assert mock_gen.call_count == 1
            mock_sleep.assert_not_called()


def test_retry_on_network_error():
    """Verify network connection errors trigger retry and backoff."""
    client = GeminiClient(api_key="network-key", max_retries=2, base_backoff=1.0)

    mock_resp = MagicMock(text=json.dumps({"topHeadlines": [], "articles": []}))

    with patch.object(
        client._genai_client.models,
        "generate_content",
        side_effect=[ConnectionResetError("Connection reset"), mock_resp],
    ) as mock_gen:
        with patch("time.sleep") as mock_sleep:
            res = client.generate_json("프롬프트")
            assert mock_gen.call_count == 2
            mock_sleep.assert_called_once_with(1.0)
            assert res == {"topHeadlines": [], "articles": []}


def test_malformed_gemini_json_response():
    """Verify malformed JSON response raises GeminiAPIError."""
    client = GeminiClient(api_key="malformed-key")

    mock_resp = MagicMock(text="<not>json</not>")

    with patch.object(client._genai_client.models, "generate_content", return_value=mock_resp):
        with pytest.raises(GeminiAPIError, match="Failed to parse Gemini model response as JSON"):
            client.generate_json("프롬프트")


def test_empty_response_text():
    """Verify empty response text raises GeminiAPIError."""
    client = GeminiClient(api_key="empty-key")

    mock_resp = MagicMock(text="")

    with patch.object(client._genai_client.models, "generate_content", return_value=mock_resp):
        with pytest.raises(GeminiAPIError, match="Empty response text from Gemini API"):
            client.generate_json("프롬프트")

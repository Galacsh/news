"""Unit tests for RSS models, feed parsing, text sanitization, and resilience."""

from __future__ import annotations

import hashlib
import io
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from src.ingest.models import Article, FeedSource
from src.ingest.rss import RSSFeedParser


# ============================================================================
# 1. Models Unit Tests
# ============================================================================


def test_article_model_instantiation_and_dict():
    """Verify Article dataclass fields, defaults, and dictionary export."""
    article = Article(
        id="test-id-123",
        title="Breaking News: Tech Innovation",
        summary="Summary of breaking news.",
        url="https://example.com/news/123",
        outlet="Tech Daily",
        published_at="2026-10-25T08:00:00+00:00",
        category="AI·빅테크",
    )
    assert article.id == "test-id-123"
    assert article.title == "Breaking News: Tech Innovation"
    assert article.outlet == "Tech Daily"
    assert article.category == "AI·빅테크"
    assert article.raw_data is None

    as_dict = article.to_dict()
    assert isinstance(as_dict, dict)
    assert as_dict["id"] == "test-id-123"
    assert as_dict["raw_data"] is None

    # With raw_data populated
    article_with_raw = Article(
        id="test-id-456",
        title="Title",
        summary="Summary",
        url="https://example.com/456",
        outlet="Outlet",
        published_at="2026-10-25T09:00:00+00:00",
        category="정치",
        raw_data={"source_guid": "guid-999"},
    )
    assert article_with_raw.raw_data == {"source_guid": "guid-999"}


def test_feedsource_model_instantiation_and_dict():
    """Verify FeedSource dataclass fields, default is_active, and to_dict."""
    source = FeedSource(
        name="Chosun Economy",
        url="https://biz.chosun.com/rss",
        category="경제·금융",
    )
    assert source.name == "Chosun Economy"
    assert source.url == "https://biz.chosun.com/rss"
    assert source.category == "경제·금융"
    assert source.is_active is True

    as_dict = source.to_dict()
    assert as_dict["is_active"] is True
    assert as_dict["name"] == "Chosun Economy"


# ============================================================================
# 2. Text Sanitization (clean_html) Tests
# ============================================================================


class TestTextSanitization:
    """Tests for HTML stripping, unescaping, and text normalization."""

    def test_strip_html_tags(self):
        html_input = "<p>First paragraph with <a href='https://link'>hyperlink</a>.</p>"
        expected = "First paragraph with hyperlink."
        assert RSSFeedParser.clean_html(html_input) == expected

    def test_strip_nested_and_multiline_tags(self):
        html_input = """
        <div>
            <h1>Headline</h1>
            <p>Text with <b>bold</b> and <i>italic</i></p>
        </div>
        """
        assert RSSFeedParser.clean_html(html_input) == "Headline Text with bold and italic"

    def test_strip_script_and_style_elements(self):
        html_input = (
            "<style>body { font-size: 14px; }</style>"
            "<p>Article body</p>"
            "<script type='text/javascript'>alert('xss');</script>"
        )
        assert RSSFeedParser.clean_html(html_input) == "Article body"

    def test_strip_html_comments(self):
        html_input = "<!-- banner ad start -->Safe news content<!-- banner ad end -->"
        assert RSSFeedParser.clean_html(html_input) == "Safe news content"

    def test_unescape_html_entities(self):
        html_input = "&lt;b&gt;Samsung &amp; Apple &quot;War&quot;&lt;/b&gt; &copy; 2026"
        # &lt;b&gt; becomes <b> then gets stripped; &amp; becomes &; &quot; becomes "; &copy; becomes ©
        assert RSSFeedParser.clean_html(html_input) == 'Samsung & Apple "War" © 2026'

    def test_korean_text_with_entities(self):
        html_input = "[단독] 현대차 &middot; 기아, &#39;전기차&#39; 신기술 공개"
        assert RSSFeedParser.clean_html(html_input) == "[단독] 현대차 · 기아, '전기차' 신기술 공개"

    def test_whitespace_normalization(self):
        html_input = "Multiple   spaces  and \n\n newlines \t with \xa0 non-breaking space."
        assert (
            RSSFeedParser.clean_html(html_input)
            == "Multiple spaces and newlines with non-breaking space."
        )

    def test_empty_and_none_inputs(self):
        assert RSSFeedParser.clean_html("") == ""
        assert RSSFeedParser.clean_html(None) == ""
        assert RSSFeedParser.clean_html("   ") == ""


# ============================================================================
# 3. ID Generation and Determinism Tests
# ============================================================================


class TestArticleIdGeneration:
    """Tests for deterministic SHA-256 hash generation."""

    def test_deterministic_sha256_hash(self):
        url = "https://news.example.com/articles/2026/10/25/12345"
        expected = hashlib.sha256(url.encode("utf-8")).hexdigest()
        assert RSSFeedParser.generate_article_id(url) == expected

    def test_whitespace_insensitivity(self):
        url1 = "https://news.example.com/item"
        url2 = "  https://news.example.com/item \n"
        assert RSSFeedParser.generate_article_id(url1) == RSSFeedParser.generate_article_id(url2)

    def test_fallback_to_title_when_url_empty(self):
        title = "Article Title Without URL"
        expected = hashlib.sha256(title.encode("utf-8")).hexdigest()
        assert RSSFeedParser.generate_article_id("", fallback_title=title) == expected


# ============================================================================
# 4. Date Parsing and Fallback Tests
# ============================================================================


class TestDateParsing:
    """Tests for ISO 8601 timestamp parsing and UTC fallback."""

    def test_parse_published_parsed_struct_time(self):
        struct = time.struct_time((2026, 10, 25, 8, 30, 0, 6, 298, 0))
        entry = {"published_parsed": struct}
        iso_str = RSSFeedParser.parse_published_date(entry)
        assert iso_str == "2026-10-25T08:30:00+00:00"

    def test_parse_updated_parsed_when_published_missing(self):
        struct = time.struct_time((2026, 10, 25, 9, 15, 0, 6, 298, 0))
        entry = {"updated_parsed": struct}
        iso_str = RSSFeedParser.parse_published_date(entry)
        assert iso_str == "2026-10-25T09:15:00+00:00"

    def test_parse_rfc822_pubdate_string(self):
        entry = {"pubDate": "Sun, 25 Oct 2026 08:00:00 +0000"}
        iso_str = RSSFeedParser.parse_published_date(entry)
        parsed_dt = datetime.fromisoformat(iso_str)
        assert parsed_dt.year == 2026
        assert parsed_dt.month == 10
        assert parsed_dt.day == 25
        assert parsed_dt.hour == 8

    def test_parse_iso8601_date_string(self):
        entry = {"published": "2026-10-25T14:20:00Z"}
        iso_str = RSSFeedParser.parse_published_date(entry)
        parsed_dt = datetime.fromisoformat(iso_str)
        assert parsed_dt.year == 2026
        assert parsed_dt.hour == 14

    def test_fallback_to_current_utc_when_missing_or_invalid(self):
        before = datetime.now(timezone.utc)
        iso_str = RSSFeedParser.parse_published_date({})
        after = datetime.now(timezone.utc)

        parsed_dt = datetime.fromisoformat(iso_str)
        assert before <= parsed_dt <= after
        assert parsed_dt.tzinfo is not None

        # Also when invalid string provided
        iso_invalid = RSSFeedParser.parse_published_date({"published": "not-a-valid-date"})
        parsed_invalid = datetime.fromisoformat(iso_invalid)
        assert parsed_invalid.year == before.year


# ============================================================================
# 5. RSS and Atom XML Parsing Tests
# ============================================================================


class TestXMLParsing:
    """Tests for parsing various RSS/Atom feeds and encodings."""

    SAMPLE_RSS_2 = """<?xml version="1.0" encoding="UTF-8"?>
    <rss version="2.0">
        <channel>
            <title>조선비즈</title>
            <link>https://biz.chosun.com</link>
            <description>조선비즈 경제 뉴스</description>
            <item>
                <title>&lt;b&gt;금리 인하&lt;/b&gt; 가능성에 코스피 상승 마감</title>
                <link>https://biz.chosun.com/news/101</link>
                <description>&lt;p&gt;한국은행 금융통화위원회가 &amp;hellip;&lt;/p&gt;</description>
                <category>경제·금융</category>
                <pubDate>Sun, 25 Oct 2026 07:00:00 +0000</pubDate>
            </item>
            <item>
                <title>AI 반도체 수요 급증... 글로벌 공급망 재편</title>
                <link>https://biz.chosun.com/news/102</link>
                <description>빅테크 기업들의 AI 칩 투자 경쟁이 치열해지고 있다.</description>
                <pubDate>Sun, 25 Oct 2026 07:30:00 +0000</pubDate>
            </item>
        </channel>
    </rss>
    """

    SAMPLE_ATOM = """<?xml version="1.0" encoding="utf-8"?>
    <feed xmlns="http://www.w3.org/2005/Atom">
        <title>Tech News Feed</title>
        <link href="https://technews.example.com" />
        <updated>2026-10-25T08:00:00Z</updated>
        <entry>
            <title>Next Gen Quantum Computing Unveiled</title>
            <link rel="alternate" href="https://technews.example.com/quantum" />
            <id>urn:uuid:1225c695-cfb8-4ebb-aaaa-80da344efa6a</id>
            <updated>2026-10-25T07:45:00Z</updated>
            <summary>&lt;div&gt;Researchers demonstrate 1000-qubit stability.&lt;/div&gt;</summary>
            <category term="AI·빅테크" />
        </entry>
    </feed>
    """

    def test_parse_rss2_normal(self):
        articles = RSSFeedParser.parse_xml(self.SAMPLE_RSS_2)
        assert len(articles) == 2

        first = articles[0]
        assert first.title == "금리 인하 가능성에 코스피 상승 마감"
        assert first.summary == "한국은행 금융통화위원회가 …"
        assert first.url == "https://biz.chosun.com/news/101"
        assert first.outlet == "조선비즈"
        assert first.category == "경제·금융"
        assert first.id == hashlib.sha256("https://biz.chosun.com/news/101".encode()).hexdigest()
        assert first.published_at.startswith("2026-10-25T07:00:00")
        assert first.raw_data is not None

        second = articles[1]
        assert second.title == "AI 반도체 수요 급증... 글로벌 공급망 재편"
        assert second.outlet == "조선비즈"

    def test_parse_rss2_outlet_and_category_override(self):
        articles = RSSFeedParser.parse_xml(
            self.SAMPLE_RSS_2,
            category="시장전망",
            outlet="조선일보 경제부",
        )
        assert len(articles) == 2
        for a in articles:
            assert a.category == "시장전망"
            assert a.outlet == "조선일보 경제부"

    def test_parse_atom_feed(self):
        articles = RSSFeedParser.parse_xml(self.SAMPLE_ATOM)
        assert len(articles) == 1
        item = articles[0]
        assert item.title == "Next Gen Quantum Computing Unveiled"
        assert item.url == "https://technews.example.com/quantum"
        assert item.summary == "Researchers demonstrate 1000-qubit stability."
        assert item.outlet == "Tech News Feed"
        assert item.category == "AI·빅테크"

    def test_parse_korean_euckr_encoding(self):
        euckr_xml = """<?xml version="1.0" encoding="euc-kr"?>
        <rss version="2.0">
            <channel>
                <title>한국경제</title>
                <link>https://hankyung.example.com</link>
                <item>
                    <title>코스피, 외국인 매수세에 1% 상승</title>
                    <link>https://hankyung.example.com/article1</link>
                    <description>외국인과 기관의 동반 순매수로 상승 마감했다.</description>
                </item>
            </channel>
        </rss>
        """
        raw_bytes = euckr_xml.encode("euc-kr")
        articles = RSSFeedParser.parse_xml(raw_bytes)
        assert len(articles) == 1
        assert articles[0].outlet == "한국경제"
        assert articles[0].title == "코스피, 외국인 매수세에 1% 상승"
        assert articles[0].summary == "외국인과 기관의 동반 순매수로 상승 마감했다."

    def test_parse_korean_cp949_without_declaration(self):
        plain_xml = """<rss version="2.0">
            <channel>
                <title>매일경제</title>
                <item>
                    <title>부동산 시장 동향 분석</title>
                    <link>https://mk.example.com/realestate</link>
                </item>
            </channel>
        </rss>
        """
        raw_bytes = plain_xml.encode("cp949")
        articles = RSSFeedParser.parse_xml(raw_bytes)
        assert len(articles) == 1
        assert articles[0].outlet == "매일경제"
        assert articles[0].title == "부동산 시장 동향 분석"

    def test_empty_and_whitespace_xml(self):
        assert RSSFeedParser.parse_xml("") == []
        assert RSSFeedParser.parse_xml(b"") == []
        assert RSSFeedParser.parse_xml("   \n\t   ") == []

    def test_malformed_xml_resilience(self):
        # Truncated garbage XML with no items
        garbage = "<?xml version='1.0'?><rss><channel><broken"
        articles = RSSFeedParser.parse_xml(garbage)
        assert articles == []

    def test_partial_valid_items_in_imperfect_xml(self):
        # XML with bozo error but valid item content
        imperfect_xml = """<rss version="2.0">
        <channel>
            <title>Imperfect Feed</title>
            <item>
                <title>Valid Item In Broken Channel</title>
                <link>https://example.com/valid</link>
                <description>Some description</description>
            </item>
        </channel>
        <!-- unclosed tag at bottom
        """
        articles = RSSFeedParser.parse_xml(imperfect_xml)
        assert len(articles) >= 1
        assert articles[0].title == "Valid Item In Broken Channel"

    def test_item_with_missing_link_uses_title_for_id(self):
        xml = """<rss version="2.0">
        <channel>
            <title>No Link Outlet</title>
            <item>
                <title>Headline with no url</title>
                <description>Body text</description>
            </item>
        </channel>
        </rss>
        """
        articles = RSSFeedParser.parse_xml(xml)
        assert len(articles) == 1
        assert articles[0].url == ""
        assert articles[0].title == "Headline with no url"
        assert articles[0].id == hashlib.sha256("Headline with no url".encode()).hexdigest()

    def test_item_with_neither_link_nor_title_is_skipped(self):
        xml = """<rss version="2.0">
        <channel>
            <title>Empty Item Outlet</title>
            <item>
                <description>Only description</description>
            </item>
        </channel>
        </rss>
        """
        articles = RSSFeedParser.parse_xml(xml)
        assert articles == []


# ============================================================================
# 6. Remote Fetching (parse_feed) & Network Resilience Tests
# ============================================================================


class TestFeedFetchingResilience:
    """Tests for HTTP fetching, timeout enforcement, and network error handling."""

    @patch("urllib.request.urlopen")
    def test_parse_feed_success(self, mock_urlopen):
        sample_content = b"""<?xml version="1.0" encoding="UTF-8"?>
        <rss version="2.0">
            <channel>
                <title>Remote News</title>
                <item>
                    <title>Remote Article</title>
                    <link>https://remote.com/1</link>
                    <description>Summary text</description>
                </item>
            </channel>
        </rss>
        """
        mock_response = MagicMock()
        mock_response.read.return_value = sample_content
        mock_response.__enter__.return_value = mock_response
        mock_urlopen.return_value = mock_response

        articles = RSSFeedParser.parse_feed(
            "https://remote.com/rss",
            category="사회",
            outlet="Custom Outlet",
            timeout=3.0,
        )

        assert len(articles) == 1
        assert articles[0].title == "Remote Article"
        assert articles[0].category == "사회"
        assert articles[0].outlet == "Custom Outlet"

        # Verify urllib.request.urlopen was called with timeout
        mock_urlopen.assert_called_once()
        req, kwargs = mock_urlopen.call_args
        assert kwargs.get("timeout") == 3.0
        # Verify custom user agent
        assert "KoreaNewsBriefingBot" in req[0].headers.get("User-agent", "")

    def test_parse_feed_empty_url(self):
        assert RSSFeedParser.parse_feed("") == []
        assert RSSFeedParser.parse_feed("   ") == []

    @patch("urllib.request.urlopen", side_effect=urllib.error.HTTPError("url", 404, "Not Found", {}, None))
    def test_parse_feed_http_404_error(self, mock_urlopen):
        articles = RSSFeedParser.parse_feed("https://example.com/not-found.xml")
        assert articles == []

    @patch("urllib.request.urlopen", side_effect=urllib.error.HTTPError("url", 500, "Server Error", {}, None))
    def test_parse_feed_http_500_error(self, mock_urlopen):
        articles = RSSFeedParser.parse_feed("https://example.com/server-error.xml")
        assert articles == []

    @patch("urllib.request.urlopen", side_effect=urllib.error.URLError("Connection refused"))
    def test_parse_feed_connection_refused(self, mock_urlopen):
        articles = RSSFeedParser.parse_feed("https://unreachable.example.com/rss")
        assert articles == []

    @patch("urllib.request.urlopen", side_effect=TimeoutError("Request timed out"))
    def test_parse_feed_timeout_error(self, mock_urlopen):
        articles = RSSFeedParser.parse_feed("https://slow.example.com/rss", timeout=1.0)
        assert articles == []

    @patch("urllib.request.urlopen", side_effect=Exception("Unexpected crash"))
    def test_parse_feed_unexpected_exception(self, mock_urlopen):
        articles = RSSFeedParser.parse_feed("https://crash.example.com/rss")
        assert articles == []

    def test_parser_instance_can_also_call_methods(self):
        """Verify RSSFeedParser works via both class and instance invocations."""
        parser = RSSFeedParser()
        articles = parser.parse_xml(
            """<rss version="2.0">
            <channel><title>Instance Test</title>
            <item><title>Item 1</title><link>https://ex.com/1</link></item>
            </channel></rss>"""
        )
        assert len(articles) == 1
        assert articles[0].title == "Item 1"

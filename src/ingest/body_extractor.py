"""Article body extraction and text enrichment module using BeautifulSoup4 and urllib."""

from __future__ import annotations

import concurrent.futures
import logging
import re
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from bs4 import BeautifulSoup

from src.ingest.models import Article
from src.ingest.sources import DEFAULT_USER_AGENT

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT: float = 4.0
MAX_BODY_CHARS: int = 900

# Common container selectors used by Korean and international news portals
CONTENT_CONTAINER_SELECTORS: list[str] = [
    "article",
    "div.article_view",
    "div#articleBody",
    "div#articleBodyContents",
    "div#newsct_article",
    "div#dic_area",
    "div.article-body",
    "div#article_body",
    "section.article-body",
    "div.news_cnt_detail",
]


class ArticleBodyExtractor:
    """Extracts clean text paragraphs from news article URLs using urllib and BeautifulSoup."""

    def __init__(
        self,
        user_agent: str = DEFAULT_USER_AGENT,
        timeout: float = DEFAULT_TIMEOUT,
        max_chars: int = MAX_BODY_CHARS,
    ) -> None:
        """Initialize the extractor with user agent, network timeout, and character limit.

        Args:
            user_agent: User-Agent header string.
            timeout: Network request timeout in seconds (default: 4.0).
            max_chars: Maximum character limit for extracted body text (default: 900).
        """
        self.user_agent = user_agent
        self.timeout = timeout
        self.max_chars = max_chars

    def extract_text_from_html(self, html: str) -> str:
        """Extract and clean text paragraphs from HTML string.

        Strips scripts, styles, navigation, and boilerplate tags.
        Targets container selectors (<article>, <div class="article_view">, <div id="articleBody">, etc.),
        joins clean paragraphs, and truncates to approximately max_chars.

        Args:
            html: Raw HTML content string.

        Returns:
            Cleaned and truncated body text.
        """
        if not html or not isinstance(html, str):
            return ""

        soup = BeautifulSoup(html, "html.parser")

        # Strip non-content and layout tags
        for tag in soup(
            ["script", "style", "noscript", "header", "footer", "nav", "aside", "form", "iframe"]
        ):
            tag.decompose()

        # Locate candidate content container
        target_element = None
        for selector in CONTENT_CONTAINER_SELECTORS:
            found = soup.select_one(selector)
            if found:
                target_element = found
                break

        paragraphs: list[str] = []
        if target_element:
            p_tags = target_element.find_all("p")
            if p_tags:
                paragraphs = [p.get_text(separator=" ", strip=True) for p in p_tags]
            else:
                paragraphs = [target_element.get_text(separator="\n", strip=True)]
        else:
            # Fallback to all <p> tags in the document
            p_tags = soup.find_all("p")
            if p_tags:
                paragraphs = [p.get_text(separator=" ", strip=True) for p in p_tags]
            elif soup.body:
                paragraphs = [soup.body.get_text(separator="\n", strip=True)]

        # Clean paragraphs: collapse whitespaces, remove empty items
        cleaned_paras: list[str] = []
        for p in paragraphs:
            cleaned = re.sub(r"\s+", " ", p).strip()
            if cleaned:
                cleaned_paras.append(cleaned)

        joined_body = "\n\n".join(cleaned_paras).strip()

        # Truncate to max_chars
        if len(joined_body) > self.max_chars:
            joined_body = joined_body[: self.max_chars].rstrip()

        return joined_body

    def fetch_html(self, url: str) -> str:
        """Fetch raw HTML content from an article URL using urllib.

        Args:
            url: Target web page URL.

        Returns:
            Decoded HTML string.

        Raises:
            urllib.error.URLError, urllib.error.HTTPError, TimeoutError: On request failure.
        """
        parsed_url = urllib.parse.urlparse(url)
        if parsed_url.scheme not in ("http", "https"):
            raise ValueError(f"Unsupported URL scheme for article body extraction: {parsed_url.scheme}")

        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": self.user_agent,
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
            },
        )
        with urllib.request.urlopen(req, timeout=self.timeout) as response:
            content_type = response.headers.get("Content-Type", "")
            charset = "utf-8"
            if "charset=" in content_type.lower():
                charset = content_type.lower().split("charset=")[-1].split(";")[0].strip()
            raw_bytes = response.read()
            try:
                return raw_bytes.decode(charset)
            except Exception:
                return raw_bytes.decode("utf-8", errors="replace")

    def extract_body(self, url: str) -> str:
        """Fetch article HTML from URL and extract cleaned body text.

        Returns empty string if any network error or extraction failure occurs.

        Args:
            url: Article web URL.

        Returns:
            Extracted text string, or empty string on failure.
        """
        if not url or not url.strip():
            return ""
        try:
            html = self.fetch_html(url)
            return self.extract_text_from_html(html)
        except Exception as e:
            logger.debug("Failed to extract body from %s: %s", url, e)
            return ""

    def enrich_article(self, article: Article) -> Article:
        """Enrich a single Article instance with extracted body text.

        Falls back to article.summary if extraction fails, network error occurs,
        or article has no URL.

        Args:
            article: Article instance to enrich.

        Returns:
            The enriched Article instance with `body` set.
        """
        extracted = ""
        if article.url:
            try:
                extracted = self.extract_body(article.url)
            except Exception as e:
                logger.debug("Error enriching article %s: %s", article.id, e)

        if extracted and extracted.strip():
            article.body = extracted.strip()
        else:
            article.body = article.summary or ""
        return article


def enrich_articles_with_body(
    articles: list[Article],
    max_workers: int = 5,
    extractor: ArticleBodyExtractor | None = None,
) -> list[Article]:
    """Enrich a list of Article instances concurrently with clean body text.

    Falls back to article.summary if extraction fails or network error occurs.

    Args:
        articles: List of Article objects to enrich.
        max_workers: Maximum number of concurrent worker threads (default: 5).
        extractor: ArticleBodyExtractor instance or None (creates default).

    Returns:
        Enriched list of Article instances.
    """
    if not articles:
        return []

    ext = extractor or ArticleBodyExtractor()
    effective_workers = min(max_workers, len(articles)) if len(articles) > 0 else 1

    with concurrent.futures.ThreadPoolExecutor(max_workers=effective_workers) as executor:
        enriched = list(executor.map(ext.enrich_article, articles))

    return enriched

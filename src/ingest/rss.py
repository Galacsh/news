"""RSS/Atom feed parsing and normalization engine."""

from __future__ import annotations

import email.utils
import hashlib
import html
import logging
import re
import urllib.error
import urllib.request
from datetime import datetime, timezone
from typing import Any

import feedparser

from src.ingest.models import Article

logger = logging.getLogger(__name__)


class RSSFeedParser:
    """Parser for RSS and Atom news feeds into normalized Article instances."""

    DEFAULT_TIMEOUT: float = 5.0
    DEFAULT_USER_AGENT: str = (
        "Mozilla/5.0 (compatible; KoreaNewsBriefingBot/1.0; "
        "+https://github.com/galacsh/news)"
    )

    @classmethod
    def clean_html(cls, text: str | None) -> str:
        """Sanitize text by stripping HTML tags, removing scripts, and unescaping entities."""
        if not text:
            return ""

        # Remove script and style elements and their contents
        cleaned = re.sub(
            r"<(script|style)[^>]*>.*?</\1>",
            " ",
            str(text),
            flags=re.DOTALL | re.IGNORECASE,
        )
        # Remove HTML comments
        cleaned = re.sub(r"<!--.*?-->", " ", cleaned, flags=re.DOTALL)
        # Convert line breaks and block tags to spaces
        cleaned = re.sub(
            r"<(br|p|div|h[1-6]|li|tr|blockquote)[^>]*>",
            " ",
            cleaned,
            flags=re.IGNORECASE,
        )
        # Strip all other HTML tags
        cleaned = re.sub(r"<[^>]+>", " ", cleaned)
        # Unescape HTML entities
        cleaned = html.unescape(cleaned)

        # Handle double-escaped HTML (e.g. &lt;b&gt; -> <b> -> strip again)
        if "<" in cleaned and ">" in cleaned:
            cleaned = re.sub(r"<[^>]+>", " ", cleaned)
            cleaned = html.unescape(cleaned)

        # Fix spacing before punctuation (e.g. "word ." -> "word.")
        cleaned = re.sub(r"\s+([.,!?:;%])", r"\1", cleaned)

        # Normalize whitespace (replace non-breaking spaces and collapse runs)
        cleaned = cleaned.replace("\xa0", " ")
        cleaned = re.sub(r"\s+", " ", cleaned).strip()
        return cleaned

    @classmethod
    def generate_article_id(cls, canonical_url: str, fallback_title: str = "") -> str:
        """Generate a deterministic SHA-256 hash ID from canonical URL."""
        target = (canonical_url or "").strip()
        if not target:
            target = (fallback_title or "").strip()
        return hashlib.sha256(target.encode("utf-8")).hexdigest()

    @classmethod
    def parse_published_date(cls, entry: Any) -> str:
        """Extract published/updated date as ISO 8601 string, with UTC now fallback."""
        # 1. Prefer feedparser's pre-parsed struct_time
        st = entry.get("published_parsed") or entry.get("updated_parsed")
        if st:
            try:
                dt = datetime(*st[:6], tzinfo=timezone.utc)
                return dt.isoformat()
            except Exception:
                pass

        # 2. Try raw date strings (RFC 822 / ISO 8601)
        for field in ("published", "updated", "pubDate"):
            raw_val = entry.get(field)
            if raw_val and isinstance(raw_val, str):
                try:
                    parsed = email.utils.parsedate_to_datetime(raw_val)
                    if parsed:
                        if parsed.tzinfo is None:
                            parsed = parsed.replace(tzinfo=timezone.utc)
                        return parsed.astimezone(timezone.utc).isoformat()
                except Exception:
                    pass

                try:
                    normalized_iso = raw_val.strip().replace("Z", "+00:00")
                    dt = datetime.fromisoformat(normalized_iso)
                    if dt.tzinfo is None:
                        dt = dt.replace(tzinfo=timezone.utc)
                    return dt.astimezone(timezone.utc).isoformat()
                except Exception:
                    pass

        # 3. Fallback to current UTC timestamp
        return datetime.now(timezone.utc).isoformat()

    @classmethod
    def _decode_xml_bytes(cls, content: bytes) -> str:
        """Safely decode raw XML bytes supporting UTF-8 and Korean legacy encodings."""
        # Check XML declaration for encoding
        header_sample = content[:300]
        match = re.search(
            rb"""<\?xml[^>]+encoding=["']([a-zA-Z0-9_\-]+)["']""",
            header_sample,
            flags=re.IGNORECASE,
        )
        if match:
            declared_enc = match.group(1).decode("ascii", errors="ignore").lower()
            try:
                return content.decode(declared_enc)
            except (LookupError, UnicodeDecodeError):
                pass

        # Try UTF-8
        try:
            return content.decode("utf-8")
        except UnicodeDecodeError:
            pass

        # Fallback to Korean legacy encodings (EUC-KR / CP949)
        for enc in ("cp949", "euc-kr"):
            try:
                return content.decode(enc)
            except (LookupError, UnicodeDecodeError):
                pass

        # Final lossy fallback
        return content.decode("utf-8", errors="replace")

    @classmethod
    def parse_xml(
        cls,
        xml_content: str | bytes,
        category: str = "",
        outlet: str = "",
    ) -> list[Article]:
        """Parse raw XML string or bytes into a list of normalized Article objects."""
        if not xml_content:
            return []

        # Ensure content is string for consistent handling
        if isinstance(xml_content, bytes):
            decoded_xml = cls._decode_xml_bytes(xml_content)
        else:
            decoded_xml = str(xml_content)

        if not decoded_xml.strip():
            return []

        try:
            feed = feedparser.parse(decoded_xml)
        except Exception as exc:
            logger.warning("Unexpected error during feedparser.parse: %s", exc)
            return []

        # If feedparser experienced a syntax or structure error and found no entries
        if getattr(feed, "bozo", False) and not feed.entries:
            logger.warning(
                "Malformed feed content with no entries parsed: %s",
                getattr(feed, "bozo_exception", "Unknown XML error"),
            )
            return []

        # Determine feed-level outlet name if not provided
        feed_outlet = outlet
        if not feed_outlet and getattr(feed, "feed", None):
            feed_outlet = cls.clean_html(feed.feed.get("title", ""))

        articles: list[Article] = []

        for entry in getattr(feed, "entries", []):
            url = entry.get("link", "").strip()
            if not url and entry.get("id"):
                url = str(entry.get("id")).strip()

            clean_title = cls.clean_html(entry.get("title", ""))

            # Summary extraction with fallbacks: summary -> description -> content
            raw_summary = entry.get("summary") or entry.get("description") or ""
            if not raw_summary and entry.get("content"):
                content_list = entry.get("content")
                if isinstance(content_list, list) and content_list:
                    raw_summary = content_list[0].get("value", "")

            clean_summary = cls.clean_html(raw_summary)

            # Skip entries with no URL and no title
            if not url and not clean_title:
                continue

            article_id = cls.generate_article_id(url, fallback_title=clean_title)
            published_at = cls.parse_published_date(entry)

            # Category resolution: parameter -> entry.category -> entry.tags
            entry_category = category
            if not entry_category:
                if entry.get("category"):
                    entry_category = cls.clean_html(entry.get("category"))
                elif entry.get("tags"):
                    tags = entry.get("tags")
                    if isinstance(tags, list) and tags:
                        first_tag = tags[0]
                        if isinstance(first_tag, dict) and first_tag.get("term"):
                            entry_category = cls.clean_html(first_tag.get("term"))

            # Outlet resolution
            entry_outlet = feed_outlet
            if not entry_outlet and entry.get("author"):
                entry_outlet = cls.clean_html(entry.get("author"))

            article = Article(
                id=article_id,
                title=clean_title,
                summary=clean_summary,
                url=url,
                outlet=entry_outlet,
                published_at=published_at,
                category=entry_category,
                raw_data=dict(entry) if isinstance(entry, dict) else None,
            )
            articles.append(article)

        return articles

    @classmethod
    def parse_feed(
        cls,
        url: str,
        category: str = "",
        outlet: str = "",
        timeout: float = DEFAULT_TIMEOUT,
    ) -> list[Article]:
        """Fetch and parse an RSS feed from a remote URL with strict timeout and error handling."""
        if not url or not url.strip():
            logger.warning("Empty URL provided to parse_feed")
            return []

        target_url = url.strip()
        req = urllib.request.Request(
            target_url,
            headers={
                "User-Agent": cls.DEFAULT_USER_AGENT,
                "Accept": "application/rss+xml, application/xml, text/xml, */*",
            },
        )

        try:
            with urllib.request.urlopen(req, timeout=timeout) as response:
                content = response.read()
                return cls.parse_xml(content, category=category, outlet=outlet)
        except urllib.error.HTTPError as exc:
            logger.warning(
                "HTTP error %s fetching feed %s: %s",
                exc.code,
                target_url,
                exc.reason,
            )
            return []
        except urllib.error.URLError as exc:
            logger.warning(
                "URL/Connection error fetching feed %s: %s",
                target_url,
                exc.reason,
            )
            return []
        except (TimeoutError, OSError) as exc:
            logger.warning(
                "Timeout or socket error fetching feed %s: %s",
                target_url,
                exc,
            )
            return []
        except Exception as exc:
            logger.warning(
                "Unexpected failure fetching feed %s: %s",
                target_url,
                exc,
            )
            return []

"""Daum News scraper, model normalization, and CLI runner."""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import logging
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from typing import Any

from bs4 import BeautifulSoup

from src.ingest.models import Article

logger = logging.getLogger(__name__)

DEFAULT_DAUM_URL = "https://news.daum.net"
DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)
KST = timezone(timedelta(hours=9))


class DaumScrapeError(Exception):
    """Exception raised for errors during Daum News scraping."""


def parse_relative_time(relative_time: str | None, now: datetime | None = None) -> str:
    """Convert relative time string (e.g. '5분 전', '1시간 전', '어제') or date string to ISO 8601.

    Falls back to current timestamp if parsing fails or input is empty.
    """
    if now is None:
        now = datetime.now(KST)
    elif now.tzinfo is None:
        now = now.replace(tzinfo=KST)

    if not relative_time or not isinstance(relative_time, str):
        return now.isoformat()

    cleaned = relative_time.strip()
    if not cleaned:
        return now.isoformat()

    # Seconds ago: '5초 전'
    m = re.match(r"^(\d+)\s*초\s*전$", cleaned)
    if m:
        return (now - timedelta(seconds=int(m.group(1)))).isoformat()

    # Minutes ago: '5분 전'
    m = re.match(r"^(\d+)\s*분\s*전$", cleaned)
    if m:
        return (now - timedelta(minutes=int(m.group(1)))).isoformat()

    # Hours ago: '2시간 전'
    m = re.match(r"^(\d+)\s*시간\s*전$", cleaned)
    if m:
        return (now - timedelta(hours=int(m.group(1)))).isoformat()

    # Days ago: '2일 전'
    m = re.match(r"^(\d+)\s*일\s*전$", cleaned)
    if m:
        return (now - timedelta(days=int(m.group(1)))).isoformat()

    # Weeks ago: '1주 전'
    m = re.match(r"^(\d+)\s*주\s*전$", cleaned)
    if m:
        return (now - timedelta(weeks=int(m.group(1)))).isoformat()

    # Months ago: '1달 전' / '1개월 전'
    m = re.match(r"^(\d+)\s*(?:달|개월)\s*전$", cleaned)
    if m:
        return (now - timedelta(days=30 * int(m.group(1)))).isoformat()

    # Years ago: '1년 전'
    m = re.match(r"^(\d+)\s*년\s*전$", cleaned)
    if m:
        return (now - timedelta(days=365 * int(m.group(1)))).isoformat()

    # Yesterday: '어제' or '어제 14:30'
    m = re.match(r"^어제(?:\s+(\d{1,2}):(\d{2}))?$", cleaned)
    if m:
        target_date = now - timedelta(days=1)
        if m.group(1) and m.group(2):
            target_date = target_date.replace(
                hour=int(m.group(1)),
                minute=int(m.group(2)),
                second=0,
                microsecond=0,
            )
        return target_date.isoformat()

    # Day before yesterday: '그저께', '그제'
    if cleaned in ("그저께", "그제"):
        return (now - timedelta(days=2)).isoformat()

    # Just now: '방금', '방금 전'
    if cleaned in ("방금", "방금 전"):
        return now.isoformat()

    # Try ISO 8601 format
    try:
        dt = datetime.fromisoformat(cleaned)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=KST)
        return dt.isoformat()
    except (ValueError, TypeError):
        pass

    # Common date formats (e.g. '2026.10.25.', '2026-10-25')
    for fmt in (
        "%Y.%m.%d. %H:%M:%S",
        "%Y.%m.%d %H:%M:%S",
        "%Y.%m.%d. %H:%M",
        "%Y.%m.%d %H:%M",
        "%Y.%m.%d.",
        "%Y.%m.%d",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M",
        "%Y-%m-%d",
    ):
        try:
            dt = datetime.strptime(cleaned, fmt)
            dt = dt.replace(tzinfo=KST)
            return dt.isoformat()
        except (ValueError, TypeError):
            continue

    return now.isoformat()


class DaumNewsScraper:
    """Scraper and normalizer for Daum News headlines."""

    parse_relative_time = staticmethod(parse_relative_time)

    def __init__(self, user_agent: str = DEFAULT_USER_AGENT) -> None:
        self.user_agent = user_agent

    def fetch_html(self, url: str = DEFAULT_DAUM_URL, timeout: int = 10) -> str:
        """Fetch HTML content from Daum News with a custom User-Agent.

        Raises DaumScrapeError on URLError, HTTPError, TimeoutError, or non-200 status.
        """
        headers = {"User-Agent": self.user_agent}
        req = urllib.request.Request(url, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=timeout) as response:
                status = getattr(response, "status", None) or getattr(response, "code", 200)
                if status != 200:
                    raise DaumScrapeError(f"HTTP request failed with status code {status}")
                content = response.read()
                charset = response.headers.get_content_charset() or "utf-8"
                return content.decode(charset, errors="replace")
        except urllib.error.HTTPError as exc:
            raise DaumScrapeError(f"HTTP error {exc.code}: {exc.reason}") from exc
        except urllib.error.URLError as exc:
            raise DaumScrapeError(f"Network error: {exc.reason}") from exc
        except TimeoutError as exc:
            raise DaumScrapeError(f"Request timed out: {exc}") from exc
        except Exception as exc:
            if isinstance(exc, DaumScrapeError):
                raise
            raise DaumScrapeError(f"Unexpected error fetching Daum HTML: {exc}") from exc

    def parse_headlines(self, html_content: str) -> list[dict[str, Any]]:
        """Parse headline items from Daum home HTML content using BeautifulSoup.

        Matches both item_newsheadline2 and item_newsbasic anchor blocks.
        """
        if not html_content or not isinstance(html_content, str):
            return []

        soup = BeautifulSoup(html_content, "html.parser")
        anchor_blocks = soup.find_all(
            "a",
            class_=lambda c: bool(c and any(cls in c.split() for cls in ("item_newsheadline2", "item_newsheadline", "item_newsbasic"))),
        )

        items: list[dict[str, Any]] = []

        for block in anchor_blocks:
            # 1. URL resolution using urljoin
            raw_url = str(block.get("href") or "").strip()
            resolved_url = urllib.parse.urljoin(DEFAULT_DAUM_URL, raw_url) if raw_url else ""

            # 2. Article ID (numeric string parsed from URL)
            id_match = (
                re.search(r"/v/(\d+)", resolved_url)
                or re.search(r"/v/([a-zA-Z0-9_-]+)", resolved_url)
                or re.search(r"(\d{8,})", resolved_url)
            )
            article_id = id_match.group(1) if id_match else ""

            # 3. Title (.tit_txt with inner text preserved or data-title)
            tit_el = block.select_one(".tit_txt")
            if tit_el:
                title = re.sub(r"\s+", " ", tit_el.get_text(strip=False)).strip()
            else:
                data_title = str(block.get("data-title") or "").strip()
                if data_title:
                    title = html.unescape(urllib.parse.unquote(data_title)).strip()
                    title = re.sub(r"\s+", " ", title)
                else:
                    title = ""

            # 4. Summary (.desc_txt)
            desc_el = block.select_one(".desc_txt")
            if desc_el:
                summary = re.sub(r"\s+", " ", desc_el.get_text(strip=False)).strip()
            else:
                summary = ""

            # 5. Outlet and relative time (.info_txt -> .txt_info)
            info_scope = block.select_one(".info_txt") or block
            spans = [
                re.sub(r"\s+", " ", s.get_text(strip=False)).strip()
                for s in info_scope.select(".txt_info")
            ]
            spans = [s for s in spans if s]

            outlet = spans[0] if len(spans) > 0 else ""
            relative_time = spans[1] if len(spans) > 1 else ""

            # 6. Thumbnail URL (picture source[srcset] or img[src])
            thumbnail_url: str | None = None
            source_el = block.select_one("picture source[srcset]")
            if source_el and source_el.get("srcset"):
                srcset = source_el["srcset"].strip()
                first_cand = srcset.split(",")[0].strip().split()[0]
                thumbnail_url = html.unescape(first_cand)
            else:
                img_el = block.select_one("img[src]")
                if img_el and img_el.get("src"):
                    thumbnail_url = html.unescape(img_el["src"].strip())

            if thumbnail_url:
                thumbnail_url = urllib.parse.urljoin(DEFAULT_DAUM_URL, thumbnail_url)
            else:
                thumbnail_url = None

            items.append({
                "title": title,
                "url": resolved_url,
                "article_id": article_id,
                "summary": summary,
                "outlet": outlet,
                "relative_time": relative_time,
                "thumbnail_url": thumbnail_url,
            })

        return items

    def to_article(self, item: dict[str, Any], now: datetime | None = None) -> Article:
        """Normalize parsed headline dictionary into an Article model."""
        article_id = str(item.get("article_id") or "").strip()
        url = str(item.get("url") or "").strip()

        if not article_id:
            m = (
                re.search(r"/v/(\d+)", url)
                or re.search(r"/v/([a-zA-Z0-9_-]+)", url)
                or re.search(r"(\d{8,})", url)
            )
            if m:
                article_id = m.group(1)
            elif url:
                article_id = hashlib.sha256(url.encode("utf-8")).hexdigest()[:16]
            else:
                article_id = hashlib.sha256(str(item.get("title", "")).encode("utf-8")).hexdigest()[:16]

        if article_id.startswith("daum:"):
            full_id = article_id
        else:
            full_id = f"daum:{article_id}"

        published_at = parse_relative_time(item.get("relative_time"), now=now)

        raw_data = {
            "is_major": True,
            "thumbnail_url": item.get("thumbnail_url"),
            "outlet": item.get("outlet", ""),
        }
        if item.get("relative_time"):
            raw_data["relative_time"] = item.get("relative_time")

        return Article(
            id=full_id,
            title=str(item.get("title", "")),
            summary=str(item.get("summary", "")),
            url=url,
            outlet=str(item.get("outlet", "")),
            published_at=published_at,
            category=str(item.get("category") or "주요뉴스"),
            category_id=item.get("category_id"),
            raw_data=raw_data,
        )

    def get_major_news(self, url: str = DEFAULT_DAUM_URL, limit: int = 20) -> list[Article]:
        """Fetch, parse, deduplicate, and convert major news headlines into Article models."""
        html_content = self.fetch_html(url=url)
        items = self.parse_headlines(html_content)

        seen_keys: set[str] = set()
        articles: list[Article] = []

        for item in items:
            article = self.to_article(item)
            dedup_key = article.id if article.id != "daum:" else article.url
            if not dedup_key or dedup_key in seen_keys:
                continue
            seen_keys.add(dedup_key)
            articles.append(article)
            if len(articles) >= limit:
                break

        return articles

    fetch_major_news = get_major_news


def format_text_output(articles: list[Article]) -> str:
    """Format article list into CLI text representation."""
    lines: list[str] = []
    for idx, article in enumerate(articles, start=1):
        lines.append(f"[{idx}] {article.title} ({article.outlet}) - {article.url}")
        if article.summary:
            lines.append(f"    {article.summary}")
    return "\n".join(lines)


def format_json_output(articles: list[Article]) -> str:
    """Format article list into JSON string."""
    data = [a.to_dict() for a in articles]
    return json.dumps(data, ensure_ascii=False, indent=2)


def main(args: list[str] | None = None) -> int:
    """CLI runner for Daum News Scraper."""
    parser = argparse.ArgumentParser(description="Daum News Major Headlines Scraper CLI")
    parser.add_argument(
        "--format",
        choices=["text", "json"],
        default="text",
        help="Output format: text (default) or json",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=10,
        help="Max articles to fetch (default: 10)",
    )
    parser.add_argument(
        "--url",
        default=DEFAULT_DAUM_URL,
        help=f"Target URL (default: {DEFAULT_DAUM_URL})",
    )
    parsed_args = parser.parse_args(args)

    scraper = DaumNewsScraper()
    try:
        articles = scraper.get_major_news(url=parsed_args.url, limit=parsed_args.limit)
    except DaumScrapeError as exc:
        print(f"Error scraping Daum News: {exc}", file=sys.stderr)
        return 1

    if parsed_args.format == "json":
        print(format_json_output(articles))
    else:
        output = format_text_output(articles)
        if output:
            print(output)
    return 0


if __name__ == "__main__":
    sys.exit(main())

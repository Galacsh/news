"""Automated RSS feed health checker utility.

Validates candidate feeds against HTTP availability, response latency,
XML validity, item parsing count, and article freshness/recency.
"""

from __future__ import annotations

import argparse
import concurrent.futures
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import json
import logging
import os
import socket
import sys
import time
from typing import Any
import urllib.error
import urllib.request

from src.ingest.models import Article, FeedSource
from src.ingest.rss import RSSFeedParser

logger = logging.getLogger(__name__)


@dataclass
class FeedHealthResult:
    """Structured health check result for an RSS/Atom candidate feed."""

    url: str
    name: str = ""
    outlet: str = ""
    category: str = ""
    category_id: int | None = None
    status: str = "healthy"  # "healthy" | "unhealthy" | "warning"
    http_code: int | None = None
    latency_ms: float = 0.0
    item_count: int = 0
    latest_published_at: str | None = None
    error: str | None = None
    is_recommended: bool = False

    def to_dict(self) -> dict[str, Any]:
        """Convert the FeedHealthResult instance to a standard dictionary."""
        return asdict(self)


class FeedHealthChecker:
    """Automated RSS/Atom feed health and freshness checker."""

    LATENCY_WARNING_THRESHOLD_MS: float = 5000.0

    def __init__(
        self,
        timeout: float = 5.0,
        user_agent: str | None = None,
        max_age_days: int = 30,
    ) -> None:
        self.timeout = float(timeout)
        self.user_agent = user_agent or RSSFeedParser.DEFAULT_USER_AGENT
        self.max_age_days = int(max_age_days)

    def _normalize_feed_input(
        self,
        feed: dict[str, Any] | FeedSource | str,
    ) -> tuple[str, str, str, str, int | None]:
        """Extract (url, name, outlet, category, category_id) from diverse feed input shapes."""
        if isinstance(feed, str):
            url = feed.strip()
            return url, "", "", "", None

        if isinstance(feed, FeedSource):
            url = (feed.url or "").strip()
            name = feed.name or ""
            outlet = getattr(feed, "outlet", "") or (name.split(" - ")[0].strip() if " - " in name else "")
            return url, name, outlet, feed.category or "", feed.category_id

        if isinstance(feed, dict):
            url = str(feed.get("url") or "").strip()
            name = str(feed.get("name") or feed.get("title") or "")
            outlet = str(feed.get("outlet") or (name.split(" - ")[0].strip() if " - " in name else ""))
            category = str(feed.get("category") or "")
            category_id = feed.get("category_id") if "category_id" in feed else feed.get("categoryId")
            return url, name, outlet, category, category_id

        return str(feed).strip(), "", "", "", None

    def _is_article_date_explicit(self, art: Article) -> bool:
        """Check whether an article had an explicit publication date in feed metadata."""
        if not art.published_at:
            return False
        if art.raw_data is not None:
            return any(
                k in art.raw_data
                for k in ("published_parsed", "updated_parsed", "published", "updated", "pubDate")
            )
        return True

    def check_feed(self, feed: dict[str, Any] | FeedSource | str) -> FeedHealthResult:
        """Check a single feed for HTTP responsiveness, latency, XML validity, and freshness."""
        url, name, outlet, category, category_id = self._normalize_feed_input(feed)

        if not url:
            return FeedHealthResult(
                url=url,
                name=name,
                outlet=outlet,
                category=category,
                category_id=category_id,
                status="unhealthy",
                error="Missing or empty feed URL",
                is_recommended=False,
            )

        start_time = time.perf_counter()
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": self.user_agent,
                "Accept": "application/rss+xml, application/xml, text/xml, */*",
            },
        )

        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                raw_bytes = resp.read()
                http_code = getattr(resp, "status", None) or resp.getcode() or 200
        except urllib.error.HTTPError as exc:
            latency_ms = round((time.perf_counter() - start_time) * 1000, 2)
            return FeedHealthResult(
                url=url,
                name=name,
                outlet=outlet,
                category=category,
                category_id=category_id,
                status="unhealthy",
                http_code=exc.code,
                latency_ms=latency_ms,
                item_count=0,
                error=f"HTTP {exc.code}: {exc.reason}",
                is_recommended=False,
            )
        except urllib.error.URLError as exc:
            latency_ms = round((time.perf_counter() - start_time) * 1000, 2)
            return FeedHealthResult(
                url=url,
                name=name,
                outlet=outlet,
                category=category,
                category_id=category_id,
                status="unhealthy",
                http_code=None,
                latency_ms=latency_ms,
                item_count=0,
                error=f"URLError: {exc.reason}",
                is_recommended=False,
            )
        except (TimeoutError, socket.timeout) as exc:
            latency_ms = round((time.perf_counter() - start_time) * 1000, 2)
            return FeedHealthResult(
                url=url,
                name=name,
                outlet=outlet,
                category=category,
                category_id=category_id,
                status="unhealthy",
                http_code=None,
                latency_ms=latency_ms,
                item_count=0,
                error=f"Timeout: {exc}",
                is_recommended=False,
            )
        except Exception as exc:
            latency_ms = round((time.perf_counter() - start_time) * 1000, 2)
            return FeedHealthResult(
                url=url,
                name=name,
                outlet=outlet,
                category=category,
                category_id=category_id,
                status="unhealthy",
                http_code=None,
                latency_ms=latency_ms,
                item_count=0,
                error=f"Request failed: {exc}",
                is_recommended=False,
            )

        latency_ms = round((time.perf_counter() - start_time) * 1000, 2)

        if http_code != 200:
            return FeedHealthResult(
                url=url,
                name=name,
                outlet=outlet,
                category=category,
                category_id=category_id,
                status="unhealthy",
                http_code=http_code,
                latency_ms=latency_ms,
                item_count=0,
                error=f"Non-200 HTTP code: {http_code}",
                is_recommended=False,
            )

        try:
            articles = RSSFeedParser.parse_xml(raw_bytes, category=category, outlet=outlet)
        except Exception as exc:
            return FeedHealthResult(
                url=url,
                name=name,
                outlet=outlet,
                category=category,
                category_id=category_id,
                status="unhealthy",
                http_code=http_code,
                latency_ms=latency_ms,
                item_count=0,
                error=f"XML parsing failed: {exc}",
                is_recommended=False,
            )

        if not articles:
            return FeedHealthResult(
                url=url,
                name=name,
                outlet=outlet,
                category=category,
                category_id=category_id,
                status="unhealthy",
                http_code=http_code,
                latency_ms=latency_ms,
                item_count=0,
                error="Empty feed items or malformed XML",
                is_recommended=False,
            )

        item_count = len(articles)
        if not outlet and articles[0].outlet:
            outlet = articles[0].outlet
        if not name:
            name = outlet or "Feed"

        valid_dates: list[tuple[datetime, str]] = []
        for art in articles:
            if self._is_article_date_explicit(art) and art.published_at:
                try:
                    dt = datetime.fromisoformat(art.published_at)
                    if dt.tzinfo is None:
                        dt = dt.replace(tzinfo=timezone.utc)
                    else:
                        dt = dt.astimezone(timezone.utc)
                    valid_dates.append((dt, art.published_at))
                except Exception:
                    pass

        latest_published_at: str | None = None
        status = "healthy"
        error: str | None = None
        is_recommended = True

        now = datetime.now(timezone.utc)

        if valid_dates:
            valid_dates.sort(key=lambda x: x[0], reverse=True)
            latest_dt, latest_published_at = valid_dates[0]
            age_days = (now - latest_dt).total_seconds() / 86400.0

            if age_days > self.max_age_days * 3:
                status = "unhealthy"
                error = (
                    f"Severely stale feed: latest article is {int(age_days)} days old "
                    f"(limit: {self.max_age_days * 3}d)"
                )
                is_recommended = False
            elif age_days > self.max_age_days:
                status = "warning"
                error = (
                    f"Stale feed: latest article is {int(age_days)} days old "
                    f"(limit: {self.max_age_days}d)"
                )
                is_recommended = False
        else:
            latest_published_at = articles[0].published_at if articles else None
            status = "warning"
            error = "Feed articles lack explicit publication dates"
            is_recommended = False

        if latency_ms > self.LATENCY_WARNING_THRESHOLD_MS and status == "healthy":
            status = "warning"
            error = f"High latency: {latency_ms:.0f}ms (> {self.LATENCY_WARNING_THRESHOLD_MS:.0f}ms)"
            is_recommended = False

        return FeedHealthResult(
            url=url,
            name=name,
            outlet=outlet,
            category=category,
            category_id=category_id,
            status=status,
            http_code=http_code,
            latency_ms=latency_ms,
            item_count=item_count,
            latest_published_at=latest_published_at,
            error=error,
            is_recommended=is_recommended,
        )

    def check_feed_catalog(
        self,
        feeds: list[dict[str, Any] | FeedSource | str],
        max_workers: int = 10,
    ) -> list[FeedHealthResult]:
        """Check multiple candidate feeds concurrently using ThreadPoolExecutor."""
        if not feeds:
            return []

        workers = max(1, min(int(max_workers), len(feeds)))
        if workers == 1:
            return [self.check_feed(f) for f in feeds]

        with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as executor:
            return list(executor.map(self.check_feed, feeds))

    @classmethod
    def recommend_feeds(
        cls,
        results: list[FeedHealthResult],
        category: str | None = None,
        min_items: int = 1,
    ) -> list[FeedHealthResult]:
        """Filter and rank healthy feeds matching criteria."""
        candidates: list[FeedHealthResult] = []
        for r in results:
            if r.status != "healthy":
                continue
            if r.item_count < min_items:
                continue
            if category:
                cat_lower = category.strip().lower()
                r_cat_lower = (r.category or "").strip().lower()
                r_name_lower = (r.name or "").strip().lower()
                r_outlet_lower = (r.outlet or "").strip().lower()
                if (
                    cat_lower not in r_cat_lower
                    and cat_lower not in r_name_lower
                    and cat_lower not in r_outlet_lower
                ):
                    continue
            candidates.append(r)

        return sorted(candidates, key=lambda r: (-r.item_count, r.latency_ms))


def parse_arguments(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse CLI arguments for feed health checking."""
    parser = argparse.ArgumentParser(
        description="Automated RSS feed health checker utility",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--input",
        "-i",
        type=str,
        default="rss-unverified.json",
        help="Path to input candidate feeds JSON file",
    )
    parser.add_argument(
        "--output",
        "-o",
        type=str,
        default=None,
        help="Path to output JSON file to save results or recommendations",
    )
    parser.add_argument(
        "--limit",
        "-l",
        type=int,
        default=None,
        help="Maximum number of feeds to check",
    )
    parser.add_argument(
        "--category",
        "-c",
        type=str,
        default=None,
        help="Filter candidate feeds by category keyword",
    )
    parser.add_argument(
        "--timeout",
        "-t",
        type=float,
        default=5.0,
        help="HTTP request timeout in seconds",
    )
    parser.add_argument(
        "--max-workers",
        "-w",
        type=int,
        default=10,
        help="Maximum concurrent worker threads",
    )
    parser.add_argument(
        "--max-age-days",
        type=int,
        default=30,
        help="Maximum age of latest article in days before marking stale",
    )
    parser.add_argument(
        "--recommend-only",
        action="store_true",
        default=False,
        help="Output only recommended healthy feeds",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """CLI entrypoint for batch scanning feeds from JSON and reporting health results."""
    args = parse_arguments(argv)

    input_path = args.input
    if not os.path.exists(input_path):
        logger.error("Input file not found: %s", input_path)
        return 1

    try:
        with open(input_path, "r", encoding="utf-8") as f:
            raw_data = json.load(f)
    except Exception as exc:
        logger.error("Failed to read/parse input JSON %s: %s", input_path, exc)
        return 1

    if isinstance(raw_data, list):
        feed_items = raw_data
    elif isinstance(raw_data, dict):
        feed_items = raw_data.get("feeds", [])
    else:
        logger.error(
            "Unsupported JSON format in %s: expected list or dict with 'feeds'",
            input_path,
        )
        return 1

    if args.category:
        cat_lower = args.category.strip().lower()

        def _matches(item: Any) -> bool:
            if isinstance(item, str):
                return cat_lower in item.lower()
            if isinstance(item, FeedSource):
                return cat_lower in item.category.lower() or cat_lower in item.name.lower()
            if isinstance(item, dict):
                return (
                    cat_lower in str(item.get("category", "")).lower()
                    or cat_lower in str(item.get("name", "")).lower()
                    or cat_lower in str(item.get("title", "")).lower()
                    or cat_lower in str(item.get("outlet", "")).lower()
                )
            return False

        feed_items = [item for item in feed_items if _matches(item)]

    if args.limit and args.limit > 0:
        feed_items = feed_items[: args.limit]

    checker = FeedHealthChecker(
        timeout=args.timeout,
        max_age_days=args.max_age_days,
    )

    results = checker.check_feed_catalog(feed_items, max_workers=args.max_workers)

    if args.recommend_only:
        selected_results = checker.recommend_feeds(results, category=args.category)
    else:
        selected_results = results

    healthy_count = sum(1 for r in results if r.status == "healthy")
    warning_count = sum(1 for r in results if r.status == "warning")
    unhealthy_count = sum(1 for r in results if r.status == "unhealthy")
    rec_count = sum(1 for r in results if r.is_recommended)

    logger.info(
        "Feed Health Check Complete: total=%d, healthy=%d, warning=%d, unhealthy=%d, recommended=%d",
        len(results),
        healthy_count,
        warning_count,
        unhealthy_count,
        rec_count,
    )

    if args.output:
        try:
            output_dir = os.path.dirname(args.output)
            if output_dir:
                os.makedirs(output_dir, exist_ok=True)
            with open(args.output, "w", encoding="utf-8") as f:
                json.dump(
                    [r.to_dict() for r in selected_results],
                    f,
                    ensure_ascii=False,
                    indent=2,
                )
            logger.info("Saved results to %s", args.output)
        except Exception as exc:
            logger.error("Failed to write output to %s: %s", args.output, exc)
            return 1

    return 0


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    sys.exit(main())

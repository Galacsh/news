"""End-to-end orchestration pipeline for Daily Korea News Briefing."""

from __future__ import annotations

import argparse
import concurrent.futures
from datetime import datetime, time, timezone
import json
import logging
import os
from pathlib import Path
import sys
from typing import Any

from src.ingest.filter import ArticleFilterPipeline
from src.ingest.models import Article, FeedSource
from src.ingest.rss import RSSFeedParser
from src.ingest.sources import DEFAULT_FEEDS_PATH, load_feed_sources
from src.llm.client import GeminiClient
from src.llm.summarizer import NewsSummarizer

logger = logging.getLogger(__name__)


def load_env_files(root: Path | str = ".") -> None:
    """Load environment variables from .env.local first, falling back to .env.

    Keys present in os.environ are preserved and never overwritten.
    Keys in .env.local take priority over .env.
    """
    root_path = Path(root)

    def _parse_and_inject(env_path: Path) -> None:
        if not env_path.is_file():
            return
        try:
            with open(env_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#"):
                        continue
                    if line.startswith("export "):
                        line = line[len("export ") :].strip()
                    if "=" not in line:
                        continue
                    key, val = line.split("=", 1)
                    key = key.strip()
                    val = val.strip()
                    if len(val) >= 2 and (
                        (val[0] == '"' and val[-1] == '"')
                        or (val[0] == "'" and val[-1] == "'")
                    ):
                        val = val[1:-1]
                    if key and key not in os.environ:
                        os.environ[key] = val
        except Exception as exc:
            logger.warning("Error reading environment file %s: %s", env_path, exc)

    _parse_and_inject(root_path / ".env.local")
    _parse_and_inject(root_path / ".env")


def parse_pipeline_date(date_val: str | datetime | None) -> tuple[datetime, str, str]:
    """Parse date argument into (reference_datetime, date_str, briefing_date_iso).

    Returns:
        reference_datetime: timezone-aware UTC datetime for recency filtering.
        date_str: 'YYYY-MM-DD' formatted string for archive filename.
        briefing_date_iso: ISO 8601 string for briefingDate in JSON.
    """
    now = datetime.now(timezone.utc)
    if date_val is None:
        return now, now.strftime("%Y-%m-%d"), now.isoformat()

    if isinstance(date_val, datetime):
        dt = date_val if date_val.tzinfo is not None else date_val.replace(tzinfo=timezone.utc)
        dt = dt.astimezone(timezone.utc)
        return dt, dt.strftime("%Y-%m-%d"), dt.isoformat()

    s = str(date_val).strip()
    # Attempt YYYY-MM-DD parse first (so today defaults to current time, and past dates default to end-of-day)
    if len(s) == 10 and s.count("-") == 2:
        try:
            parsed_d = datetime.strptime(s, "%Y-%m-%d").date()
            date_str = parsed_d.strftime("%Y-%m-%d")
            if date_str == now.strftime("%Y-%m-%d"):
                ref_dt = now
                iso_str = now.isoformat()
            else:
                ref_dt = datetime.combine(parsed_d, time(23, 59, 59), tzinfo=timezone.utc)
                iso_str = f"{date_str}T23:59:59+00:00"
            return ref_dt, date_str, iso_str
        except ValueError:
            pass

    # Attempt ISO 8601 parse
    try:
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        else:
            dt = dt.astimezone(timezone.utc)
        return dt, dt.strftime("%Y-%m-%d"), dt.isoformat()
    except ValueError:
        pass

    return now, now.strftime("%Y-%m-%d"), s


class DailyBriefingPipeline:
    """Orchestrates news feed ingestion, filtering, AI synthesis, and static storage."""

    def __init__(
        self,
        feeds_path: str | Path = DEFAULT_FEEDS_PATH,
        output_dir: str | Path = "data",
        dry_run: bool = False,
        date: str | datetime | None = None,
        timeout: float = 10.0,
        max_workers: int = 5,
        env_root: str | Path = ".",
        client: GeminiClient | None = None,
        summarizer: NewsSummarizer | None = None,
    ) -> None:
        """Initialize the DailyBriefingPipeline.

        Args:
            feeds_path: Path to the feeds configuration JSON.
            output_dir: Directory where dynamic latest.json and archive files are written.
            dry_run: If True, operates in mock LLM mode without external API calls.
            date: Target date for the briefing (YYYY-MM-DD or ISO 8601 string or datetime).
            timeout: Network timeout in seconds for fetching individual RSS feeds.
            max_workers: Maximum concurrent worker threads for RSS ingestion.
            env_root: Directory containing .env and .env.local.
            client: Optional pre-configured GeminiClient instance.
            summarizer: Optional pre-configured NewsSummarizer instance.
        """
        load_env_files(env_root)

        self.feeds_path = Path(feeds_path)
        self.output_dir = Path(output_dir)
        self.dry_run = dry_run
        self.timeout = timeout
        self.max_workers = max(1, max_workers)

        self.ref_datetime, self.date_str, self.briefing_date = parse_pipeline_date(date)

        if summarizer is not None:
            self.summarizer = summarizer
        else:
            if client is None:
                client = GeminiClient(dry_run=self.dry_run, mock_mode=self.dry_run)
            self.summarizer = NewsSummarizer(client=client)

    def load_feeds(self) -> list[FeedSource]:
        """Load verified active feed sources from configuration."""
        sources = load_feed_sources(self.feeds_path)
        active_feeds = [f for f in sources if f.is_active]
        logger.info(
            "Loaded %d active feeds out of %d total from %s",
            len(active_feeds),
            len(sources),
            self.feeds_path,
        )
        return active_feeds

    def _fetch_single_feed(self, feed: FeedSource) -> list[Article]:
        """Safely fetch and parse articles for a single feed source."""
        try:
            articles = RSSFeedParser.parse_feed(
                url=feed.url,
                category=feed.category,
                outlet=feed.name,
                timeout=self.timeout,
            )
            for art in articles:
                if art.category_id is None and feed.category_id is not None:
                    art.category_id = feed.category_id
                if not art.category and feed.category:
                    art.category = feed.category
            return articles
        except Exception as exc:
            logger.warning("Failed to fetch feed '%s' (%s): %s", feed.name, feed.url, exc)
            return []

    def fetch_candidate_articles(self, feeds: list[FeedSource]) -> list[Article]:
        """Fetch candidate articles across all active feeds with concurrency and timeout safety."""
        if not feeds:
            logger.warning("No active feeds available to fetch.")
            return []

        articles: list[Article] = []
        workers = min(len(feeds), self.max_workers)

        if workers <= 1:
            for feed in feeds:
                articles.extend(self._fetch_single_feed(feed))
        else:
            with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as executor:
                futures = {executor.submit(self._fetch_single_feed, feed): feed for feed in feeds}
                for future in concurrent.futures.as_completed(futures):
                    feed = futures[future]
                    try:
                        feed_articles = future.result()
                        articles.extend(feed_articles)
                    except Exception as exc:
                        logger.warning("Error fetching articles from feed %s: %s", feed.name, exc)

        logger.info("Ingested %d candidate articles across %d feeds", len(articles), len(feeds))
        return articles

    def filter_articles(self, articles: list[Article]) -> list[Article]:
        """Process candidate articles through deduplication, recency, and category quota filter."""
        if not articles:
            return []

        filter_pipeline = ArticleFilterPipeline(
            max_hours=24.0,
            max_per_category=5,
            reference_time=self.ref_datetime,
        )
        grouped = filter_pipeline.process(articles)
        retained: list[Article] = []
        for cat_name, arts in grouped.items():
            retained.extend(arts)

        logger.info(
            "Filtered %d candidate articles down to %d retained articles",
            len(articles),
            len(retained),
        )
        return retained

    def summarize(self, articles: list[Article]) -> dict[str, Any]:
        """Synthesize retained articles into structured daily briefing."""
        try:
            briefing = self.summarizer.summarize_articles(
                articles=articles,
                briefing_date=self.briefing_date,
            )
        except Exception as exc:
            logger.warning("Summarization encountered error (%s). Generating fallback.", exc)
            grouped = self.summarizer.group_articles_by_category(articles)
            briefing = self.summarizer.extract_fallback_briefing(
                grouped_articles=grouped,
                briefing_date=self.briefing_date,
            )

        # Enforce sequential integer IDs (1..3 for top headlines, 4..N for articles)
        headlines = briefing.get("topHeadlines", [])
        for idx, h in enumerate(headlines, start=1):
            h["id"] = idx

        items = briefing.get("articles", [])
        for idx, item in enumerate(items, start=len(headlines) + 1):
            item["id"] = idx

        if "briefingDate" not in briefing or not briefing["briefingDate"]:
            briefing["briefingDate"] = self.briefing_date

        return briefing

    def write_outputs(self, briefing: dict[str, Any]) -> tuple[Path, Path]:
        """Write dynamic daily briefing to latest.json and historical archive."""
        output_path = self.output_dir
        output_path.mkdir(parents=True, exist_ok=True)

        archive_dir = output_path / "archive"
        archive_dir.mkdir(parents=True, exist_ok=True)

        latest_path = output_path / "latest.json"
        archive_path = archive_dir / f"{self.date_str}.json"

        content = json.dumps(briefing, ensure_ascii=False, indent=2) + "\n"

        with open(latest_path, "w", encoding="utf-8") as f:
            f.write(content)

        with open(archive_path, "w", encoding="utf-8") as f:
            f.write(content)

        logger.info("Saved latest briefing to %s and archive to %s", latest_path, archive_path)
        return latest_path, archive_path

    def run(self) -> dict[str, Any]:
        """Execute the end-to-end news briefing pipeline."""
        logger.info("Starting Daily Korea News Briefing pipeline (dry_run=%s)", self.dry_run)
        feeds = self.load_feeds()
        candidates = self.fetch_candidate_articles(feeds)
        retained = self.filter_articles(candidates)
        briefing = self.summarize(retained)
        self.write_outputs(briefing)
        logger.info("Pipeline completed successfully for date %s", self.date_str)
        return briefing


def run_pipeline(
    feeds_path: str | Path = DEFAULT_FEEDS_PATH,
    output_dir: str | Path = "data",
    dry_run: bool = False,
    date: str | datetime | None = None,
    timeout: float = 10.0,
    max_workers: int = 5,
    env_root: str | Path = ".",
    client: GeminiClient | None = None,
    summarizer: NewsSummarizer | None = None,
) -> dict[str, Any]:
    """Execute end-to-end news briefing pipeline with provided parameters."""
    pipeline = DailyBriefingPipeline(
        feeds_path=feeds_path,
        output_dir=output_dir,
        dry_run=dry_run,
        date=date,
        timeout=timeout,
        max_workers=max_workers,
        env_root=env_root,
        client=client,
        summarizer=summarizer,
    )
    return pipeline.run()


def build_parser() -> argparse.ArgumentParser:
    """Build command-line argument parser for pipeline execution."""
    parser = argparse.ArgumentParser(
        description="Daily Korea News Briefing - Static Orchestration Pipeline"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=False,
        help="Run in mock LLM mode without external API calls",
    )
    parser.add_argument(
        "--feeds-path",
        type=str,
        default=str(DEFAULT_FEEDS_PATH),
        help=f"Path to feeds JSON catalog (default: {DEFAULT_FEEDS_PATH})",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default="data",
        help="Directory where latest.json and archive JSON files are written (default: data)",
    )
    parser.add_argument(
        "--date",
        type=str,
        default=None,
        help="Target date for briefing in YYYY-MM-DD or ISO 8601 format",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=10.0,
        help="Network timeout in seconds per feed fetch (default: 10.0)",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """Main CLI entrypoint for Daily Korea News Briefing pipeline."""
    parser = build_parser()
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    try:
        run_pipeline(
            feeds_path=args.feeds_path,
            output_dir=args.output_dir,
            dry_run=args.dry_run,
            date=args.date,
            timeout=args.timeout,
        )
        return 0
    except Exception as exc:
        logger.error("Pipeline failed: %s", exc, exc_info=True)
        return 1


if __name__ == "__main__":
    sys.exit(main())

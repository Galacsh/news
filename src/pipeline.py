"""End-to-end orchestration pipeline for Daily Korea News Briefing."""

from __future__ import annotations

import argparse
import concurrent.futures
from datetime import datetime, time as dt_time, timezone
import json
import logging
import os
from pathlib import Path
import re
import sys
import threading
import time
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


def generate_archive_manifest(archive_dir: Path | str) -> dict[str, Any]:
    """Scan and index all valid briefing JSON files in archive_dir into manifest.json.

    Scans both timestamped (YYYY-MM-DD_HHMMSS.json) and legacy (YYYY-MM-DD.json) files,
    ignoring manifest.json, directories, and non-JSON files. Extracts metadata for each run
    and sorts entries in reverse chronological order (newest first).

    Args:
        archive_dir: Directory containing historical briefing JSON files.

    Returns:
        The generated manifest dictionary containing metadata and reverse-chronological archive entries.
    """
    archive_path = Path(archive_dir)
    archive_path.mkdir(parents=True, exist_ok=True)

    filename_pattern = re.compile(r"^(\d{4}-\d{2}-\d{2})(?:_(\d{2})(\d{2})(\d{2}))?\.json$")
    entries: list[dict[str, Any]] = []

    for file_path in archive_path.iterdir():
        if not file_path.is_file():
            continue
        if file_path.name == "manifest.json" or not file_path.name.endswith(".json"):
            continue

        match = filename_pattern.match(file_path.name)
        if not match:
            continue

        file_date, hh, mm, ss = match.groups()

        try:
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception as exc:
            logger.warning("Failed to parse archive JSON file %s: %s", file_path.name, exc)
            continue

        if not isinstance(data, dict):
            logger.warning("Skipping non-dict archive JSON %s", file_path.name)
            continue

        if not any(k in data for k in ("briefingDate", "topHeadlines", "articles")):
            logger.warning("Skipping non-briefing JSON file %s", file_path.name)
            continue

        briefing_date = str(data.get("briefingDate") or "")

        if hh is not None:
            time_str = f"{hh}:{mm}:{ss}"
        else:
            time_str = ""
            if briefing_date and ("T" in briefing_date or " " in briefing_date):
                try:
                    b_dt = datetime.fromisoformat(briefing_date.replace("Z", "+00:00"))
                    time_str = b_dt.strftime("%H:%M:%S")
                except Exception:
                    time_str = ""

        top_headlines = data.get("topHeadlines")
        if not isinstance(top_headlines, list):
            top_headlines = []

        articles = data.get("articles")
        if not isinstance(articles, list):
            articles = []

        total_articles = len(top_headlines) + len(articles)

        entries.append({
            "filename": file_path.name,
            "date": file_date,
            "time": time_str,
            "briefingDate": briefing_date,
            "topHeadlines": top_headlines,
            "totalArticles": total_articles,
        })

    entries.sort(
        key=lambda e: (
            e.get("date") or "",
            e.get("time") or "",
            e.get("briefingDate") or "",
            e.get("filename") or "",
        ),
        reverse=True,
    )

    manifest = {
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "totalRuns": len(entries),
        "archives": entries,
    }

    manifest_file = archive_path / "manifest.json"
    manifest_content = json.dumps(manifest, ensure_ascii=False, indent=2) + "\n"
    with open(manifest_file, "w", encoding="utf-8") as f:
        f.write(manifest_content)

    logger.info("Generated archive manifest at %s with %d entries", manifest_file, len(entries))
    return manifest


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

        self.feeds_attempted: int = 0
        self.feeds_failed: int = 0
        self.feed_status: list[dict[str, Any]] = []
        self.raw_articles_count: int = 0
        self.filtered_count: int = 0
        self.category_breakdown: dict[str, int] = {}
        self.gemini_latency_ms: float = 0.0
        self.gemini_fallback_used: bool = False
        self.pipeline_start_time: float = 0.0
        self._status_lock = threading.Lock()

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
        t0 = time.perf_counter()
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
            latency_ms = round((time.perf_counter() - t0) * 1000, 2)
            entry: dict[str, Any] = {
                "outlet": feed.name,
                "url": feed.url,
                "category": feed.category,
                "status": "success",
                "articles_count": len(articles),
                "latency_ms": latency_ms,
                "error": None,
            }
            with self._status_lock:
                self.feed_status.append(entry)
            return articles
        except Exception as exc:
            latency_ms = round((time.perf_counter() - t0) * 1000, 2)
            logger.warning("Failed to fetch feed '%s' (%s): %s", feed.name, feed.url, exc)
            entry = {
                "outlet": feed.name,
                "url": feed.url,
                "category": feed.category,
                "status": "failed",
                "articles_count": 0,
                "latency_ms": latency_ms,
                "error": str(exc),
            }
            with self._status_lock:
                self.feed_status.append(entry)
            return []

    def fetch_candidate_articles(self, feeds: list[FeedSource]) -> list[Article]:
        """Fetch candidate articles across all active feeds with concurrency and timeout safety."""
        self.feeds_attempted = len(feeds)
        self.feed_status = []
        if not feeds:
            self.feeds_failed = 0
            self.raw_articles_count = 0
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

        self.feeds_failed = sum(1 for s in self.feed_status if s.get("status") == "failed")
        self.raw_articles_count = len(articles)

        logger.info("Ingested %d candidate articles across %d feeds", len(articles), len(feeds))
        return articles

    def filter_articles(self, articles: list[Article]) -> list[Article]:
        """Process candidate articles through deduplication, recency, and category quota filter."""
        if not articles:
            self.filtered_count = 0
            self.category_breakdown = {}
            return []

        filter_pipeline = ArticleFilterPipeline(
            max_hours=24.0,
            max_per_category=5,
            reference_time=self.ref_datetime,
            min_per_category=2,
            adaptive_lookback=True,
        )
        grouped = filter_pipeline.process(articles)
        retained: list[Article] = []
        for cat_name, arts in grouped.items():
            retained.extend(arts)

        self.filtered_count = len(retained)
        category_breakdown: dict[str, int] = {}
        for art in retained:
            cat = art.category or "기타"
            category_breakdown[cat] = category_breakdown.get(cat, 0) + 1
        self.category_breakdown = category_breakdown

        logger.info(
            "Filtered %d candidate articles down to %d retained articles",
            len(articles),
            len(retained),
        )
        return retained

    def summarize(self, articles: list[Article]) -> dict[str, Any]:
        """Synthesize retained articles into structured daily briefing."""
        t0 = time.perf_counter()
        llm_failed = False
        client = getattr(self.summarizer, "client", None) if self.summarizer else None
        if client is None:
            self.gemini_fallback_used = True

        orig_generate = None
        if client is not None and hasattr(client, "generate_json"):
            orig_generate = client.generate_json

            def tracked_generate(*args: Any, **kwargs: Any) -> Any:
                nonlocal llm_failed
                try:
                    return orig_generate(*args, **kwargs)
                except Exception:
                    llm_failed = True
                    raise

            client.generate_json = tracked_generate

        try:
            if not self.summarizer:
                raise RuntimeError("No summarizer configured")
            briefing = self.summarizer.summarize_articles(
                articles=articles,
                briefing_date=self.briefing_date,
            )
            if (
                llm_failed
                or getattr(self.summarizer, "fallback", False)
                or getattr(self.summarizer, "fallback_used", False)
            ):
                self.gemini_fallback_used = True
        except Exception as exc:
            logger.warning("Summarization encountered error (%s). Generating fallback.", exc)
            self.gemini_fallback_used = True
            if self.summarizer:
                grouped = self.summarizer.group_articles_by_category(articles)
                briefing = self.summarizer.extract_fallback_briefing(
                    grouped_articles=grouped,
                    briefing_date=self.briefing_date,
                )
            else:
                briefing = {
                    "briefingDate": self.briefing_date,
                    "topHeadlines": [],
                    "articles": [],
                }
        finally:
            if client is not None and orig_generate is not None:
                client.generate_json = orig_generate
            self.gemini_latency_ms = round((time.perf_counter() - t0) * 1000, 2)

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

    def write_outputs(
        self,
        briefing: dict[str, Any],
        pipeline_latency_ms: float | None = None,
    ) -> tuple[Path, Path]:
        """Write dynamic daily briefing to latest.json and historical archive, and telemetry."""
        output_path = self.output_dir
        output_path.mkdir(parents=True, exist_ok=True)

        archive_dir = output_path / "archive"
        archive_dir.mkdir(parents=True, exist_ok=True)

        latest_path = output_path / "latest.json"
        archive_path = archive_dir / f"{self.date_str}.json"

        if isinstance(self.ref_datetime, datetime):
            timestamp_str = self.ref_datetime.strftime("%Y-%m-%d_%H%M%S")
        else:
            timestamp_str = datetime.now(timezone.utc).strftime("%Y-%m-%d_%H%M%S")
        timestamped_archive_path = archive_dir / f"{timestamp_str}.json"

        content = json.dumps(briefing, ensure_ascii=False, indent=2) + "\n"

        with open(latest_path, "w", encoding="utf-8") as f:
            f.write(content)

        with open(archive_path, "w", encoding="utf-8") as f:
            f.write(content)

        with open(timestamped_archive_path, "w", encoding="utf-8") as f:
            f.write(content)

        logger.info(
            "Saved latest briefing to %s, day archive to %s, and timestamped archive to %s",
            latest_path,
            archive_path,
            timestamped_archive_path,
        )

        generate_archive_manifest(archive_dir)

        if pipeline_latency_ms is None:
            if self.pipeline_start_time > 0:
                pipeline_latency_ms = round((time.perf_counter() - self.pipeline_start_time) * 1000, 2)
            else:
                pipeline_latency_ms = 0.0

        telemetry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "date": self.date_str,
            "feeds_attempted": self.feeds_attempted,
            "feeds_failed": self.feeds_failed,
            "raw_articles_count": self.raw_articles_count,
            "filtered_count": self.filtered_count,
            "gemini_latency_ms": self.gemini_latency_ms,
            "gemini_fallback_used": self.gemini_fallback_used,
            "category_breakdown": self.category_breakdown,
            "feed_status": self.feed_status,
            "pipeline_latency_ms": pipeline_latency_ms,
        }

        telemetry_dir = output_path / "telemetry"
        telemetry_dir.mkdir(parents=True, exist_ok=True)

        telemetry_latest_path = telemetry_dir / "latest.json"
        telemetry_archive_path = telemetry_dir / f"{self.date_str}.json"

        telemetry_json = json.dumps(telemetry, ensure_ascii=False, indent=2) + "\n"
        with open(telemetry_latest_path, "w", encoding="utf-8") as f:
            f.write(telemetry_json)
        with open(telemetry_archive_path, "w", encoding="utf-8") as f:
            f.write(telemetry_json)

        logger.info("Saved telemetry to %s and %s", telemetry_latest_path, telemetry_archive_path)

        return latest_path, archive_path

    def run(self) -> dict[str, Any]:
        """Execute the end-to-end news briefing pipeline."""
        self.pipeline_start_time = time.perf_counter()
        logger.info("Starting Daily Korea News Briefing pipeline (dry_run=%s)", self.dry_run)
        feeds = self.load_feeds()
        candidates = self.fetch_candidate_articles(feeds)
        retained = self.filter_articles(candidates)
        briefing = self.summarize(retained)
        self.write_outputs(briefing)
        pipeline_latency_ms = round((time.perf_counter() - self.pipeline_start_time) * 1000, 2)
        logger.info(
            "Pipeline completed successfully for date %s (latency: %.2fms)",
            self.date_str,
            pipeline_latency_ms,
        )
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

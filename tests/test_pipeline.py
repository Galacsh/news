"""Unit tests for the end-to-end news briefing pipeline runner."""

from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
import sys
from typing import Any
import urllib.error

import pytest

from src.ingest.models import Article, FeedSource
from src.llm.client import GeminiAPIError, GeminiClient
from src.pipeline import (
    DailyBriefingPipeline,
    build_parser,
    generate_archive_manifest,
    load_env_files,
    main,
    parse_pipeline_date,
    run_pipeline,
)


@pytest.fixture(autouse=True)
def mock_body_enrichment_default(monkeypatch: pytest.MonkeyPatch) -> None:
    """Mock enrich_articles_with_body across pipeline tests to avoid live HTTP calls while setting transient body."""
    def _mock_enrich(
        articles: list[Article],
        max_workers: int = 5,
        extractor: Any = None,
    ) -> list[Article]:
        for art in articles:
            if not getattr(art, "body", None):
                art.body = f"모의 본문 텍스트: {art.title}"
        return articles

    monkeypatch.setattr("src.pipeline.enrich_articles_with_body", _mock_enrich)


def test_load_env_files_priority(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Test that .env.local takes precedence over .env, and existing os.environ keys are preserved."""
    # Ensure test keys are not pre-set
    monkeypatch.delenv("TEST_KEY_LOCAL", raising=False)
    monkeypatch.delenv("TEST_KEY_SHARED", raising=False)
    monkeypatch.delenv("TEST_KEY_DEFAULT", raising=False)
    monkeypatch.delenv("TEST_KEY_PRESET", raising=False)

    # Pre-set an environment variable in os.environ
    monkeypatch.setenv("TEST_KEY_PRESET", "original_preset")

    # Create .env.local
    local_env_content = (
        "# Local override environment\n"
        "TEST_KEY_LOCAL=local_value\n"
        "TEST_KEY_SHARED=shared_from_local\n"
        'TEST_KEY_PRESET="overwritten_local"\n'
        'QUOTED_VAR="hello world"\n'
        "SINGLE_QUOTED='single world'\n"
        "export EXPORTED_VAR=exported_val\n"
    )
    (tmp_path / ".env.local").write_text(local_env_content, encoding="utf-8")

    # Create .env
    default_env_content = (
        "# Default environment\n"
        "TEST_KEY_DEFAULT=default_value\n"
        "TEST_KEY_SHARED=shared_from_default\n"
        "TEST_KEY_PRESET=overwritten_default\n"
    )
    (tmp_path / ".env").write_text(default_env_content, encoding="utf-8")

    load_env_files(tmp_path)

    # 1. Pre-existing environment variable is preserved
    assert os.environ.get("TEST_KEY_PRESET") == "original_preset"

    # 2. Key defined only in .env.local is injected
    assert os.environ.get("TEST_KEY_LOCAL") == "local_value"

    # 3. Key in both files uses .env.local value (priority)
    assert os.environ.get("TEST_KEY_SHARED") == "shared_from_local"

    # 4. Key defined only in .env is injected
    assert os.environ.get("TEST_KEY_DEFAULT") == "default_value"

    # 5. Quotes and exports parsed cleanly
    assert os.environ.get("QUOTED_VAR") == "hello world"
    assert os.environ.get("SINGLE_QUOTED") == "single world"
    assert os.environ.get("EXPORTED_VAR") == "exported_val"


def test_load_env_files_missing_graceful(tmp_path: Path) -> None:
    """Test that missing env files do not cause errors."""
    empty_dir = tmp_path / "empty_dir"
    empty_dir.mkdir()
    # Should execute without throwing any exception
    load_env_files(empty_dir)


def test_parse_pipeline_date() -> None:
    """Test date parsing logic across string, datetime, and None inputs."""
    # None returns current date
    ref_now, date_now, iso_now = parse_pipeline_date(None)
    assert len(date_now) == 10
    assert "T" in iso_now

    # YYYY-MM-DD string
    ref_dt, date_str, iso_str = parse_pipeline_date("2026-10-25")
    assert date_str == "2026-10-25"
    assert "2026-10-25" in iso_str

    # Full ISO 8601 string
    ref_iso, date_iso, iso_res = parse_pipeline_date("2026-10-25T14:30:00+00:00")
    assert date_iso == "2026-10-25"
    assert iso_res == "2026-10-25T14:30:00+00:00"

    # Datetime object
    dt_obj = datetime(2026, 10, 25, 12, 0, tzinfo=timezone.utc)
    ref_from_dt, date_from_dt, iso_from_dt = parse_pipeline_date(dt_obj)
    assert date_from_dt == "2026-10-25"
    assert "2026-10-25" in iso_from_dt


@pytest.fixture
def mock_feeds_file(tmp_path: Path) -> Path:
    """Generate a temporary feeds.json file with active and inactive entries."""
    feeds_file = tmp_path / "feeds.json"
    feeds_data = {
        "feeds": [
            {
                "name": "테스트 언론 - 정치",
                "url": "https://example.com/rss/politics.xml",
                "category": "정치",
                "categoryId": 1,
                "is_active": True,
            },
            {
                "name": "테스트 언론 - 경제",
                "url": "https://example.com/rss/economy.xml",
                "category": "경제·금융",
                "categoryId": 2,
                "is_active": True,
            },
            {
                "name": "비활성 피드",
                "url": "https://example.com/rss/inactive.xml",
                "category": "사회",
                "categoryId": 4,
                "is_active": False,
            },
        ]
    }
    feeds_file.write_text(json.dumps(feeds_data), encoding="utf-8")
    return feeds_file


def test_run_pipeline_dry_run_success(
    tmp_path: Path,
    mock_feeds_file: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test run_pipeline end-to-end in dry-run mode producing valid latest.json and archive files."""
    # Mock RSS feed fetch to return sample articles
    sample_articles = [
        Article(
            id="art-1",
            title="정부 새 경제 부양책 국무회의 통과",
            summary="국무회의에서 대규모 경기 부양 대책이 최종 의결되었습니다.",
            url="https://example.com/news/1",
            outlet="테스트 언론",
            published_at="2026-10-25T10:00:00+00:00",
            category="경제·금융",
            category_id=2,
        ),
        Article(
            id="art-2",
            title="국회 본회의 정치 현안 합의",
            summary="여야 원내대표가 쟁점 법안 처리에 전격 합의했습니다.",
            url="https://example.com/news/2",
            outlet="테스트 언론",
            published_at="2026-10-25T11:00:00+00:00",
            category="정치",
            category_id=1,
        ),
    ]

    monkeypatch.setattr(
        "src.ingest.rss.RSSFeedParser.parse_feed",
        lambda url, category="", outlet="", timeout=10.0: [
            art for art in sample_articles if art.category == category or not category
        ],
    )

    output_dir = tmp_path / "data"

    briefing = run_pipeline(
        feeds_path=mock_feeds_file,
        output_dir=output_dir,
        dry_run=True,
        date="2026-10-25",
    )

    # 1. Output files exist
    latest_file = output_dir / "latest.json"
    archive_files = list((output_dir / "archive").glob("2026-10-25_*.json"))

    assert latest_file.is_file(), "latest.json must be written"
    assert len(archive_files) == 1, "Timestamped archive must be written"
    assert not (output_dir / "archive" / "2026-10-25.json").exists(), "Day-level archive should not exist"
    archive_file = archive_files[0]

    # 2. Validate JSON structure
    with open(latest_file, "r", encoding="utf-8") as f:
        latest_data = json.load(f)

    assert "briefingDate" in latest_data
    assert "topHeadlines" in latest_data
    assert "articles" in latest_data

    # 3. Exactly 3 topHeadlines with sequential IDs 1, 2, 3
    assert len(latest_data["topHeadlines"]) == 3
    for idx, item in enumerate(latest_data["topHeadlines"], start=1):
        assert item["id"] == idx
        assert "headline" in item
        assert "summary" in item
        assert "impact" in item
        assert "deepDive" in item
        assert "links" in item
        assert "categoryId" in item
        assert "body" not in item

    # 4. Articles have continuous sequential integer IDs starting from 4
    for idx, item in enumerate(latest_data["articles"], start=4):
        assert item["id"] == idx
        assert "headline" in item
        assert "summary" in item
        assert "impact" in item
        assert "deepDive" in item
        assert "links" in item
        assert "categoryId" in item
        assert "body" not in item

    assert '"body":' not in latest_file.read_text(encoding="utf-8")
    assert '"body":' not in archive_file.read_text(encoding="utf-8")

    # 5. Archive content matches latest.json
    with open(archive_file, "r", encoding="utf-8") as f:
        archive_data = json.load(f)
    assert archive_data == latest_data

    # 6. Telemetry output exists and contains expected schema and metrics
    telemetry_latest_file = output_dir / "telemetry" / "latest.json"
    telemetry_archive_file = output_dir / "telemetry" / "2026-10-25.json"

    assert telemetry_latest_file.is_file(), "telemetry/latest.json must be written"
    assert telemetry_archive_file.is_file(), "telemetry/2026-10-25.json must be written"

    with open(telemetry_latest_file, "r", encoding="utf-8") as f:
        telemetry_data = json.load(f)

    assert "timestamp" in telemetry_data
    assert telemetry_data["date"] == "2026-10-25"
    assert telemetry_data["feeds_attempted"] == 2
    assert telemetry_data["feeds_failed"] == 0
    assert telemetry_data["raw_articles_count"] == 2
    assert telemetry_data["filtered_count"] == 2
    assert isinstance(telemetry_data["gemini_latency_ms"], (int, float))
    assert telemetry_data["gemini_fallback_used"] is False
    assert telemetry_data["category_breakdown"] == {"경제·금융": 1, "정치": 1}
    assert isinstance(telemetry_data["feed_status"], list)
    assert len(telemetry_data["feed_status"]) == 2
    assert isinstance(telemetry_data["pipeline_latency_ms"], (int, float))

    with open(telemetry_archive_file, "r", encoding="utf-8") as f:
        telemetry_archive_data = json.load(f)
    assert telemetry_archive_data == telemetry_data


def test_run_pipeline_empty_feeds(tmp_path: Path) -> None:
    """Test pipeline execution when feeds catalog is empty, ensuring fallback briefing."""
    empty_feeds = tmp_path / "empty_feeds.json"
    empty_feeds.write_text(json.dumps({"feeds": []}), encoding="utf-8")

    output_dir = tmp_path / "output"

    briefing = run_pipeline(
        feeds_path=empty_feeds,
        output_dir=output_dir,
        dry_run=True,
        date="2026-10-25",
    )

    latest_file = output_dir / "latest.json"
    assert latest_file.is_file()
    assert len(briefing["topHeadlines"]) == 0
    assert len(briefing["articles"]) == 0


def test_run_pipeline_network_error_fallback(
    tmp_path: Path,
    mock_feeds_file: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test pipeline resiliency against RSS network errors, verifying empty fallback on zero articles."""

    def mock_failing_parse(*args, **kwargs):
        raise urllib.error.URLError("Simulated connection timeout")

    monkeypatch.setattr("src.ingest.rss.RSSFeedParser.parse_feed", mock_failing_parse)

    output_dir = tmp_path / "output_err"

    briefing = run_pipeline(
        feeds_path=mock_feeds_file,
        output_dir=output_dir,
        dry_run=True,
        date="2026-10-25",
    )

    assert (output_dir / "latest.json").is_file()
    assert len(list((output_dir / "archive").glob("2026-10-25_*.json"))) == 1
    assert not (output_dir / "archive" / "2026-10-25.json").exists()
    assert len(briefing["topHeadlines"]) == 0
    assert len(briefing["articles"]) == 0


def test_run_pipeline_llm_error_fallback(
    tmp_path: Path,
    mock_feeds_file: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test pipeline extractive fallback using real articles when LLM generation fails."""
    sample_data = [
        ("정치", 1, "국회 본회의 정치 현안 여야 전격 합의"),
        ("경제·금융", 2, "한국은행 기준금리 동결 발표 및 시장 영향"),
        ("IT·과학", 3, "국내 연구진 차세대 양자 컴퓨터 소자 개발"),
    ]
    sample_articles = [
        Article(
            id=f"art-{i}",
            title=title,
            summary=f"뉴스 요약 설명 {i}",
            url=f"https://example.com/news/{i}",
            outlet="테스트 언론",
            published_at="2026-10-25T10:00:00+00:00",
            category=cat,
            category_id=cid,
        )
        for i, (cat, cid, title) in enumerate(sample_data, start=1)
    ]

    monkeypatch.setattr(
        "src.ingest.rss.RSSFeedParser.parse_feed",
        lambda url, category="", outlet="", timeout=10.0: sample_articles,
    )

    def mock_failing_generate(*args, **kwargs):
        raise GeminiAPIError("Resource exhausted: 429 quota reached")

    monkeypatch.setattr(
        "src.llm.client.GeminiClient.generate_json",
        mock_failing_generate,
    )

    output_dir = tmp_path / "output_llm_err"

    briefing = run_pipeline(
        feeds_path=mock_feeds_file,
        output_dir=output_dir,
        dry_run=True,
        date="2026-10-25",
    )

    assert (output_dir / "latest.json").is_file()
    assert len(list((output_dir / "archive").glob("2026-10-25_*.json"))) == 1
    assert not (output_dir / "archive" / "2026-10-25.json").exists()
    assert len(briefing["topHeadlines"]) == 3
    assert briefing["topHeadlines"][0]["id"] == 1
    assert "국회 본회의 정치 현안 여야 전격 합의" in briefing["topHeadlines"][0]["headline"]
    for item in briefing["topHeadlines"] + briefing.get("articles", []):
        assert "deepDive" in item
        assert "body" not in item


def test_run_pipeline_empty_articles(
    tmp_path: Path,
    mock_feeds_file: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test pipeline returns empty briefing when no articles are fetched."""
    monkeypatch.setattr(
        "src.ingest.rss.RSSFeedParser.parse_feed",
        lambda url, category="", outlet="", timeout=10.0: [],
    )

    output_dir = tmp_path / "output_empty"

    briefing = run_pipeline(
        feeds_path=mock_feeds_file,
        output_dir=output_dir,
        dry_run=True,
        date="2026-10-25",
    )

    assert (output_dir / "latest.json").is_file()
    assert len(briefing["topHeadlines"]) == 0
    assert len(briefing["articles"]) == 0


def test_cli_main_success(tmp_path: Path, mock_feeds_file: Path) -> None:
    """Test CLI main() runner execution with valid command-line arguments."""
    output_dir = tmp_path / "cli_out"
    exit_code = main(
        [
            "--dry-run",
            "--feeds-path",
            str(mock_feeds_file),
            "--output-dir",
            str(output_dir),
            "--date",
            "2026-10-25",
        ]
    )

    assert exit_code == 0
    assert (output_dir / "latest.json").is_file()
    assert len(list((output_dir / "archive").glob("2026-10-25_*.json"))) == 1
    assert not (output_dir / "archive" / "2026-10-25.json").exists()


def test_cli_main_failure_handled(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Test CLI main() returns exit code 1 on unhandled exception."""

    def mock_failing_pipeline(*args, **kwargs):
        raise RuntimeError("Fatal system failure")

    monkeypatch.setattr("src.pipeline.run_pipeline", mock_failing_pipeline)

    exit_code = main(["--dry-run", "--output-dir", str(tmp_path)])
    assert exit_code == 1


def test_cli_subprocess_run(tmp_path: Path, mock_feeds_file: Path) -> None:
    """Test executing python -m src.pipeline via actual subprocess in dry-run mode."""
    cmd = [
        sys.executable,
        "-m",
        "src.pipeline",
        "--dry-run",
        "--feeds-path",
        str(mock_feeds_file),
        "--output-dir",
        str(tmp_path),
        "--date",
        "2026-10-25",
    ]

    res = subprocess.run(cmd, capture_output=True, text=True)
    assert res.returncode == 0, f"CLI runner failed with stderr:\n{res.stderr}"

    latest_file = tmp_path / "latest.json"
    archive_files = list((tmp_path / "archive").glob("2026-10-25_*.json"))

    assert latest_file.is_file(), "latest.json must be created by CLI process"
    assert len(archive_files) == 1, "Timestamped archive must be created by CLI process"
    assert not (tmp_path / "archive" / "2026-10-25.json").exists()

    with open(latest_file, "r", encoding="utf-8") as f:
        data = json.load(f)
    assert len(data["topHeadlines"]) == 0
    assert len(data["articles"]) == 0


def test_pipeline_telemetry_metrics(
    tmp_path: Path,
    mock_feeds_file: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify comprehensive pipeline telemetry logging, metrics types, feed failures, and LLM fallback tracking."""
    sample_article = Article(
        id="art-1",
        title="정부 새 경제 부양책 국무회의 통과",
        summary="국무회의에서 대규모 경기 부양 대책이 최종 의결되었습니다.",
        url="https://example.com/news/1",
        outlet="테스트 언론",
        published_at="2026-10-25T10:00:00+00:00",
        category="정치",
        category_id=1,
    )

    # 1. Normal run: check all fields and types
    monkeypatch.setattr(
        "src.ingest.rss.RSSFeedParser.parse_feed",
        lambda url, category="", outlet="", timeout=10.0: [sample_article],
    )

    out_normal = tmp_path / "telemetry_normal"
    run_pipeline(
        feeds_path=mock_feeds_file,
        output_dir=out_normal,
        dry_run=True,
        date="2026-10-25",
    )

    latest_telemetry = out_normal / "telemetry" / "latest.json"
    assert latest_telemetry.is_file()
    with open(latest_telemetry, "r", encoding="utf-8") as f:
        data = json.load(f)

    expected_keys = {
        "timestamp",
        "date",
        "feeds_attempted",
        "feeds_failed",
        "raw_articles_count",
        "filtered_count",
        "gemini_latency_ms",
        "gemini_fallback_used",
        "category_breakdown",
        "feed_status",
        "pipeline_latency_ms",
    }
    assert expected_keys.issubset(data.keys())
    assert isinstance(data["feeds_attempted"], int)
    assert isinstance(data["feeds_failed"], int)
    assert isinstance(data["raw_articles_count"], int)
    assert isinstance(data["filtered_count"], int)
    assert isinstance(data["gemini_latency_ms"], (int, float))
    assert isinstance(data["category_breakdown"], dict)
    assert isinstance(data["feed_status"], list)
    assert isinstance(data["gemini_fallback_used"], bool)
    assert isinstance(data["pipeline_latency_ms"], (int, float))

    for status_entry in data["feed_status"]:
        assert "outlet" in status_entry
        assert "url" in status_entry
        assert "category" in status_entry
        assert status_entry["status"] in ("success", "failed")
        assert isinstance(status_entry["articles_count"], int)
        assert isinstance(status_entry["latency_ms"], (int, float))

    # 2. Feed failure: verify feeds_failed > 0 when a feed raises an exception
    def mock_partial_fail_feed(url, category="", outlet="", timeout=10.0):
        if "politics" in url:
            raise urllib.error.URLError("Connection refused to politics feed")
        return [sample_article]

    monkeypatch.setattr(
        "src.ingest.rss.RSSFeedParser.parse_feed",
        mock_partial_fail_feed,
    )

    out_feed_fail = tmp_path / "telemetry_feed_fail"
    run_pipeline(
        feeds_path=mock_feeds_file,
        output_dir=out_feed_fail,
        dry_run=True,
        date="2026-10-25",
    )

    with open(out_feed_fail / "telemetry" / "latest.json", "r", encoding="utf-8") as f:
        feed_fail_data = json.load(f)

    assert feed_fail_data["feeds_failed"] > 0
    failed_statuses = [s for s in feed_fail_data["feed_status"] if s["status"] == "failed"]
    assert len(failed_statuses) > 0
    assert failed_statuses[0]["error"] is not None
    assert "Connection refused" in failed_statuses[0]["error"]

    # 3. LLM fallback: verify gemini_fallback_used == True when LLM falls back
    monkeypatch.setattr(
        "src.ingest.rss.RSSFeedParser.parse_feed",
        lambda url, category="", outlet="", timeout=10.0: [sample_article],
    )

    def mock_llm_error(*args, **kwargs):
        raise GeminiAPIError("503 Service Unavailable")

    monkeypatch.setattr(
        "src.llm.client.GeminiClient.generate_json",
        mock_llm_error,
    )

    out_llm_fail = tmp_path / "telemetry_llm_fail"
    run_pipeline(
        feeds_path=mock_feeds_file,
        output_dir=out_llm_fail,
        dry_run=True,
        date="2026-10-25",
    )

    with open(out_llm_fail / "telemetry" / "latest.json", "r", encoding="utf-8") as f:
        llm_fail_data = json.load(f)

    assert llm_fail_data["gemini_fallback_used"] is True


def test_timestamped_archive_generation_only(
    tmp_path: Path,
    mock_feeds_file: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify write_outputs generates timestamped archive and manifest.json without day-level archive."""
    sample_article = Article(
        id="art-1",
        title="테스트 헤드라인 기사",
        summary="테스트 요약 내용입니다.",
        url="https://example.com/news/1",
        outlet="테스트 언론",
        published_at="2026-10-25T14:30:15+00:00",
        category="정치",
        category_id=1,
    )

    monkeypatch.setattr(
        "src.ingest.rss.RSSFeedParser.parse_feed",
        lambda url, category="", outlet="", timeout=10.0: [sample_article],
    )

    out_dir = tmp_path / "data_timestamped"
    run_pipeline(
        feeds_path=mock_feeds_file,
        output_dir=out_dir,
        dry_run=True,
        date="2026-10-25T14:30:15Z",
    )

    archive_dir = out_dir / "archive"
    day_file = archive_dir / "2026-10-25.json"
    timestamped_file = archive_dir / "2026-10-25_143015.json"
    manifest_file = archive_dir / "manifest.json"

    assert not day_file.exists(), "Day-level archive 2026-10-25.json must NOT be generated"
    assert timestamped_file.is_file(), "Timestamped archive 2026-10-25_143015.json must be generated"
    assert manifest_file.is_file(), "Manifest file manifest.json must be generated"

    with open(timestamped_file, "r", encoding="utf-8") as f:
        ts_data = json.load(f)
    with open(manifest_file, "r", encoding="utf-8") as f:
        manifest_data = json.load(f)

    assert ts_data["briefingDate"] == "2026-10-25T14:30:15+00:00"

    assert "archives" in manifest_data
    assert "totalRuns" in manifest_data
    assert manifest_data["totalRuns"] == len(manifest_data["archives"])

    ts_entries = [e for e in manifest_data["archives"] if e["filename"] == "2026-10-25_143015.json"]
    assert len(ts_entries) == 1
    ts_entry = ts_entries[0]
    assert ts_entry["date"] == "2026-10-25"
    assert ts_entry["time"] == "14:30:15"
    assert ts_entry["briefingDate"] == "2026-10-25T14:30:15+00:00"
    assert isinstance(ts_entry["topHeadlines"], list)
    assert isinstance(ts_entry["totalArticles"], int)
    assert ts_entry["totalArticles"] > 0


def test_multiple_intraday_runs_preserve_archives(
    tmp_path: Path,
    mock_feeds_file: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify multiple intra-day runs create distinct timestamped archives without overwriting."""
    out_dir = tmp_path / "data_multirun"

    article_morning = Article(
        id="art-morning",
        title="오전 속보 헤드라인",
        summary="오전 주요 뉴스 내용입니다.",
        url="https://example.com/morning",
        outlet="테스트 언론",
        published_at="2026-10-25T09:00:00+00:00",
        category="정치",
        category_id=1,
    )

    article_afternoon = Article(
        id="art-afternoon",
        title="오후 긴급 속보 헤드라인",
        summary="오후 주요 뉴스 내용입니다.",
        url="https://example.com/afternoon",
        outlet="테스트 언론",
        published_at="2026-10-25T16:45:00+00:00",
        category="경제·금융",
        category_id=2,
    )

    # Run 1: Morning
    monkeypatch.setattr(
        "src.ingest.rss.RSSFeedParser.parse_feed",
        lambda url, category="", outlet="", timeout=10.0: [article_morning],
    )
    run_pipeline(
        feeds_path=mock_feeds_file,
        output_dir=out_dir,
        dry_run=True,
        date="2026-10-25T09:00:00Z",
    )

    morning_file = out_dir / "archive" / "2026-10-25_090000.json"
    assert morning_file.is_file()
    with open(morning_file, "r", encoding="utf-8") as f:
        morning_content = json.load(f)

    # Run 2: Afternoon
    monkeypatch.setattr(
        "src.ingest.rss.RSSFeedParser.parse_feed",
        lambda url, category="", outlet="", timeout=10.0: [article_afternoon],
    )
    run_pipeline(
        feeds_path=mock_feeds_file,
        output_dir=out_dir,
        dry_run=True,
        date="2026-10-25T16:45:00Z",
    )

    afternoon_file = out_dir / "archive" / "2026-10-25_164500.json"
    assert afternoon_file.is_file()
    with open(afternoon_file, "r", encoding="utf-8") as f:
        afternoon_content = json.load(f)

    # Verify both timestamped files exist independently and retain distinct content
    assert morning_file.is_file()
    with open(morning_file, "r", encoding="utf-8") as f:
        morning_recheck = json.load(f)
    assert morning_recheck == morning_content, "Morning archive was not overwritten"

    # Day-level file is not created; only timestamped files exist
    day_file = out_dir / "archive" / "2026-10-25.json"
    assert not day_file.exists(), "Day-level archive 2026-10-25.json should not exist"

    # Verify manifest has both runs in reverse chronological order
    manifest_file = out_dir / "archive" / "manifest.json"
    assert manifest_file.is_file()
    with open(manifest_file, "r", encoding="utf-8") as f:
        manifest = json.load(f)

    filenames = [e["filename"] for e in manifest["archives"]]
    assert "2026-10-25_164500.json" in filenames
    assert "2026-10-25_090000.json" in filenames

    idx_pm = filenames.index("2026-10-25_164500.json")
    idx_am = filenames.index("2026-10-25_090000.json")
    assert idx_pm < idx_am, "Afternoon run must precede morning run in manifest (newest first)"


def test_generate_archive_manifest_indexes_timestamped_and_legacy(tmp_path: Path) -> None:
    """Verify generate_archive_manifest indexes timestamped and legacy files with reverse chronological order."""
    archive_dir = tmp_path / "archive"
    archive_dir.mkdir(parents=True, exist_ok=True)

    # 1. Legacy file without time (YYYY-MM-DD.json)
    legacy_file_1 = archive_dir / "2026-10-22.json"
    legacy_file_1.write_text(
        json.dumps({
            "briefingDate": "2026-10-22",
            "topHeadlines": [
                {"id": 1, "categoryId": 1, "headline": "22일 헤드라인 1", "summary": "요약 1"},
                {"id": 2, "categoryId": 2, "headline": "22일 헤드라인 2", "summary": "요약 2"},
            ],
            "articles": [
                {"id": 3, "categoryId": 1, "title": "22일 기사 1", "summary": "요약"},
            ],
        }),
        encoding="utf-8",
    )

    # 2. Legacy file with ISO timestamp in briefingDate (YYYY-MM-DD.json)
    legacy_file_2 = archive_dir / "2026-10-23.json"
    legacy_file_2.write_text(
        json.dumps({
            "briefingDate": "2026-10-23T08:30:00+00:00",
            "topHeadlines": [
                {"id": 1, "categoryId": 1, "headline": "23일 아침 헤드라인", "summary": "요약"},
            ],
            "articles": [],
        }),
        encoding="utf-8",
    )

    # 3. Timestamped files (YYYY-MM-DD_HHMMSS.json)
    ts_file_morning = archive_dir / "2026-10-25_100000.json"
    ts_file_morning.write_text(
        json.dumps({
            "briefingDate": "2026-10-25T10:00:00+00:00",
            "topHeadlines": [
                {"id": 1, "categoryId": 1, "headline": "25일 10시 헤드라인", "summary": "요약"},
            ],
            "articles": [
                {"id": 2, "categoryId": 2, "title": "기사 A", "summary": "요약 A"},
                {"id": 3, "categoryId": 3, "title": "기사 B", "summary": "요약 B"},
            ],
        }),
        encoding="utf-8",
    )

    ts_file_evening = archive_dir / "2026-10-25_201530.json"
    ts_file_evening.write_text(
        json.dumps({
            "briefingDate": "2026-10-25T20:15:30+00:00",
            "topHeadlines": [
                {"id": 1, "categoryId": 1, "headline": "25일 저녁 헤드라인", "summary": "저녁 요약"},
            ],
            "articles": [
                {"id": 2, "categoryId": 1, "title": "기사 1", "summary": "요약 1"},
            ],
        }),
        encoding="utf-8",
    )

    # 4. Files to be ignored:
    # Pre-existing manifest.json
    (archive_dir / "manifest.json").write_text("{}", encoding="utf-8")
    # Non-json file
    (archive_dir / "notes.txt").write_text("some notes", encoding="utf-8")
    # Non-dict json
    (archive_dir / "array.json").write_text("[1, 2, 3]", encoding="utf-8")
    # Corrupt json
    (archive_dir / "2026-10-21.json").write_text("{corrupt json", encoding="utf-8")
    # Subdirectory
    (archive_dir / "backup").mkdir()

    manifest = generate_archive_manifest(archive_dir)

    assert manifest["totalRuns"] == 4
    assert len(manifest["archives"]) == 4

    # Verify reverse chronological sorting
    filenames = [e["filename"] for e in manifest["archives"]]
    assert filenames == [
        "2026-10-25_201530.json",
        "2026-10-25_100000.json",
        "2026-10-23.json",
        "2026-10-22.json",
    ]

    # Verify evening entry
    e0 = manifest["archives"][0]
    assert e0["filename"] == "2026-10-25_201530.json"
    assert e0["date"] == "2026-10-25"
    assert e0["time"] == "20:15:30"
    assert e0["briefingDate"] == "2026-10-25T20:15:30+00:00"
    assert e0["totalArticles"] == 2
    assert len(e0["topHeadlines"]) == 1

    # Verify morning entry
    e1 = manifest["archives"][1]
    assert e1["filename"] == "2026-10-25_100000.json"
    assert e1["date"] == "2026-10-25"
    assert e1["time"] == "10:00:00"
    assert e1["totalArticles"] == 3

    # Verify legacy file with time in briefingDate
    e2 = manifest["archives"][2]
    assert e2["filename"] == "2026-10-23.json"
    assert e2["date"] == "2026-10-23"
    assert e2["time"] == "08:30:00"
    assert e2["totalArticles"] == 1

    # Verify legacy file without time in briefingDate
    e3 = manifest["archives"][3]
    assert e3["filename"] == "2026-10-22.json"
    assert e3["date"] == "2026-10-22"
    assert e3["time"] == ""
    assert e3["totalArticles"] == 3


def test_generate_archive_manifest_empty_dir(tmp_path: Path) -> None:
    """Verify generate_archive_manifest handles an empty archive directory gracefully."""
    empty_archive = tmp_path / "empty_archive"
    manifest = generate_archive_manifest(empty_archive)

    assert manifest["totalRuns"] == 0
    assert manifest["archives"] == []
    assert (empty_archive / "manifest.json").is_file()


def test_pipeline_enriches_articles_with_body_and_strips_body_from_outputs(
    tmp_path: Path,
    mock_feeds_file: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify pipeline integrates body enrichment with max_workers and guarantees body never persists to disk."""
    sample_article = Article(
        id="art-body-test",
        title="인공지능 반도체 신기술 발표",
        summary="차세대 저전력 AI 반도체 혁신 기술이 공개되었습니다.",
        url="https://example.com/news/ai-chip",
        outlet="기술일보",
        published_at="2026-10-25T12:00:00+00:00",
        category="IT·과학",
        category_id=3,
    )

    enrich_calls: list[dict[str, Any]] = []

    def mock_enrich_tracker(articles: list[Article], max_workers: int = 5, extractor: Any = None) -> list[Article]:
        enrich_calls.append({"count": len(articles), "max_workers": max_workers})
        for art in articles:
            art.body = f"상세한 전체 본문 텍스트: {art.title}에 관한 심층 취재 내용입니다."
        return articles

    monkeypatch.setattr("src.pipeline.enrich_articles_with_body", mock_enrich_tracker)
    monkeypatch.setattr(
        "src.ingest.rss.RSSFeedParser.parse_feed",
        lambda url, category="", outlet="", timeout=10.0: [sample_article],
    )

    out_dir = tmp_path / "data_body_strip"
    pipeline = DailyBriefingPipeline(
        feeds_path=mock_feeds_file,
        output_dir=out_dir,
        dry_run=True,
        date="2026-10-25T12:00:00Z",
        max_workers=4,
    )

    briefing = pipeline.run()

    # 1. Verify enrich_articles_with_body was invoked with configured max_workers
    assert len(enrich_calls) == 1
    assert enrich_calls[0]["max_workers"] == 4
    assert enrich_calls[0]["count"] >= 1

    # 2. Output files exist
    latest_file = out_dir / "latest.json"
    archive_file = out_dir / "archive" / "2026-10-25_120000.json"
    assert latest_file.is_file()
    assert archive_file.is_file()

    # 3. In-memory briefing returned has clean structure and no transient body
    for item in briefing["topHeadlines"] + briefing["articles"]:
        assert "headline" in item
        assert "summary" in item
        assert "impact" in item
        assert "deepDive" in item
        assert "links" in item
        assert "body" not in item
        assert isinstance(item["deepDive"], dict)
        assert "lensTitle" in item["deepDive"]
        assert "sections" in item["deepDive"]
        assert len(item["deepDive"]["sections"]) == 2

    # 4. JSON files written to disk never leak transient body
    latest_content = latest_file.read_text(encoding="utf-8")
    archive_content = archive_file.read_text(encoding="utf-8")
    assert '"body":' not in latest_content
    assert '"body":' not in archive_content

    with open(latest_file, "r", encoding="utf-8") as f:
        saved_latest = json.load(f)
    for item in saved_latest["topHeadlines"] + saved_latest["articles"]:
        assert "deepDive" in item
        assert "body" not in item


def test_pipeline_summarize_batched_and_fallback(
    tmp_path: Path,
    mock_feeds_file: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify summarize handles batched output and fallback error recovery with sequential IDs and deepDive."""
    pipeline = DailyBriefingPipeline(
        feeds_path=mock_feeds_file,
        output_dir=tmp_path / "data_summarize",
        dry_run=True,
        date="2026-10-25",
    )

    art1 = Article(
        id="art-1",
        title="국회 본회의 기사",
        summary="국회 요약",
        url="https://example.com/1",
        outlet="언론사A",
        published_at="2026-10-25T10:00:00+00:00",
        category="정치",
        category_id=1,
    )
    art1.body = "정치 본문"

    art2 = Article(
        id="art-2",
        title="기준금리 기사",
        summary="금리 요약",
        url="https://example.com/2",
        outlet="언론사B",
        published_at="2026-10-25T11:00:00+00:00",
        category="경제·금융",
        category_id=2,
    )
    art2.body = "경제 본문"

    art3 = Article(
        id="art-3",
        title="인공지능 기술 기사",
        summary="AI 요약",
        url="https://example.com/3",
        outlet="언론사C",
        published_at="2026-10-25T12:00:00+00:00",
        category="IT·과학",
        category_id=3,
    )
    art3.body = "IT 본문"

    articles = [art1, art2, art3]

    # Normal summarization flow (calls summarizer.summarize_articles)
    res_normal = pipeline.summarize(articles)
    assert "topHeadlines" in res_normal
    assert len(res_normal["topHeadlines"]) == 3
    for idx, h in enumerate(res_normal["topHeadlines"], start=1):
        assert h["id"] == idx
        assert "deepDive" in h
        assert "lensTitle" in h["deepDive"]
        assert "sections" in h["deepDive"]
        assert "body" not in h

    for idx, a in enumerate(res_normal["articles"], start=4):
        assert a["id"] == idx
        assert "deepDive" in a
        assert "lensTitle" in a["deepDive"]
        assert "sections" in a["deepDive"]
        assert "body" not in a

    # Fallback flow: simulate error inside summarizer.summarize_articles
    def mock_fail_summarize(*args: Any, **kwargs: Any) -> Any:
        raise RuntimeError("Gemini API call failed")

    monkeypatch.setattr(pipeline.summarizer, "summarize_articles", mock_fail_summarize)
    res_fallback = pipeline.summarize(articles)

    assert pipeline.gemini_fallback_used is True
    assert len(res_fallback["topHeadlines"]) == 3
    for idx, h in enumerate(res_fallback["topHeadlines"], start=1):
        assert h["id"] == idx
        assert "deepDive" in h
        assert "lensTitle" in h["deepDive"]
        assert "sections" in h["deepDive"]
        assert "body" not in h

    for idx, a in enumerate(res_fallback["articles"], start=4):
        assert a["id"] == idx
        assert "deepDive" in a
        assert "lensTitle" in a["deepDive"]
        assert "sections" in a["deepDive"]
        assert "body" not in a




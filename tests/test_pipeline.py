"""Unit tests for the end-to-end news briefing pipeline runner."""

from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
import sys
import urllib.error

import pytest

from src.ingest.models import Article, FeedSource
from src.llm.client import GeminiAPIError, GeminiClient
from src.pipeline import (
    DailyBriefingPipeline,
    build_parser,
    load_env_files,
    main,
    parse_pipeline_date,
    run_pipeline,
)


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
    archive_file = output_dir / "archive" / "2026-10-25.json"

    assert latest_file.is_file(), "latest.json must be written"
    assert archive_file.is_file(), "archive/2026-10-25.json must be written"

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
        assert "links" in item
        assert "categoryId" in item

    # 4. Articles have continuous sequential integer IDs starting from 4
    for idx, item in enumerate(latest_data["articles"], start=4):
        assert item["id"] == idx
        assert "headline" in item
        assert "categoryId" in item

    # 5. Archive content matches latest.json
    with open(archive_file, "r", encoding="utf-8") as f:
        archive_data = json.load(f)
    assert archive_data == latest_data


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
    assert (output_dir / "archive" / "2026-10-25.json").is_file()
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
    assert (output_dir / "archive" / "2026-10-25.json").is_file()
    assert len(briefing["topHeadlines"]) == 3
    assert briefing["topHeadlines"][0]["id"] == 1
    assert "국회 본회의 정치 현안 여야 전격 합의" in briefing["topHeadlines"][0]["headline"]


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
    assert (output_dir / "archive" / "2026-10-25.json").is_file()


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
    archive_file = tmp_path / "archive" / "2026-10-25.json"

    assert latest_file.is_file(), "latest.json must be created by CLI process"
    assert archive_file.is_file(), "archive/2026-10-25.json must be created by CLI process"

    with open(latest_file, "r", encoding="utf-8") as f:
        data = json.load(f)
    assert len(data["topHeadlines"]) == 0
    assert len(data["articles"]) == 0

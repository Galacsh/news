"""Unit tests for GitHub Actions workflow configuration."""

from __future__ import annotations

from pathlib import Path
import re
import pytest

WORKFLOW_PATH = Path(".github/workflows/daily-briefing.yml")


@pytest.fixture(scope="module")
def workflow_content() -> str:
    """Fixture providing the raw text of the workflow file."""
    assert WORKFLOW_PATH.is_file(), f"Workflow file not found at {WORKFLOW_PATH}"
    return WORKFLOW_PATH.read_text(encoding="utf-8")


def test_workflow_file_exists() -> None:
    """Verify that .github/workflows/daily-briefing.yml exists as a regular file."""
    assert WORKFLOW_PATH.exists()
    assert WORKFLOW_PATH.is_file()


def test_workflow_triggers(workflow_content: str) -> None:
    """Verify that schedule cron and workflow_dispatch triggers are configured."""
    assert "on:" in workflow_content
    cron_match = re.search(r"cron:\s*['\"]45 6 \* \* \*['\"]", workflow_content)
    assert cron_match is not None, "Expected cron schedule '45 6 * * *' not found"
    tz_match = re.search(r"timezone:\s*['\"]Asia/Seoul['\"]", workflow_content)
    assert tz_match is not None, "Expected timezone 'Asia/Seoul' not found"
    assert "workflow_dispatch:" in workflow_content
    assert "push:" in workflow_content
    assert re.search(r"branches:\s*-\s*main", workflow_content) or "- main" in workflow_content


def test_workflow_permissions(workflow_content: str) -> None:
    """Verify write permissions for contents, pages, and id-token."""
    assert "permissions:" in workflow_content
    assert re.search(r"contents:\s*write", workflow_content) is not None
    assert re.search(r"pages:\s*write", workflow_content) is not None
    assert re.search(r"id-token:\s*write", workflow_content) is not None


def test_workflow_concurrency(workflow_content: str) -> None:
    """Verify concurrency group and cancel-in-progress settings."""
    assert "concurrency:" in workflow_content
    assert re.search(r"group:\s*['\"]?pages['\"]?", workflow_content) is not None
    assert re.search(r"cancel-in-progress:\s*false", workflow_content) is not None


def test_workflow_briefing_job_setup(workflow_content: str) -> None:
    """Verify checkout, timeout, and Python 3.13 setup with pip caching."""
    assert "briefing:" in workflow_content
    assert "runs-on: ubuntu-latest" in workflow_content
    assert re.search(r"timeout-minutes:\s*15", workflow_content) is not None
    assert "actions/checkout@v4" in workflow_content
    assert re.search(r"fetch-depth:\s*0", workflow_content) is not None
    assert "actions/setup-python@v5" in workflow_content
    assert re.search(r"python-version:\s*['\"]3\.13['\"]", workflow_content) is not None
    assert re.search(r"cache:\s*['\"]pip['\"]", workflow_content) is not None
    assert "pip install -r requirements.txt" in workflow_content


def test_workflow_briefing_job_timeout(workflow_content: str) -> None:
    """Verify briefing job has timeout-minutes: 15 configured for safety."""
    assert re.search(r"timeout-minutes:\s*15", workflow_content) is not None


def test_workflow_pipeline_execution(workflow_content: str) -> None:
    """Verify pipeline execution with GEMINI_API_KEY secret."""
    assert "python -m src.pipeline" in workflow_content
    assert "GEMINI_API_KEY:" in workflow_content
    assert "${{ secrets.GEMINI_API_KEY }}" in workflow_content


def test_workflow_git_commit_and_push(workflow_content: str) -> None:
    """Verify git commit and push step for updated data."""
    assert 'git config user.name "github-actions[bot]"' in workflow_content
    assert 'git config user.email "github-actions[bot]@users.noreply.github.com"' in workflow_content
    assert "git add data/" in workflow_content
    assert "git diff --staged --quiet" in workflow_content
    assert "chore: update daily news briefing [skip ci]" in workflow_content
    assert "git push" in workflow_content


def test_workflow_pages_upload_and_deploy(workflow_content: str) -> None:
    """Verify GitHub Pages upload artifact and deployment job."""
    assert "actions/upload-pages-artifact@v3" in workflow_content
    assert "deploy:" in workflow_content
    assert "needs: briefing" in workflow_content
    assert "name: github-pages" in workflow_content
    assert "${{ steps.deployment.outputs.page_url }}" in workflow_content
    assert "actions/deploy-pages@v4" in workflow_content

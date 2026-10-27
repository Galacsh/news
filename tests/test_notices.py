"""Tests for Notice Center schema, viewer page, and 7-day unread logic."""

from datetime import date, datetime, timedelta
import json
from pathlib import Path
import re


def parse_date(date_val) -> date | None:
    """Parse date from ISO string or YYYY-MM-DD."""
    if isinstance(date_val, date) and not isinstance(date_val, datetime):
        return date_val
    if isinstance(date_val, datetime):
        return date_val.date()
    if not isinstance(date_val, str):
        return None
    try:
        # Handles YYYY-MM-DD or ISO 8601 strings
        return datetime.fromisoformat(date_val.replace("Z", "+00:00")).date()
    except (ValueError, TypeError):
        try:
            return datetime.strptime(date_val[:10], "%Y-%m-%d").date()
        except (ValueError, TypeError):
            return None


def is_notice_recent(notice_date, reference_date: date | None = None, max_days: int = 7) -> bool:
    """Determine whether a notice date falls within the last `max_days` days."""
    if reference_date is None:
        reference_date = date.today()
    parsed = parse_date(notice_date)
    if not parsed:
        return False
    diff = (reference_date - parsed).days
    return 0 <= diff <= max_days


def calculate_unread_notices(
    notices: list[dict],
    read_notice_ids: list | set,
    reference_date: date | None = None,
    max_days: int = 7,
) -> list[dict]:
    """Return all notices that were published within max_days and are not in read_notice_ids."""
    if reference_date is None:
        reference_date = date.today()
    read_set = {str(nid) for nid in read_notice_ids} if read_notice_ids else set()

    unread = []
    for notice in notices:
        nid = str(notice.get("id", ""))
        ndate = notice.get("date")
        if nid and nid not in read_set and is_notice_recent(ndate, reference_date, max_days):
            unread.append(notice)
    return unread


def is_unread_badge_active(
    notices: list[dict],
    read_notice_ids: list | set,
    reference_date: date | None = None,
    max_days: int = 7,
) -> bool:
    """Return True if any unread notice exists within the 7-day window."""
    return len(calculate_unread_notices(notices, read_notice_ids, reference_date, max_days)) > 0


# ==============================================================================
# 1. Schema and Data Integrity Tests for data/notices.json
# ==============================================================================

def test_notices_json_file_exists():
    path = Path("data/notices.json")
    assert path.is_file(), "data/notices.json must exist"


def test_notices_json_is_valid_array():
    path = Path("data/notices.json")
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    assert isinstance(data, list), "data/notices.json must be a JSON array"


def test_notices_schema_requirements():
    path = Path("data/notices.json")
    with open(path, encoding="utf-8") as f:
        notices = json.load(f)

    seen_ids = set()
    for item in notices:
        assert isinstance(item, dict), "Each notice item must be an object"

        # id requirement: unique string or number
        assert "id" in item, "Notice missing 'id'"
        assert isinstance(item["id"], (str, int)), "'id' must be string or number"
        assert str(item["id"]).strip() != "", "'id' must not be empty"
        assert item["id"] not in seen_ids, f"Duplicate notice id found: {item['id']}"
        seen_ids.add(item["id"])

        # title requirement: non-empty string
        assert "title" in item, "Notice missing 'title'"
        assert isinstance(item["title"], str), "'title' must be string"
        assert item["title"].strip() != "", "'title' must not be empty"

        # date requirement: valid date string
        assert "date" in item, "Notice missing 'date'"
        parsed_d = parse_date(item["date"])
        assert parsed_d is not None, f"Notice 'date' must be valid date string: {item['date']}"

        # category requirement: string (e.g. update, notice, maintenance)
        assert "category" in item, "Notice missing 'category'"
        assert isinstance(item["category"], str), "'category' must be string"
        assert item["category"].strip() != "", "'category' must not be empty"

        # content requirement: non-empty string
        assert "content" in item, "Notice missing 'content'"
        assert isinstance(item["content"], str), "'content' must be string"
        assert item["content"].strip() != "", "'content' must not be empty"


def test_notices_has_recent_and_older_samples():
    path = Path("data/notices.json")
    with open(path, encoding="utf-8") as f:
        notices = json.load(f)

    if not notices:
        # Initialized/empty notices state
        return

    # Reference benchmark date from project context
    ref_date = date(2026, 10, 25)

    recent_count = sum(1 for n in notices if is_notice_recent(n["date"], ref_date, max_days=7))
    older_count = sum(1 for n in notices if not is_notice_recent(n["date"], ref_date, max_days=7))

    assert recent_count >= 1, "Must include at least one sample notice within 7 days of 2026-10-25"
    assert older_count >= 1, "Must include at least one older sample notice (>7 days)"


# ==============================================================================
# 2. DOM Structure and Styling Tests for notices.html
# ==============================================================================

def test_notices_html_file_exists():
    path = Path("notices.html")
    assert path.is_file(), "notices.html must exist"


def test_notices_html_head_and_styles():
    content = Path("notices.html").read_text(encoding="utf-8")

    # CDN scripts
    assert "cdn.tailwindcss.com" in content, "Must include Tailwind CDN"
    assert "@phosphor-icons/web" in content, "Must include Phosphor Icons CDN"

    # Pretendard font config
    assert "Pretendard" in content, "Must configure Pretendard font"

    # Dark slate styling
    assert "bg-slate-950" in content, "Must use bg-slate-950 background"
    assert "text-slate-100" in content, "Must use text-slate-100 text color"


def test_notices_html_header_back_link():
    content = Path("notices.html").read_text(encoding="utf-8")

    # Link back to index.html with text "← 뉴스 브리핑"
    assert 'href="index.html"' in content or "href='index.html'" in content, (
        "Header must contain link to index.html"
    )
    assert "← 뉴스 브리핑" in content, "Back link must have text '← 뉴스 브리핑'"


def test_notices_html_container_and_error_handling():
    content = Path("notices.html").read_text(encoding="utf-8")

    # Notices container element
    assert 'id="noticesContainer"' in content, "Must have #noticesContainer DOM element"


def test_notices_html_script_and_localstorage():
    content = Path("notices.html").read_text(encoding="utf-8")

    # Must fetch data/notices.json
    assert "data/notices.json" in content, "Script must fetch data/notices.json"

    # Must access read_notice_ids in localStorage
    assert "read_notice_ids" in content, "Script must reference read_notice_ids"
    assert re.search(r'localStorage\.setItem\(\s*["\']read_notice_ids["\']', content), (
        "Script must persist read_notice_ids to localStorage"
    )


# ==============================================================================
# 3. 7-Day Unread Calculation Logic Tests
# ==============================================================================

def test_unread_calculation_within_7_days():
    ref_date = date(2026, 10, 25)
    sample_notices = [
        {"id": "n1", "date": "2026-10-25", "title": "Today notice"},       # 0 days old -> unread
        {"id": "n2", "date": "2026-10-22", "title": "3 days ago notice"},   # 3 days old -> unread
        {"id": "n3", "date": "2026-10-18", "title": "7 days ago notice"},   # 7 days old -> unread
        {"id": "n4", "date": "2026-10-17", "title": "8 days ago notice"},   # 8 days old -> not unread
        {"id": "n5", "date": "2026-10-01", "title": "Old notice"},          # 24 days old -> not unread
    ]

    # Case 1: No notices read yet
    unread = calculate_unread_notices(sample_notices, read_notice_ids=[], reference_date=ref_date)
    unread_ids = [n["id"] for n in unread]
    assert unread_ids == ["n1", "n2", "n3"], "Only notices within 7 days should be unread"
    assert is_unread_badge_active(sample_notices, [], reference_date=ref_date) is True

    # Case 2: Today's notice read (n1 in read_notice_ids)
    unread_partial = calculate_unread_notices(sample_notices, read_notice_ids=["n1"], reference_date=ref_date)
    assert [n["id"] for n in unread_partial] == ["n2", "n3"]
    assert is_unread_badge_active(sample_notices, ["n1"], reference_date=ref_date) is True

    # Case 3: All recent notices read
    read_all_recent = ["n1", "n2", "n3"]
    unread_none = calculate_unread_notices(sample_notices, read_notice_ids=read_all_recent, reference_date=ref_date)
    assert unread_none == []
    assert is_unread_badge_active(sample_notices, read_all_recent, reference_date=ref_date) is False


def test_unread_calculation_ignores_older_unread_notices():
    ref_date = date(2026, 10, 25)
    # Notice that is 10 days old, not in read_notice_ids
    sample = [
        {"id": "old-1", "date": "2026-10-15", "title": "Old announcement"}
    ]
    unread = calculate_unread_notices(sample, read_notice_ids=[], reference_date=ref_date)
    assert len(unread) == 0, "Older notice (>7 days) must NOT trigger unread state"
    assert is_unread_badge_active(sample, [], reference_date=ref_date) is False


def test_unread_calculation_future_and_invalid_dates():
    ref_date = date(2026, 10, 25)
    sample = [
        {"id": "future-1", "date": "2026-10-28", "title": "Future notice"},
        {"id": "invalid-1", "date": "invalid-date", "title": "Invalid notice"},
    ]
    unread = calculate_unread_notices(sample, read_notice_ids=[], reference_date=ref_date)
    assert len(unread) == 0, "Future or invalid dates must not be counted as recent unread"


def test_unread_simulation_visiting_notices_clears_badge():
    ref_date = date(2026, 10, 25)
    notices = [
        {"id": "n1", "date": "2026-10-25", "title": "Update 1"},
        {"id": "n2", "date": "2026-10-24", "title": "Update 2"},
    ]

    # Initial state: user has never visited notices.html
    local_storage = {"read_notice_ids": []}
    assert is_unread_badge_active(notices, local_storage["read_notice_ids"], reference_date=ref_date) is True

    # Simulated user visit to notices.html: marks displayed notices as read
    displayed_ids = [n["id"] for n in notices]
    local_storage["read_notice_ids"] = list(set(local_storage["read_notice_ids"] + displayed_ids))

    # Badge should now be cleared
    assert is_unread_badge_active(notices, local_storage["read_notice_ids"], reference_date=ref_date) is False
    assert calculate_unread_notices(notices, local_storage["read_notice_ids"], reference_date=ref_date) == []


# ==============================================================================
# 4. Main Dashboard (index.html) Notice Link and Unread Badge Tests
# ==============================================================================

def test_index_html_notice_link_and_badge():
    """Verify that index.html contains notice link pointing to notices.html and #noticeBadge."""
    path = Path("index.html")
    assert path.is_file(), "index.html must exist"
    content = path.read_text(encoding="utf-8")

    # Header must contain notice link pointing to notices.html
    assert 'href="notices.html"' in content or "href='notices.html'" in content, (
        "index.html header must contain link to notices.html"
    )
    assert 'id="noticeLink"' in content, "Notice link must have id='noticeLink'"

    # Must contain bell icon
    assert "ph-bell" in content, "Notice link must contain ph-bell icon"

    # Must contain #noticeBadge element with initial hidden state
    assert 'id="noticeBadge"' in content, "Must contain element with id='noticeBadge'"
    assert re.search(r'id=["\']noticeBadge["\'][^>]*class=["\'][^"\']*hidden', content) or \
           re.search(r'class=["\'][^"\']*hidden[^"\']*["\'][^>]*id=["\']noticeBadge["\']', content), (
        "#noticeBadge must include 'hidden' class by default"
    )

    # Must be placed in header alongside #refreshBtn
    header_match = re.search(r"<header.*?</header>", content, re.DOTALL)
    assert header_match, "index.html must have <header> element"
    header_html = header_match.group(0)
    assert 'id="noticeLink"' in header_html, "#noticeLink must be located inside <header>"
    assert 'id="refreshBtn"' in header_html, "#refreshBtn must be located inside <header>"


def test_index_html_script_unread_notice_logic():
    """Verify script in index.html fetches notices, checks localStorage, and applies 7-day unread logic."""
    content = Path("index.html").read_text(encoding="utf-8")

    # Script references data/notices.json
    assert "data/notices.json" in content, "index.html script must reference data/notices.json"

    # Script accesses read_notice_ids in localStorage
    assert "read_notice_ids" in content, "index.html script must reference read_notice_ids"
    assert "localStorage.getItem" in content, "index.html script must read from localStorage"

    # Script has checkUnreadNotices function
    assert "checkUnreadNotices" in content, "index.html script must define checkUnreadNotices"

    # 7-day calculation logic present (7 * 24 * 60 * 60 * 1000 or similar 7-day window)
    assert "7 * 24 * 60 * 60 * 1000" in content or "7 * 86400000" in content, (
        "index.html script must contain 7-day window calculation in milliseconds"
    )

    # Badge visibility toggling
    assert "noticeBadge" in content, "index.html script must reference #noticeBadge"


def test_index_unread_badge_logic_unit_and_simulation():
    """Unit and simulation test verifying 7-day unread badge logic:
    - recent unread notices trigger badge
    - read notices or notices > 7 days old do not trigger badge
    - mixed scenario with multiple notices
    """
    now = datetime(2026, 10, 25, 12, 0, 0)
    now_ms = int(now.timestamp() * 1000)
    seven_days_ms = 7 * 24 * 60 * 60 * 1000
    one_day_ms = 24 * 60 * 60 * 1000

    def evaluate_badge(notices: list[dict], read_ids: list[str]) -> bool:
        """Mirror the client-side JavaScript logic in index.html."""
        read_set = set(str(nid) for nid in read_ids)
        for notice in notices:
            if not notice or not notice.get("id"):
                continue
            nid = str(notice["id"])
            if nid in read_set:
                continue
            date_str = notice.get("date")
            if not date_str:
                continue
            try:
                dt = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
            except ValueError:
                continue
            notice_ms = int(dt.timestamp() * 1000)
            diff_ms = now_ms - notice_ms
            if diff_ms <= seven_days_ms and notice_ms <= now_ms + one_day_ms:
                return True
        return False

    sample_notices = [
        {"id": "n1", "date": "2026-10-25T10:00:00", "title": "Today's notice"},          # diff < 1 day -> unread
        {"id": "n2", "date": "2026-10-21T12:00:00", "title": "4 days ago notice"},        # diff 4 days -> unread
        {"id": "n3", "date": "2026-10-18T12:00:00", "title": "7 days ago notice"},        # diff exactly 7 days -> unread
        {"id": "n4", "date": "2026-10-17T11:00:00", "title": "8 days ago notice"},        # diff > 7 days -> NOT unread
        {"id": "n5", "date": "2026-10-01T00:00:00", "title": "Old notice"},               # diff 24 days -> NOT unread
    ]

    # 1. Unread notices exist within 7 days -> badge active
    assert evaluate_badge(sample_notices, read_ids=[]) is True

    # 2. Only older notices unread (all within 7 days read) -> badge inactive
    assert evaluate_badge(sample_notices, read_ids=["n1", "n2", "n3"]) is False

    # 3. Only older notices exist (>7 days) -> badge inactive
    older_only = [
        {"id": "n4", "date": "2026-10-17T11:00:00", "title": "8 days ago"},
        {"id": "n5", "date": "2026-10-01T00:00:00", "title": "Old notice"},
    ]
    assert evaluate_badge(older_only, read_ids=[]) is False

    # 4. Partial read: one recent read, one recent still unread -> badge active
    assert evaluate_badge(sample_notices, read_ids=["n1"]) is True

    # 5. Future notice > 1 day in advance -> badge inactive
    future_notice = [{"id": "n-fut", "date": "2026-10-30T00:00:00", "title": "Far future"}]
    assert evaluate_badge(future_notice, read_ids=[]) is False

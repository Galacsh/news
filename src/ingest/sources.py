"""News feed sources management, verification, probing, and catalog persistence."""

from __future__ import annotations

import concurrent.futures
import json
import logging
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

from src.ingest.models import FeedSource

logger = logging.getLogger(__name__)

DEFAULT_USER_AGENT: str = (
    "Mozilla/5.0 (compatible; KoreaNewsBriefingBot/1.0; "
    "+https://github.com/galacsh/news)"
)

TARGET_CATEGORIES: list[str] = [
    "정치",
    "경제·금융",
    "산업·기업",
    "사회",
    "국제·글로벌",
    "AI·빅테크",
    "IT·통신",
    "문화·콘텐츠",
    "스포츠",
    "라이프스타일",
]

# Shorthand alias mappings to canonical category names
CATEGORY_ALIASES: dict[str, str] = {
    "정치": "정치",
    "경제": "경제·금융",
    "금융": "경제·금융",
    "경제금융": "경제·금융",
    "경제·금융": "경제·금융",
    "산업": "산업·기업",
    "기업": "산업·기업",
    "산업기업": "산업·기업",
    "산업·기업": "산업·기업",
    "사회": "사회",
    "국제": "국제·글로벌",
    "글로벌": "국제·글로벌",
    "국제글로벌": "국제·글로벌",
    "국제·글로벌": "국제·글로벌",
    "세계": "국제·글로벌",
    "ai": "AI·빅테크",
    "빅테크": "AI·빅테크",
    "인공지능": "AI·빅테크",
    "ai·빅테크": "AI·빅테크",
    "it": "IT·통신",
    "통신": "IT·통신",
    "it·통신": "IT·통신",
    "문화": "문화·콘텐츠",
    "콘텐츠": "문화·콘텐츠",
    "연예": "문화·콘텐츠",
    "문화·콘텐츠": "문화·콘텐츠",
    "스포츠": "스포츠",
    "체육": "스포츠",
    "라이프": "라이프스타일",
    "생활": "라이프스타일",
    "라이프스타일": "라이프스타일",
}

# Pre-curated verified fallback feeds mapped to all 10 target categories
DEFAULT_FALLBACK_FEEDS: list[FeedSource] = [
    # Cat 1: 정치
    FeedSource(
        name="연합뉴스 - 정치",
        url="https://www.yna.co.kr/rss/politics.xml",
        category="정치",
        category_id=1,
        is_active=True,
    ),
    FeedSource(
        name="동아일보 - 정치",
        url="https://rss.donga.com/politics.xml",
        category="정치",
        category_id=1,
        is_active=True,
    ),
    FeedSource(
        name="매일경제 - 정치",
        url="https://www.mk.co.kr/rss/30200030/",
        category="정치",
        category_id=1,
        is_active=True,
    ),
    # Cat 2: 경제·금융
    FeedSource(
        name="연합뉴스 - 경제",
        url="https://www.yna.co.kr/rss/economy.xml",
        category="경제·금융",
        category_id=2,
        is_active=True,
    ),
    FeedSource(
        name="한국경제 - 경제",
        url="https://www.hankyung.com/feed/economy",
        category="경제·금융",
        category_id=2,
        is_active=True,
    ),
    FeedSource(
        name="매일경제 - 경제",
        url="https://www.mk.co.kr/rss/30100041/",
        category="경제·금융",
        category_id=2,
        is_active=True,
    ),
    FeedSource(
        name="동아일보 - 경제",
        url="https://rss.donga.com/economy.xml",
        category="경제·금융",
        category_id=2,
        is_active=True,
    ),
    # Cat 3: 산업·기업
    FeedSource(
        name="연합뉴스 - 산업",
        url="https://www.yna.co.kr/rss/industry.xml",
        category="산업·기업",
        category_id=3,
        is_active=True,
    ),
    FeedSource(
        name="한국경제 - 금융·증권",
        url="https://www.hankyung.com/feed/finance",
        category="산업·기업",
        category_id=3,
        is_active=True,
    ),
    FeedSource(
        name="매일경제 - 기업경영",
        url="https://www.mk.co.kr/rss/50100032/",
        category="산업·기업",
        category_id=3,
        is_active=True,
    ),
    # Cat 4: 사회
    FeedSource(
        name="연합뉴스 - 사회",
        url="https://www.yna.co.kr/rss/society.xml",
        category="사회",
        category_id=4,
        is_active=True,
    ),
    FeedSource(
        name="동아일보 - 사회",
        url="https://rss.donga.com/national.xml",
        category="사회",
        category_id=4,
        is_active=True,
    ),
    FeedSource(
        name="매일경제 - 사회",
        url="https://www.mk.co.kr/rss/50400012/",
        category="사회",
        category_id=4,
        is_active=True,
    ),
    # Cat 5: 국제·글로벌
    FeedSource(
        name="연합뉴스 - 국제",
        url="https://www.yna.co.kr/rss/international.xml",
        category="국제·글로벌",
        category_id=5,
        is_active=True,
    ),
    FeedSource(
        name="동아일보 - 국제",
        url="https://rss.donga.com/global.xml",
        category="국제·글로벌",
        category_id=5,
        is_active=True,
    ),
    FeedSource(
        name="매일경제 - 국제",
        url="https://www.mk.co.kr/rss/30300018/",
        category="국제·글로벌",
        category_id=5,
        is_active=True,
    ),
    # Cat 6: AI·빅테크
    FeedSource(
        name="AI타임스 - 전체",
        url="https://www.aitimes.com/rss/allArticle.xml",
        category="AI·빅테크",
        category_id=6,
        is_active=True,
    ),
    FeedSource(
        name="MIT Tech Review - AI",
        url="https://www.technologyreview.com/topic/artificial-intelligence/feed",
        category="AI·빅테크",
        category_id=6,
        is_active=True,
    ),
    FeedSource(
        name="GeekNews - AI/개발",
        url="https://news.hada.io/rss/news",
        category="AI·빅테크",
        category_id=6,
        is_active=True,
    ),
    FeedSource(
        name="지디넷코리아 - AI/IT",
        url="https://zdnet.co.kr/feed/",
        category="AI·빅테크",
        category_id=6,
        is_active=True,
    ),
    # Cat 7: IT·통신
    FeedSource(
        name="전자신문 - IT·과학",
        url="https://rss.etnews.com/Section901.xml",
        category="IT·통신",
        category_id=7,
        is_active=True,
    ),
    FeedSource(
        name="한국경제 - IT",
        url="https://www.hankyung.com/feed/it",
        category="IT·통신",
        category_id=7,
        is_active=True,
    ),
    FeedSource(
        name="동아일보 - IT의학",
        url="https://rss.donga.com/science.xml",
        category="IT·통신",
        category_id=7,
        is_active=True,
    ),
    FeedSource(
        name="매일경제 - IT",
        url="https://www.mk.co.kr/rss/50300009/",
        category="IT·통신",
        category_id=7,
        is_active=True,
    ),
    # Cat 8: 문화·콘텐츠
    FeedSource(
        name="연합뉴스 - 문화",
        url="https://www.yna.co.kr/rss/culture.xml",
        category="문화·콘텐츠",
        category_id=8,
        is_active=True,
    ),
    FeedSource(
        name="동아일보 - 문화",
        url="https://rss.donga.com/culture.xml",
        category="문화·콘텐츠",
        category_id=8,
        is_active=True,
    ),
    FeedSource(
        name="매일경제 - 문화/연예",
        url="https://www.mk.co.kr/rss/30000023/",
        category="문화·콘텐츠",
        category_id=8,
        is_active=True,
    ),
    FeedSource(
        name="SBS - 연예/문화",
        url="https://news.sbs.co.kr/news/SectionRssFeed.do?sectionId=07",
        category="문화·콘텐츠",
        category_id=8,
        is_active=True,
    ),
    # Cat 9: 스포츠
    FeedSource(
        name="연합뉴스 - 스포츠",
        url="https://www.yna.co.kr/rss/sports.xml",
        category="스포츠",
        category_id=9,
        is_active=True,
    ),
    FeedSource(
        name="동아일보 - 스포츠",
        url="https://rss.donga.com/sports.xml",
        category="스포츠",
        category_id=9,
        is_active=True,
    ),
    FeedSource(
        name="SBS - 스포츠",
        url="https://news.sbs.co.kr/news/SectionRssFeed.do?sectionId=09",
        category="스포츠",
        category_id=9,
        is_active=True,
    ),
    FeedSource(
        name="일간스포츠 - 스포츠",
        url="http://isplus.joins.com/rss/",
        category="스포츠",
        category_id=9,
        is_active=True,
    ),
    # Cat 10: 라이프스타일
    FeedSource(
        name="연합뉴스 - 건강",
        url="https://www.yna.co.kr/rss/health.xml",
        category="라이프스타일",
        category_id=10,
        is_active=True,
    ),
    FeedSource(
        name="한국경제 - 라이프",
        url="https://www.hankyung.com/feed/life",
        category="라이프스타일",
        category_id=10,
        is_active=True,
    ),
    FeedSource(
        name="동아일보 - 라이프",
        url="https://rss.donga.com/lifeinfo.xml",
        category="라이프스타일",
        category_id=10,
        is_active=True,
    ),
    FeedSource(
        name="동아일보 - 건강",
        url="https://rss.donga.com/health.xml",
        category="라이프스타일",
        category_id=10,
        is_active=True,
    ),
]


def clean_feed_url(raw_url: str) -> str:
    """Clean and normalize feed URL by stripping trailing non-URL text or punctuation."""
    if not raw_url:
        return ""
    # Extract standard URL characters (stop before non-ASCII characters or delimiters)
    match = re.search(r"(https?://[a-zA-Z0-9_\-\.\:\/\?\=\&\%\#\+\~]+)", raw_url.strip())
    if not match:
        return raw_url.strip()
    url = match.group(1)
    # Strip any trailing punctuation that might have adhered
    return url.rstrip("|;,.\"'`>")


def resolve_category_name(category: str) -> str:
    """Resolve category name to canonical target category if recognized, else return stripped category."""
    if not category:
        return ""
    cleaned = category.strip()
    lowered = cleaned.lower()
    if lowered in CATEGORY_ALIASES:
        return CATEGORY_ALIASES[lowered]
    for target in TARGET_CATEGORIES:
        if lowered == target.lower():
            return target
        # Check components of compound category (e.g. 경제, 금융)
        parts = [p.lower() for p in target.split("·")]
        if lowered in parts:
            return target
    return cleaned


def infer_category(text: str, url: str = "") -> str:
    """Infer news category from source name, title, and feed URL."""
    combined = f"{text} {url}".strip()

    # Priority 1: AI / BigTech
    if re.search(
        r"(?i)(?:\b(?:ai|a\.i\.|llm|chatgpt|claude|openai|anthropic)\b|인공지능|빅테크|머신러닝|딥러닝)",
        combined,
    ):
        return "AI·빅테크"

    # Priority 2: IT / Telecom
    if re.search(
        r"(?i)(?:\b(?:it|ict|tech)\b|과학|통신|인터넷|모바일|소프트웨어|보안|디지털|스마트폰|반도체|컴퓨터)",
        combined,
    ):
        return "IT·통신"

    # Targeted keyword checks
    rule_mappings: list[tuple[str, list[str]]] = [
        ("정치", ["정치", "청와대", "대통령", "국회", "정당", "대선", "총선", "외교안보", "politic"]),
        ("경제·금융", ["경제", "금융", "증권", "부동산", "재테크", "코스피", "코스닥", "마켓", "머니", "외환", "economy", "finance"]),
        ("산업·기업", ["산업", "기업", "비즈니스", "비즈", "유통", "자동차", "중소기업", "중기", "바이오", "에너지", "industry", "business", "biz"]),
        ("사회", ["사회", "사건", "사고", "법원", "검찰", "경찰", "교육", "노동", "복지", "환경", "society"]),
        ("국제·글로벌", ["국제", "글로벌", "세계", "해외", "지구촌", "world", "global", "international"]),
        ("문화·콘텐츠", ["문화", "연예", "방송", "영화", "공연", "음악", "전시", "도서", "웹툰", "미디어", "엔터", "스타", "culture", "entertainment"]),
        ("스포츠", ["스포츠", "축구", "야구", "농구", "배구", "골프", "올림픽", "월드컵", "sports"]),
        ("라이프스타일", ["라이프", "생활", "건강", "여성", "여행", "레저", "푸드", "패션", "뷰티", "리빙", "의료", "health", "life", "living"]),
    ]

    combined_lower = combined.lower()
    for cat, keywords in rule_mappings:
        for kw in keywords:
            if kw in combined_lower:
                return cat

    return "종합"


def parse_unverified_file(path: str | Path) -> list[FeedSource]:
    """Parse candidate feeds from unverified text file, cleaning URLs, inferring metadata, and deduplicating.

    Args:
        path: Path to the unverified RSS feeds text file (e.g. rss-unverified.txt).

    Returns:
        List of unique FeedSource instances.
    """
    file_path = Path(path)
    if not file_path.exists():
        raise FileNotFoundError(f"Unverified feeds file not found: {file_path}")

    # Read content with resilient encoding fallback
    raw_bytes = file_path.read_bytes()
    try:
        content = raw_bytes.decode("utf-8")
    except UnicodeDecodeError:
        content = raw_bytes.decode("cp949", errors="replace")

    sources: list[FeedSource] = []
    seen_urls: set[str] = set()
    current_outlet = ""

    for line in content.splitlines():
        line = line.strip()
        if not line:
            continue

        url_match = re.search(r"https?://[^\s]+", line)
        if not url_match:
            # Header line indicating outlet or section
            if not line.startswith("올린이:") and not line.startswith("###"):
                # Clean comment symbols or bracket prefixes if present
                clean_header = line.lstrip("#").strip()
                if clean_header:
                    current_outlet = clean_header
            continue

        raw_url = url_match.group(0)
        clean_url = clean_feed_url(raw_url)
        if not clean_url or clean_url in seen_urls:
            continue

        seen_urls.add(clean_url)

        # Extract title and outlet from the text preceding the URL
        text_before_url = line[: url_match.start()].lstrip("#").strip()

        outlet = current_outlet
        feed_title = text_before_url

        # Check for bracketed outlet syntax, e.g., "[경향신문]정치"
        bracket_match = re.search(r"\[([^\]]+)\](.*)", text_before_url)
        if bracket_match:
            outlet = bracket_match.group(1).strip()
            feed_title = bracket_match.group(2).strip()

        if outlet and feed_title:
            full_name = f"{outlet} - {feed_title}"
        elif outlet:
            full_name = outlet
        elif feed_title:
            full_name = feed_title
        else:
            # Fallback to domain name
            parsed = urllib.parse.urlparse(clean_url)
            full_name = parsed.netloc or clean_url

        # Infer category from combined name and URL
        category = infer_category(f"{outlet} {feed_title}", clean_url)

        sources.append(
            FeedSource(
                name=full_name,
                url=clean_url,
                category=category,
                is_active=True,
            )
        )

    return sources


def validate_feed(url: str, timeout: float = 3.0) -> bool:
    """Validate HTTP accessibility and feed XML structure of a target feed URL.

    Args:
        url: URL of the RSS/Atom feed to validate.
        timeout: HTTP request timeout in seconds.

    Returns:
        True if the feed responded with HTTP 200 and valid RSS/Atom markers; False otherwise.
    """
    if not url or not (url.startswith("http://") or url.startswith("https://")):
        return False

    target_url = url.strip()
    req = urllib.request.Request(
        target_url,
        headers={
            "User-Agent": DEFAULT_USER_AGENT,
            "Accept": "application/rss+xml, application/atom+xml, application/xml, text/xml, */*",
        },
    )

    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            status = getattr(response, "status", None) or response.getcode()
            if status not in (200, 301, 302, 304, 307, 308):
                return False

            sample = response.read(4096)
            if not sample:
                return False

            lower_sample = sample.lower()
            # Must contain RSS/Atom or RDF XML indicator markers
            has_feed_marker = any(
                marker in lower_sample
                for marker in (b"<rss", b"<feed", b"<rdf:rdf", b"<channel")
            )
            return has_feed_marker
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, OSError) as exc:
        logger.debug("Validation failed for %s: %s", target_url, exc)
        return False
    except Exception as exc:
        logger.debug("Unexpected validation error for %s: %s", target_url, exc)
        return False


def probe_feeds(
    sources: list[FeedSource],
    max_workers: int = 10,
    timeout: float = 3.0,
) -> list[FeedSource]:
    """Concurrently probe feed sources to verify whether their endpoints are responsive and valid feeds.

    Args:
        sources: List of FeedSource instances to test.
        max_workers: Maximum number of concurrent probe worker threads.
        timeout: Timeout in seconds for each feed probe.

    Returns:
        List of FeedSource instances with `is_active` set to True or False.
    """
    if not sources:
        return []

    probed_sources = [
        FeedSource(name=s.name, url=s.url, category=s.category, is_active=s.is_active)
        for s in sources
    ]

    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_source = {
            executor.submit(validate_feed, s.url, timeout=timeout): s
            for s in probed_sources
        }
        for future in concurrent.futures.as_completed(future_to_source):
            src = future_to_source[future]
            try:
                src.is_active = future.result()
            except Exception:
                src.is_active = False

    return probed_sources


def filter_sources_by_categories(
    sources: list[FeedSource],
    interested_categories: list[str],
    active_only: bool = False,
) -> list[FeedSource]:
    """Filter feed sources matching interested categories.

    Args:
        sources: List of FeedSource candidates.
        interested_categories: List of category names or aliases (e.g. ['정치', 'AI']).
        active_only: If True, only include sources where is_active is True.

    Returns:
        Filtered list of FeedSource instances.
    """
    if not sources:
        return []

    if not interested_categories:
        if active_only:
            return [s for s in sources if s.is_active]
        return list(sources)

    # Normalize interested categories into canonical categories set
    canonical_interested: set[str] = set()
    for cat in interested_categories:
        if not cat:
            continue
        resolved = resolve_category_name(cat)
        canonical_interested.add(resolved.lower())
        canonical_interested.add(cat.strip().lower())

    filtered: list[FeedSource] = []
    for source in sources:
        if active_only and not source.is_active:
            continue

        source_cat = (source.category or "").strip().lower()
        resolved_source_cat = resolve_category_name(source.category).lower()

        # Check direct or canonical match
        if (
            source_cat in canonical_interested
            or resolved_source_cat in canonical_interested
        ):
            filtered.append(source)

    return filtered


DEFAULT_FEEDS_PATH = Path("data/feeds.json")


def save_verified_feeds(sources: list[FeedSource], path: str | Path) -> None:
    """Save verified feed sources catalog to a JSON file.

    Args:
        sources: List of FeedSource instances to store.
        path: Target file path.
    """
    file_path = Path(path)
    file_path.parent.mkdir(parents=True, exist_ok=True)

    data = {"feeds": [source.to_dict() for source in sources]}

    # Atomic write pattern using PID-tagged temporary file
    temp_file = file_path.with_suffix(f".tmp.{os.getpid()}")
    try:
        with open(temp_file, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        temp_file.replace(file_path)
    except Exception:
        if temp_file.exists():
            temp_file.unlink(missing_ok=True)
        raise


def load_verified_feeds(path: str | Path) -> list[FeedSource]:
    """Load verified feed sources catalog from a JSON file.

    Supports both raw array format `[{...}]` and wrapped object format `{"feeds": [...]}`.

    Args:
        path: Path to the JSON catalog file.

    Returns:
        List of loaded FeedSource instances.
    """
    file_path = Path(path)
    if not file_path.exists():
        raise FileNotFoundError(f"Verified feeds file not found: {file_path}")

    with open(file_path, "r", encoding="utf-8") as f:
        raw_data = json.load(f)

    if isinstance(raw_data, dict):
        if "feeds" in raw_data:
            feed_items = raw_data["feeds"]
        elif "sources" in raw_data:
            feed_items = raw_data["sources"]
        else:
            raise ValueError(
                "Invalid verified feeds catalog format: dictionary must contain 'feeds' or 'sources' list"
            )
    elif isinstance(raw_data, list):
        feed_items = raw_data
    else:
        raise ValueError(
            f"Invalid verified feeds catalog format: expected list or dict, got {type(raw_data).__name__}"
        )

    if not isinstance(feed_items, list):
        raise ValueError(
            f"Invalid verified feeds catalog format: expected list inside feeds/sources, got {type(feed_items).__name__}"
        )

    return [
        FeedSource(
            name=item.get("name", ""),
            url=item.get("url", ""),
            category=item.get("category", ""),
            category_id=item.get("categoryId") or item.get("category_id"),
            is_active=item.get("is_active", True),
        )
        for item in feed_items
        if isinstance(item, dict)
    ]


def load_feed_sources(path: str | Path = DEFAULT_FEEDS_PATH) -> list[FeedSource]:
    """Load feed sources from JSON configuration file with safe fallback.

    Args:
        path: Path to feed configuration JSON. Defaults to data/feeds.json.

    Returns:
        List of FeedSource objects.
    """
    p = Path(path)
    if p.exists():
        try:
            return load_verified_feeds(p)
        except Exception as e:
            logger.warning("Failed to load feed sources from %s: %s. Using default fallback.", p, e)
    return list(DEFAULT_FALLBACK_FEEDS)

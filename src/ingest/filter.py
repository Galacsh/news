"""Article filtering, deduplication, recency verification, and category quota management."""

from __future__ import annotations

import difflib
import logging
import re
import urllib.parse
from datetime import datetime, timezone
from typing import Any

from src.ingest.models import Article
from src.ingest.sources import TARGET_CATEGORIES, resolve_category_name

logger = logging.getLogger(__name__)

# Query parameters commonly used for tracking and analytics
TRACKING_QUERY_PARAMS: set[str] = {
    "utm_source",
    "utm_medium",
    "utm_campaign",
    "utm_term",
    "utm_content",
    "ref",
    "feed",
    "rss",
    "fbclid",
    "gclid",
    "ns_source",
    "ns_mchannel",
}


def parse_iso_datetime(dt_str: str | None) -> datetime | None:
    """Parse an ISO 8601 string into an aware UTC datetime object."""
    if not dt_str or not isinstance(dt_str, str):
        return None
    try:
        normalized = dt_str.strip().replace("Z", "+00:00")
        dt = datetime.fromisoformat(normalized)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        return None


def normalize_article_url(url: str | None) -> str:
    """Normalize article URL by stripping tracking parameters, lowercase domain, and trailing slashes."""
    if not url:
        return ""
    try:
        parsed = urllib.parse.urlparse(url.strip())
        if not parsed.scheme or not parsed.netloc:
            return url.strip()

        scheme = parsed.scheme.lower()
        netloc = parsed.netloc.lower()
        path = parsed.path.rstrip("/")

        # Filter out tracking query parameters
        query_pairs = urllib.parse.parse_qsl(parsed.query, keep_blank_values=True)
        filtered_queries = [
            (k, v) for k, v in query_pairs if k.lower() not in TRACKING_QUERY_PARAMS
        ]
        new_query = urllib.parse.urlencode(filtered_queries)

        return urllib.parse.urlunparse((scheme, netloc, path, "", new_query, ""))
    except Exception:
        return url.strip()


def normalize_title(title: str | None) -> str:
    """Normalize article title by stripping prefix tags, media suffixes, and non-alphanumeric punctuation."""
    if not title:
        return ""
    # Strip leading prefix tags like [속보], [단독], (속보), (단독), [포토]
    text = re.sub(r"^[\[\(][^\]\)]+[\]\)]\s*", "", title)
    # Strip trailing media credits like "- 연합뉴스", "| 매일경제", "- 한국경제"
    text = re.sub(r"\s*[-|–]\s*[^ -|–]+$", "", text)
    # Replace punctuation characters with spaces while preserving Korean, English, digits
    text = re.sub(r"[^\w\s가-힣]", " ", text)
    # Collapse multiple whitespace characters into single space
    return re.sub(r"\s+", " ", text).strip().lower()


def _normalize_outlet_brand(outlet: str | None) -> str:
    """Normalize outlet name into a canonical brand name (lowercase, stripped of sub-category suffix)."""
    if not outlet:
        return ""
    clean = outlet.strip().lower()
    if " - " in clean:
        clean = clean.split(" - ")[0].strip()
    return clean


def is_same_outlet_or_feed(art1: Article, art2: Article) -> bool:
    """Determine whether two articles originate from the same outlet or identical feed."""
    outlet1 = _normalize_outlet_brand(art1.outlet)
    outlet2 = _normalize_outlet_brand(art2.outlet)

    # Identical non-empty outlet brand (e.g. '연합뉴스')
    if outlet1 and outlet2:
        return outlet1 == outlet2

    # Check feed URL or feed name in raw_data if available
    feed1 = str(
        (art1.raw_data or {}).get("feed")
        or (art1.raw_data or {}).get("feed_url")
        or (art1.raw_data or {}).get("feed_name")
        or ""
    ).strip().lower()
    feed2 = str(
        (art2.raw_data or {}).get("feed")
        or (art2.raw_data or {}).get("feed_url")
        or (art2.raw_data or {}).get("feed_name")
        or ""
    ).strip().lower()
    if feed1 and feed2:
        return feed1 == feed2

    # If neither article has outlet or feed metadata, treat as same source
    if not outlet1 and not outlet2 and not feed1 and not feed2:
        return True

    return False


def deduplicate_articles(
    articles: list[Article],
    title_similarity_threshold: float = 0.8,
) -> list[Article]:
    """Prune duplicate articles by canonical URL, unique ID, and same-outlet title similarity.

    Identical IDs and normalized URLs are pruned across all outlets.
    Title similarity pruning only applies if articles originate from the same outlet or identical feed,
    preserving cross-outlet coverage of the same event for downstream consensus clustering.

    Args:
        articles: List of Article objects.
        title_similarity_threshold: Float between 0.0 and 1.0 indicating threshold for title deduplication.

    Returns:
        List of deduplicated Article objects preserving order.
    """
    if not articles:
        return []

    accepted_articles: list[Article] = []
    seen_ids: set[str] = set()
    seen_urls: set[str] = set()
    accepted_records: list[tuple[str, Article]] = []

    for article in articles:
        # 1. Deduplicate by unique Article ID
        if article.id and article.id in seen_ids:
            logger.debug("Article id %s pruned as duplicate ID", article.id)
            continue

        # 2. Deduplicate by normalized URL
        clean_url = normalize_article_url(article.url)
        if clean_url and clean_url in seen_urls:
            logger.debug("Article url %s pruned as duplicate URL", article.url)
            continue

        # 3. Deduplicate by title similarity (only within same outlet or identical feed)
        norm_title = normalize_title(article.title)
        is_title_duplicate = False

        if norm_title:
            len_curr = len(norm_title)
            for prev_title, prev_article in accepted_records:
                if not is_same_outlet_or_feed(article, prev_article):
                    continue

                len_prev = len(prev_title)
                # Quick upper bound test for SequenceMatcher ratio:
                # ratio <= (2 * min(lenA, lenB)) / (lenA + lenB)
                upper_bound = (2.0 * min(len_curr, len_prev)) / (len_curr + len_prev)
                if upper_bound < title_similarity_threshold:
                    continue

                similarity = difflib.SequenceMatcher(None, norm_title, prev_title).ratio()
                if similarity >= title_similarity_threshold:
                    is_title_duplicate = True
                    logger.debug(
                        "Article '%s' pruned due to same-outlet title similarity (%0.2f) with '%s'",
                        article.title,
                        similarity,
                        prev_title,
                    )
                    break

        if is_title_duplicate:
            continue

        # Article is unique; accept and register
        if article.id:
            seen_ids.add(article.id)
        if clean_url:
            seen_urls.add(clean_url)
        if norm_title:
            accepted_records.append((norm_title, article))

        accepted_articles.append(article)

    return accepted_articles


KOREAN_PARTICLES: tuple[str, ...] = (
    "했다고",
    "했다는",
    "있다고",
    "있다는",
    "된다고",
    "한다는",
    "한다고",
    "하기로",
    "하며",
    "하고",
    "하고는",
    "하게",
    "하지",
    "했다",
    "한다",
    "된다",
    "됐다",
    "되는",
    "하여",
    "에서",
    "으로",
    "에게",
    "부터",
    "까지",
    "에는",
    "에도",
    "이란",
    "처럼",
    "은",
    "는",
    "이",
    "가",
    "을",
    "를",
    "의",
    "에",
    "로",
    "와",
    "과",
    "도",
    "만",
)

TOPIC_STOPWORDS: set[str] = {
    "기자",
    "뉴스",
    "오늘",
    "어제",
    "지난",
    "밝혔다",
    "말했다",
    "전했다",
    "따르면",
    "대해",
    "대한",
    "통해",
    "위해",
    "위한",
    "관련",
    "것으로",
    "있는",
    "있다",
    "했다",
    "등의",
    "이를",
    "이번",
    "이에",
    "라며",
    "하는",
    "된다",
    "됐다",
    "사진",
    "단독",
    "속보",
    "이달",
    "오는",
}


def extract_topic_keywords(text: str) -> set[str]:
    """Tokenize text into keywords (Hangul words/nouns, numbers, alphanumeric)."""
    if not text:
        return set()

    clean = re.sub(r"<[^>]+>", " ", text)
    clean = re.sub(r"^[\[\(][^\]\)]+[\]\)]\s*", "", clean)

    raw_tokens = re.findall(r"[가-힣a-zA-Z0-9]+", clean.lower())
    keywords: set[str] = set()

    for token in raw_tokens:
        if token in TOPIC_STOPWORDS:
            continue

        stripped = token
        for p in KOREAN_PARTICLES:
            if len(token) > len(p) + 1 and token.endswith(p):
                stripped = token[: -len(p)]
                break

        if stripped in TOPIC_STOPWORDS:
            continue

        if len(stripped) >= 2 or stripped.isdigit():
            keywords.add(stripped)

    return keywords


def calculate_jaccard_similarity(set_a: set[str], set_b: set[str]) -> float:
    """Compute token Jaccard similarity between two keyword sets."""
    if not set_a or not set_b:
        return 0.0
    intersection = len(set_a & set_b)
    if not intersection:
        return 0.0
    union = len(set_a | set_b)
    return intersection / union if union > 0 else 0.0


def format_related_title(title: str, outlet: str | None) -> str:
    """Format related link title ensuring outlet prefix is included if not already present."""
    clean_title = (title or "").strip()
    if not clean_title:
        return ""
    if not outlet or not outlet.strip():
        return clean_title

    outlet_str = outlet.strip()
    brand = outlet_str.split(" - ")[0].strip() if " - " in outlet_str else outlet_str
    if not brand:
        return clean_title

    if (
        clean_title.startswith(f"[{brand}]")
        or clean_title.startswith(f"({brand})")
        or clean_title.startswith(f"[{outlet_str}]")
        or clean_title.startswith(f"({outlet_str})")
        or clean_title.startswith(f"{brand}:")
        or clean_title.startswith(f"{brand} -")
    ):
        return clean_title

    return f"[{brand}] {clean_title}"


def are_articles_same_topic(
    art_a: Article,
    art_b: Article,
    tokens_a: set[str],
    tokens_b: set[str],
    similarity_threshold: float = 0.20,
) -> bool:
    """Check if two articles cover the same topic with category isolation and multi-token consensus rules."""
    # Category isolation: if both categories are defined and different, reject immediately
    cat_a = getattr(art_a, "category", None) or ""
    cat_b = getattr(art_b, "category", None) or ""
    if cat_a and cat_b and cat_a != cat_b:
        return False

    # Common tokens
    common = tokens_a & tokens_b

    # Single-token rule: NEVER match on < 2 common tokens (prevents chain-reaction percolation)
    if len(common) < 2:
        return False

    # Rule 1 (Jaccard): title token Jaccard similarity >= 0.35
    jaccard_sim = calculate_jaccard_similarity(tokens_a, tokens_b)
    if jaccard_sim >= 0.35:
        return True

    # Rule 2 (Overlap ratio): overlap ratio >= 0.40 with min_len >= 3 and len(common) >= 2
    min_len = min(len(tokens_a), len(tokens_b))
    if min_len >= 3 and len(common) >= 2 and (len(common) / min_len) >= 0.40:
        return True

    # Rule 3 (SequenceMatcher): normalized title string similarity >= 0.60
    norm_a = normalize_title(art_a.title)
    norm_b = normalize_title(art_b.title)
    if norm_a and norm_b:
        seq_sim = difflib.SequenceMatcher(None, norm_a, norm_b).ratio()
        if seq_sim >= 0.60:
            return True

    return False


def cluster_articles_by_topic(
    articles: list[Article],
    similarity_threshold: float = 0.20,
    reference_time: datetime | None = None,
) -> list[Article]:
    """Cluster articles covering the same topic across outlets and rank by consensus.

    1. Tokenize titles (and fallback to summary if title has no tokens) into keywords.
    2. Group articles covering the same topic via common keywords, token Jaccard, overlap ratio, or SequenceMatcher.
    3. For each cluster, pick the best representative (longest title/summary, newest).
    4. Attach all other articles in the cluster as related_links:
       [{"title": f"[{outlet}] {a.title}", "url": a.url}, ...] to the representative.
    5. Rank clusters by Consensus Score: `(distinct_outlets_count * 10) + recency_score`
       so stories covered by multiple independent outlets rank higher than single-outlet stories.

    Args:
        articles: List of Article instances to cluster.
        similarity_threshold: Jaccard similarity threshold for clustering (default: 0.20).
        reference_time: Optional reference datetime for recency scoring.

    Returns:
        List of cluster representative Article instances ranked by Consensus Score descending.
    """
    if not articles:
        return []

    if len(articles) == 1:
        rep = articles[0]
        if rep.raw_data is None:
            rep.raw_data = {}
        rep.raw_data["consensus_score"] = 10.0 + 1.0
        rep.raw_data["distinct_outlets_count"] = 1
        rep.raw_data["cluster_size"] = 1
        return [rep]

    article_tokens = [
        extract_topic_keywords(a.title) or extract_topic_keywords(a.summary)
        for a in articles
    ]

    n = len(articles)
    parent = list(range(n))

    def find(i: int) -> int:
        path = []
        while parent[i] != i:
            path.append(i)
            i = parent[i]
        for node in path:
            parent[node] = i
        return i

    def union(i: int, j: int) -> None:
        root_i = find(i)
        root_j = find(j)
        if root_i != root_j:
            parent[root_j] = root_i

    for i in range(n):
        cat_i = getattr(articles[i], "category", None) or ""
        for j in range(i + 1, n):
            cat_j = getattr(articles[j], "category", None) or ""
            # Category isolation: only compare pairs in identical category or where either is None/empty
            if cat_i and cat_j and cat_i != cat_j:
                continue
            if are_articles_same_topic(
                articles[i],
                articles[j],
                article_tokens[i],
                article_tokens[j],
                similarity_threshold=similarity_threshold,
            ):
                union(i, j)

    clusters: dict[int, list[Article]] = {}
    for i, article in enumerate(articles):
        root = find(i)
        if root not in clusters:
            clusters[root] = []
        clusters[root].append(article)

    parsed_timestamps = [
        (
            parse_iso_datetime(a.published_at)
            or datetime.min.replace(tzinfo=timezone.utc)
        ).timestamp()
        for a in articles
    ]
    min_ts = min(parsed_timestamps) if parsed_timestamps else 0.0
    max_ts = max(parsed_timestamps) if parsed_timestamps else 0.0

    cluster_representatives: list[tuple[float, float, Article]] = []

    for cluster_members in clusters.values():
        def _representative_sort_key(a: Article) -> tuple[int, float]:
            length = len(a.title.strip()) + len((a.summary or "").strip())
            dt = parse_iso_datetime(a.published_at) or datetime.min.replace(tzinfo=timezone.utc)
            return (length, dt.timestamp())

        sorted_members = sorted(cluster_members, key=_representative_sort_key, reverse=True)
        rep = sorted_members[0]
        other_members = sorted_members[1:]

        sorted_others = sorted(
            other_members,
            key=lambda a: parse_iso_datetime(a.published_at)
            or datetime.min.replace(tzinfo=timezone.utc),
            reverse=True,
        )
        seen_urls = {rep.url}
        seen_outlets: set[str] = set()
        rep_brand = _normalize_outlet_brand(rep.outlet)
        if rep_brand:
            seen_outlets.add(rep_brand)

        related_links: list[dict[str, str]] = []
        for other in sorted_others:
            if not other.url or other.url in seen_urls:
                continue
            other_brand = _normalize_outlet_brand(other.outlet)
            if other_brand and other_brand in seen_outlets:
                continue
            if other_brand:
                seen_outlets.add(other_brand)
            seen_urls.add(other.url)
            link_title = format_related_title(other.title, other.outlet)
            related_links.append({"title": link_title, "url": other.url})
            if len(related_links) >= 4:
                break
        rep.related_links = related_links[:4]

        outlets = {
            _normalize_outlet_brand(m.outlet)
            for m in cluster_members
            if _normalize_outlet_brand(m.outlet)
        }
        distinct_outlets_count = max(1, len(outlets))

        member_dts = [
            parse_iso_datetime(m.published_at) or datetime.min.replace(tzinfo=timezone.utc)
            for m in cluster_members
        ]
        cluster_newest_dt = (
            max(member_dts) if member_dts else datetime.min.replace(tzinfo=timezone.utc)
        )
        cluster_ts = cluster_newest_dt.timestamp()

        if max_ts > min_ts:
            recency_score = (cluster_ts - min_ts) / (max_ts - min_ts)
        else:
            recency_score = 1.0

        consensus_score = (distinct_outlets_count * 10.0) + recency_score

        if rep.raw_data is None:
            rep.raw_data = {}
        rep.raw_data["consensus_score"] = consensus_score
        rep.raw_data["distinct_outlets_count"] = distinct_outlets_count
        rep.raw_data["cluster_size"] = len(cluster_members)

        cluster_representatives.append((consensus_score, cluster_ts, rep))

    cluster_representatives.sort(key=lambda item: (item[0], item[1]), reverse=True)

    return [item[2] for item in cluster_representatives]


def filter_by_recency(
    articles: list[Article],
    max_hours: float = 24.0,
    reference_time: datetime | None = None,
) -> list[Article]:
    """Filter out articles older than max_hours relative to reference_time.

    Args:
        articles: List of Article instances.
        max_hours: Maximum allowable article age in hours.
        reference_time: Reference datetime for age calculation (defaults to current UTC time).

    Returns:
        List of Article instances within the recency window.
    """
    if not articles:
        return []

    if reference_time is None:
        ref_dt = datetime.now(timezone.utc)
    else:
        if reference_time.tzinfo is None:
            ref_dt = reference_time.replace(tzinfo=timezone.utc)
        else:
            ref_dt = reference_time.astimezone(timezone.utc)

    max_seconds = max_hours * 3600.0
    # Allow small clock drift for articles with timestamps up to 2 hours into the future
    future_tolerance_seconds = 7200.0

    filtered: list[Article] = []
    for article in articles:
        pub_dt = parse_iso_datetime(article.published_at)
        if pub_dt is None:
            logger.warning(
                "Article %s has invalid published_at '%s', filtering out",
                article.id,
                article.published_at,
            )
            continue

        delta_seconds = (ref_dt - pub_dt).total_seconds()
        # Check that article is neither too old nor excessively in the future
        if -future_tolerance_seconds <= delta_seconds <= max_seconds:
            filtered.append(article)
        else:
            logger.debug(
                "Article %s excluded by recency filter (age: %.1f hours)",
                article.id,
                delta_seconds / 3600.0,
            )

    return filtered


def group_and_trim_by_category(
    articles: list[Article],
    categories: list[str],
    max_per_category: int = 8,
) -> dict[str, list[Article]]:
    """Group articles by specified categories, sort descending by published_at, and trim to max_per_category.

    Args:
        articles: List of Article instances.
        categories: Ordered list of categories to retain.
        max_per_category: Maximum number of articles per category.

    Returns:
        Dictionary mapping category names to trimmed lists of Article instances.
    """
    if not categories:
        # Group dynamically by article.category if no categories specified
        grouped_dynamic: dict[str, list[Article]] = {}
        for a in articles:
            cat = a.category or "기타"
            if cat not in grouped_dynamic:
                grouped_dynamic[cat] = []
            grouped_dynamic[cat].append(a)

        result_dynamic: dict[str, list[Article]] = {}
        for cat, items in grouped_dynamic.items():
            sorted_items = sorted(
                items,
                key=lambda art: (
                    (art.raw_data or {}).get("consensus_score", 0.0),
                    parse_iso_datetime(art.published_at)
                    or datetime.min.replace(tzinfo=timezone.utc),
                ),
                reverse=True,
            )
            result_dynamic[cat] = sorted_items[:max_per_category]
        return result_dynamic

    # Initialize dictionary maintaining category order
    grouped: dict[str, list[Article]] = {cat: [] for cat in categories}

    # Build category resolution lookup table
    lookup: dict[str, str] = {}
    for cat in categories:
        lookup[cat.strip().lower()] = cat
        canonical = resolve_category_name(cat)
        lookup[canonical.lower()] = cat
        parts = [p.strip().lower() for p in cat.split("·")]
        for p in parts:
            if p and p not in lookup:
                lookup[p] = cat

    for article in articles:
        art_cat = (article.category or "").strip()
        matched_target_cat: str | None = None

        if art_cat.lower() in lookup:
            matched_target_cat = lookup[art_cat.lower()]
        else:
            canonical_art = resolve_category_name(art_cat).lower()
            if canonical_art in lookup:
                matched_target_cat = lookup[canonical_art]
            else:
                for p in art_cat.split("·"):
                    p_clean = p.strip().lower()
                    if p_clean in lookup:
                        matched_target_cat = lookup[p_clean]
                        break

        if matched_target_cat and matched_target_cat in grouped:
            grouped[matched_target_cat].append(article)

    # Sort each category by consensus_score then published_at descending and trim
    trimmed: dict[str, list[Article]] = {}
    for cat, items in grouped.items():
        sorted_items = sorted(
            items,
            key=lambda art: (
                (art.raw_data or {}).get("consensus_score", 0.0),
                parse_iso_datetime(art.published_at)
                or datetime.min.replace(tzinfo=timezone.utc),
            ),
            reverse=True,
        )
        trimmed[cat] = sorted_items[:max_per_category]

    return trimmed


def apply_adaptive_lookback(
    articles: list[Article],
    categories: list[str],
    min_per_category: int = 2,
    max_hours: float = 24.0,
    max_lookback_hours: float = 72.0,
    reference_time: datetime | None = None,
    max_per_category: int = 8,
    title_similarity_threshold: float = 0.8,
    cluster_similarity_threshold: float = 0.20,
    enable_clustering: bool = True,
) -> dict[str, list[Article]]:
    """Filter articles with adaptive category lookback fallback.

    For categories that do not meet `min_per_category` within the primary `max_hours` window,
    this function looks back up to `max_lookback_hours` to backfill missing articles.

    Args:
        articles: Raw or pre-filtered Article list.
        categories: Target categories to include.
        min_per_category: Minimum desired articles per category before lookback activates.
        max_hours: Primary recency window in hours (e.g. 24.0).
        max_lookback_hours: Extended recency lookback window in hours (e.g. 72.0).
        reference_time: Reference datetime for recency calculation.
        max_per_category: Maximum number of articles per category.
        title_similarity_threshold: Threshold ratio for title deduplication.
        cluster_similarity_threshold: Jaccard similarity threshold for topic clustering.
        enable_clustering: Whether to run cross-outlet consensus clustering.

    Returns:
        Dictionary mapping category names to lists of unique, trimmed Article instances.
    """
    if not articles:
        return {cat: [] for cat in categories} if categories else {}

    # Sort articles newest first before deduplication so newer items are preferred
    sorted_articles = sorted(
        articles,
        key=lambda art: parse_iso_datetime(art.published_at)
        or datetime.min.replace(tzinfo=timezone.utc),
        reverse=True,
    )

    # Step 1: Deduplicate all articles across URLs, IDs, and title similarity
    deduped_articles = deduplicate_articles(
        sorted_articles,
        title_similarity_threshold=title_similarity_threshold,
    )

    # Step 1.5: Cross-outlet consensus clustering
    if enable_clustering:
        processed_articles = cluster_articles_by_topic(
            deduped_articles,
            similarity_threshold=cluster_similarity_threshold,
            reference_time=reference_time,
        )
    else:
        processed_articles = deduped_articles

    # Step 2: Primary recency filtering and category grouping
    recent_articles = filter_by_recency(
        processed_articles,
        max_hours=max_hours,
        reference_time=reference_time,
    )
    grouped = group_and_trim_by_category(
        recent_articles,
        categories=categories,
        max_per_category=max_per_category,
    )

    # Step 3: Adaptive lookback for deficient categories
    target_quota = min(min_per_category, max_per_category)
    deficient_categories = [
        cat for cat in categories if len(grouped.get(cat, [])) < target_quota
    ]

    if deficient_categories:
        effective_lookback = max(max_lookback_hours, max_hours)
        extended_articles = filter_by_recency(
            processed_articles,
            max_hours=effective_lookback,
            reference_time=reference_time,
        )
        extended_grouped = group_and_trim_by_category(
            extended_articles,
            categories=deficient_categories,
            max_per_category=max(max_per_category, min_per_category, len(extended_articles)),
        )

        for cat in deficient_categories:
            cat_articles = list(grouped.get(cat, []))
            existing_ids = {a.id for a in cat_articles if a.id}
            existing_urls = {normalize_article_url(a.url) for a in cat_articles if a.url}

            for candidate in extended_grouped.get(cat, []):
                if len(cat_articles) >= target_quota:
                    break
                cand_url = normalize_article_url(candidate.url)
                if candidate.id and candidate.id in existing_ids:
                    continue
                if cand_url and cand_url in existing_urls:
                    continue
                cat_articles.append(candidate)
                if candidate.id:
                    existing_ids.add(candidate.id)
                if cand_url:
                    existing_urls.add(cand_url)

            # Sort descending by consensus score then published_at
            grouped[cat] = sorted(
                cat_articles,
                key=lambda art: (
                    (art.raw_data or {}).get("consensus_score", 0.0),
                    parse_iso_datetime(art.published_at)
                    or datetime.min.replace(tzinfo=timezone.utc),
                ),
                reverse=True,
            )

    return grouped


class ArticleFilterPipeline:
    """Pipeline combining deduplication, consensus clustering, recency filtering, category grouping, and quota trimming."""

    def __init__(
        self,
        categories: list[str] | None = None,
        max_hours: float = 24.0,
        max_per_category: int = 8,
        title_similarity_threshold: float = 0.8,
        reference_time: datetime | None = None,
        min_per_category: int = 0,
        adaptive_lookback: bool = False,
        max_lookback_hours: float = 72.0,
        cluster_similarity_threshold: float = 0.20,
        enable_clustering: bool = True,
    ) -> None:
        """Initialize the filtering pipeline.

        Args:
            categories: List of categories to include. If None, all detected categories are retained.
            max_hours: Maximum allowable article age in hours.
            max_per_category: Maximum number of articles per category.
            title_similarity_threshold: Threshold ratio for title deduplication.
            reference_time: Reference datetime for recency calculation.
            min_per_category: Minimum number of articles per category before lookback triggers.
            adaptive_lookback: Whether to enable adaptive lookback fallback.
            max_lookback_hours: Extended recency lookback window in hours.
            cluster_similarity_threshold: Jaccard similarity threshold for topic clustering.
            enable_clustering: Whether to run cross-outlet consensus clustering.
        """
        self.categories = list(categories) if categories is not None else None
        self.max_hours = max_hours
        self.max_per_category = max_per_category
        self.title_similarity_threshold = title_similarity_threshold
        self.reference_time = reference_time
        self.min_per_category = min_per_category
        self.adaptive_lookback = adaptive_lookback
        self.max_lookback_hours = max_lookback_hours
        self.cluster_similarity_threshold = cluster_similarity_threshold
        self.enable_clustering = enable_clustering

    def process(self, articles: list[Article]) -> dict[str, list[Article]]:
        """Run the end-to-end filtering pipeline.

        Args:
            articles: Raw list of ingested Article instances.

        Returns:
            Dictionary mapping category names to lists of normalized, unique, and trimmed Article instances.
        """
        if not articles:
            if self.categories:
                return {cat: [] for cat in self.categories}
            return {}

        if not (self.adaptive_lookback or self.min_per_category > 0):
            # Step 1: Filter out old or invalid date articles
            recent_articles = filter_by_recency(
                articles,
                max_hours=self.max_hours,
                reference_time=self.reference_time,
            )

            # Step 2: Deduplicate articles by URL and title similarity
            deduped_articles = deduplicate_articles(
                recent_articles,
                title_similarity_threshold=self.title_similarity_threshold,
            )

            # Step 3: Cluster articles by topic and rank by consensus
            if self.enable_clustering:
                processed_articles = cluster_articles_by_topic(
                    deduped_articles,
                    similarity_threshold=self.cluster_similarity_threshold,
                    reference_time=self.reference_time,
                )
            else:
                processed_articles = deduped_articles

            # Step 4: Group by category and trim to max quota
            target_categories = self.categories
            if target_categories is None:
                # Preserve order of appearance across unique categories
                seen_cats: set[str] = set()
                target_categories = []
                for art in processed_articles:
                    cat = art.category or "종합"
                    if cat not in seen_cats:
                        seen_cats.add(cat)
                        target_categories.append(cat)

            return group_and_trim_by_category(
                processed_articles,
                categories=target_categories,
                max_per_category=self.max_per_category,
            )

        # Adaptive category lookback enabled
        target_categories = self.categories
        if target_categories is None:
            seen_cats = set()
            target_categories = []
            for art in articles:
                cat = art.category or "종합"
                if cat not in seen_cats:
                    seen_cats.add(cat)
                    target_categories.append(cat)

        effective_min = self.min_per_category if self.min_per_category > 0 else 2
        return apply_adaptive_lookback(
            articles=articles,
            categories=target_categories,
            min_per_category=effective_min,
            max_hours=self.max_hours,
            max_lookback_hours=self.max_lookback_hours,
            reference_time=self.reference_time,
            max_per_category=self.max_per_category,
            title_similarity_threshold=self.title_similarity_threshold,
            cluster_similarity_threshold=self.cluster_similarity_threshold,
            enable_clustering=self.enable_clustering,
        )

    def process_flat(self, articles: list[Article]) -> list[Article]:
        """Run the filtering pipeline and return a flattened list sorted by consensus score and recency.

        Args:
            articles: Raw list of ingested Article instances.

        Returns:
            Flattened list of accepted Article instances sorted by consensus score and recency.
        """
        grouped = self.process(articles)
        flat_list: list[Article] = []
        for cat_articles in grouped.values():
            flat_list.extend(cat_articles)

        return sorted(
            flat_list,
            key=lambda art: (
                (art.raw_data or {}).get("consensus_score", 0.0),
                parse_iso_datetime(art.published_at)
                or datetime.min.replace(tzinfo=timezone.utc),
            ),
            reverse=True,
        )

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


def deduplicate_articles(
    articles: list[Article],
    title_similarity_threshold: float = 0.8,
) -> list[Article]:
    """Prune duplicate articles by canonical URL, unique ID, and title similarity.

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
    accepted_norm_titles: list[str] = []

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

        # 3. Deduplicate by title similarity
        norm_title = normalize_title(article.title)
        is_title_duplicate = False

        if norm_title:
            len_curr = len(norm_title)
            for prev_title in accepted_norm_titles:
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
                        "Article '%s' pruned due to title similarity (%0.2f) with '%s'",
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
            accepted_norm_titles.append(norm_title)

        accepted_articles.append(article)

    return accepted_articles


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
    max_per_category: int = 5,
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
                key=lambda art: parse_iso_datetime(art.published_at)
                or datetime.min.replace(tzinfo=timezone.utc),
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

    # Sort each category by published_at descending and trim
    trimmed: dict[str, list[Article]] = {}
    for cat, items in grouped.items():
        sorted_items = sorted(
            items,
            key=lambda art: parse_iso_datetime(art.published_at)
            or datetime.min.replace(tzinfo=timezone.utc),
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
    max_per_category: int = 5,
    title_similarity_threshold: float = 0.8,
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

    # Step 2: Primary recency filtering and category grouping
    recent_articles = filter_by_recency(
        deduped_articles,
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
            deduped_articles,
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

            # Sort descending by published_at
            grouped[cat] = sorted(
                cat_articles,
                key=lambda art: parse_iso_datetime(art.published_at)
                or datetime.min.replace(tzinfo=timezone.utc),
                reverse=True,
            )

    return grouped


class ArticleFilterPipeline:
    """Pipeline combining deduplication, recency filtering, category grouping, and quota trimming."""

    def __init__(
        self,
        categories: list[str] | None = None,
        max_hours: float = 24.0,
        max_per_category: int = 5,
        title_similarity_threshold: float = 0.8,
        reference_time: datetime | None = None,
        min_per_category: int = 0,
        adaptive_lookback: bool = False,
        max_lookback_hours: float = 72.0,
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
        """
        self.categories = list(categories) if categories is not None else None
        self.max_hours = max_hours
        self.max_per_category = max_per_category
        self.title_similarity_threshold = title_similarity_threshold
        self.reference_time = reference_time
        self.min_per_category = min_per_category
        self.adaptive_lookback = adaptive_lookback
        self.max_lookback_hours = max_lookback_hours

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

            # Step 3: Group by category and trim to max quota
            target_categories = self.categories
            if target_categories is None:
                # Preserve order of appearance across unique categories
                seen_cats: set[str] = set()
                target_categories = []
                for art in deduped_articles:
                    cat = art.category or "종합"
                    if cat not in seen_cats:
                        seen_cats.add(cat)
                        target_categories.append(cat)

            return group_and_trim_by_category(
                deduped_articles,
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
        )

    def process_flat(self, articles: list[Article]) -> list[Article]:
        """Run the filtering pipeline and return a flattened list sorted by published_at descending.

        Args:
            articles: Raw list of ingested Article instances.

        Returns:
            Flattened list of accepted Article instances sorted newest first.
        """
        grouped = self.process(articles)
        flat_list: list[Article] = []
        for cat_articles in grouped.values():
            flat_list.extend(cat_articles)

        return sorted(
            flat_list,
            key=lambda art: parse_iso_datetime(art.published_at)
            or datetime.min.replace(tzinfo=timezone.utc),
            reverse=True,
        )

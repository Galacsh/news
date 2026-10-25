"""News ingestion package."""

from src.ingest.filter import (
    ArticleFilterPipeline,
    deduplicate_articles,
    filter_by_recency,
    group_and_trim_by_category,
    normalize_article_url,
    normalize_title,
)
from src.ingest.models import Article, FeedSource
from src.ingest.rss import RSSFeedParser
from src.ingest.sources import (
    DEFAULT_FALLBACK_FEEDS,
    DEFAULT_FEEDS_PATH,
    TARGET_CATEGORIES,
    filter_sources_by_categories,
    load_feed_sources,
    load_verified_feeds,
    parse_unverified_file,
    probe_feeds,
    save_verified_feeds,
    validate_feed,
)

__all__ = [
    "Article",
    "ArticleFilterPipeline",
    "DEFAULT_FALLBACK_FEEDS",
    "DEFAULT_FEEDS_PATH",
    "FeedSource",
    "RSSFeedParser",
    "TARGET_CATEGORIES",
    "deduplicate_articles",
    "filter_by_recency",
    "filter_sources_by_categories",
    "group_and_trim_by_category",
    "load_feed_sources",
    "load_verified_feeds",
    "normalize_article_url",
    "normalize_title",
    "parse_unverified_file",
    "probe_feeds",
    "save_verified_feeds",
    "validate_feed",
]

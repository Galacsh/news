"""Data models for RSS news feed ingestion."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass
class Article:
    """Represents a normalized news article ingested from an RSS/Atom feed."""

    id: str
    title: str
    summary: str
    url: str
    outlet: str
    published_at: str  # ISO 8601 string (e.g. '2026-10-25T08:00:00+00:00')
    category: str = ""
    category_id: int | None = None
    raw_data: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert the Article instance to a standard dictionary."""
        return asdict(self)


@dataclass
class FeedSource:
    """Represents a configured news RSS/Atom feed source."""

    name: str
    url: str
    category: str = ""
    category_id: int | None = None
    is_active: bool = True

    def to_dict(self) -> dict[str, Any]:
        """Convert the FeedSource instance to a standard dictionary."""
        return asdict(self)

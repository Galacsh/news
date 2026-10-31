"""Data models for RSS news feed ingestion."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
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
    related_links: list[dict[str, str]] = field(default_factory=list)
    body: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Convert the Article instance to a standard dictionary without transient body."""
        data = asdict(self)
        data.pop("body", None)
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Article:
        """Create an Article instance from a dictionary representation."""
        return cls(
            id=data.get("id", ""),
            title=data.get("title", ""),
            summary=data.get("summary", ""),
            url=data.get("url", ""),
            outlet=data.get("outlet", ""),
            published_at=data.get("published_at", ""),
            category=data.get("category", ""),
            category_id=data.get("category_id"),
            raw_data=data.get("raw_data"),
            related_links=list(data.get("related_links") or []),
            body=data.get("body", ""),
        )


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

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> FeedSource:
        """Create a FeedSource instance from a dictionary representation."""
        return cls(
            name=data.get("name", ""),
            url=data.get("url", ""),
            category=data.get("category", ""),
            category_id=data.get("category_id"),
            is_active=data.get("is_active", True),
        )

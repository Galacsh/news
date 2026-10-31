"""News summarizer engine synthesizing RSS articles into structured briefings."""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.ingest.models import Article
from src.llm.client import GeminiAPIError, GeminiClient
from src.llm.prompts import (
    BRIEFING_RESPONSE_SCHEMA,
    CATEGORY_LENSES,
    SYSTEM_PROMPT,
    build_briefing_prompt,
    load_default_categories,
)

logger = logging.getLogger(__name__)


def make_default_deep_dive(
    category_id: int,
    headline: str = "",
    summary: str = "",
) -> dict[str, Any]:
    """Generate a category-tailored analytical deepDive adhering to CATEGORY_LENSES."""
    lens = CATEGORY_LENSES.get(category_id, CATEGORY_LENSES[1])
    sections = []
    subject = headline.strip() if headline.strip() else "해당 사안"
    for label in lens["sections"]:
        sections.append({
            "label": label,
            "content": f"{subject} 관련 {label} 관점에서 핵심 사실과 향후 파급 효과를 면밀히 분석하고 있어요.",
        })
    return {
        "lensTitle": lens["lensTitle"],
        "sections": sections,
    }


class NewsSummarizer:
    """Orchestrates news candidate clustering, LLM summarization, and schema formatting."""

    def __init__(
        self,
        client: GeminiClient | None = None,
        categories_path: Path | str | None = None,
        fallback_on_error: bool = True,
    ) -> None:
        """Initialize NewsSummarizer with client, category metadata, and fallback policy.

        Args:
            client: GeminiClient instance. If None, initialized with default configuration.
            categories_path: Path to categories.json file.
            fallback_on_error: If True, extract fallback briefing on GeminiAPIError.
        """
        if client is not None:
            self.client = client
        else:
            api_key = os.environ.get("GEMINI_API_KEY", "").strip()
            self.client = GeminiClient(api_key=api_key) if api_key else GeminiClient(mock_mode=True)
        self.categories: list[dict[str, Any]] = load_default_categories(categories_path)
        self.categories_map: dict[int, dict[str, Any]] = {
            cat["id"]: cat for cat in self.categories
        }
        self.fallback_on_error: bool = fallback_on_error

        # Name / alias to category_id lookup map
        self.name_to_id: dict[str, int] = {}
        for cat in self.categories:
            cid = cat["id"]
            self.name_to_id[cat["name"]] = cid
            for alias in cat.get("aliases", []):
                self.name_to_id[alias] = cid

    def group_articles_by_category(
        self,
        articles: list[Article],
    ) -> dict[int, list[Article]]:
        """Group a flat list of Article objects by category_id."""
        grouped: dict[int, list[Article]] = {}
        for art in articles:
            cid = art.category_id
            if cid is None and art.category:
                cid = self.name_to_id.get(art.category)
            if cid is None:
                cid = 1  # Default to category 1 (정치) if unresolvable

            if cid not in grouped:
                grouped[cid] = []
            grouped[cid].append(art)

        return grouped

    def summarize_articles(
        self,
        articles: list[Article] | dict[int, list[Article]],
        briefing_date: str | datetime | None = None,
        batch_size: int = 3,
    ) -> dict[str, Any]:
        """Synthesize candidate articles into a structured daily news briefing with category batching.

        Args:
            articles: Either a flat list of Article objects or a dict grouped by categoryId.
            briefing_date: Optional briefing date (ISO 8601 string or datetime object).
            batch_size: Number of categories processed per Gemini call (default: 3).

        Returns:
            Structured dictionary matching dashboard schema:
            {
                "briefingDate": "...",
                "topHeadlines": [... exactly 3 items ...],
                "articles": [... category items ...]
            }

        Raises:
            GeminiAPIError: If LLM call fails and fallback_on_error is False.
        """
        # Resolve briefing date string
        if isinstance(briefing_date, datetime):
            briefing_date_str = briefing_date.isoformat()
        elif isinstance(briefing_date, str) and briefing_date.strip():
            briefing_date_str = briefing_date.strip()
        else:
            briefing_date_str = datetime.now(timezone.utc).isoformat()

        # Group articles if flat list
        if isinstance(articles, dict):
            grouped = articles
        else:
            grouped = self.group_articles_by_category(articles)

        # If no articles were collected, return empty briefing without external LLM call
        total_articles = sum(len(cat_arts) for cat_arts in grouped.values())
        if total_articles == 0:
            return {
                "briefingDate": briefing_date_str,
                "topHeadlines": [],
                "articles": [],
            }

        active_cids = [cid for cid in sorted(grouped.keys()) if grouped[cid]]
        if not active_cids:
            return {
                "briefingDate": briefing_date_str,
                "topHeadlines": [],
                "articles": [],
            }

        # Partition active categories into chunks of batch_size
        chunk_size = max(1, batch_size)
        chunks = [
            active_cids[i : i + chunk_size]
            for i in range(0, len(active_cids), chunk_size)
        ]

        batch_headlines_list: list[list[dict[str, Any]]] = []
        all_candidate_articles: list[dict[str, Any]] = []

        for chunk_cids in chunks:
            chunk_grouped = {cid: grouped[cid] for cid in chunk_cids}
            prompt = build_briefing_prompt(chunk_grouped, categories=self.categories)

            try:
                raw_data = self.client.generate_json(
                    contents=prompt,
                    system_instruction=SYSTEM_PROMPT,
                    response_schema=BRIEFING_RESPONSE_SCHEMA,
                )

                chunk_headlines: list[dict[str, Any]] = []
                raw_headlines = raw_data.get("topHeadlines")
                if isinstance(raw_headlines, list):
                    for hl in raw_headlines:
                        if isinstance(hl, dict):
                            cid = self._coerce_category_id(hl.get("categoryId"))
                            if len(chunks) == 1 or cid in chunk_cids:
                                chunk_headlines.append(hl)
                batch_headlines_list.append(chunk_headlines)

                raw_articles = raw_data.get("articles")
                if isinstance(raw_articles, list):
                    for art_item in raw_articles:
                        if isinstance(art_item, dict):
                            cid = self._coerce_category_id(art_item.get("categoryId"))
                            if len(chunks) == 1 or cid in chunk_cids:
                                all_candidate_articles.append(art_item)

            except Exception as exc:
                if not self.fallback_on_error:
                    raise
                logger.warning(
                    "LLM summarization failed for category chunk %s (%s). Generating extractive fallback for this chunk.",
                    chunk_cids,
                    exc,
                )
                chunk_fallback = self.extract_fallback_briefing(
                    chunk_grouped,
                    briefing_date=briefing_date_str,
                )
                batch_headlines_list.append(chunk_fallback.get("topHeadlines", []))
                all_candidate_articles.extend(chunk_fallback.get("articles", []))

        # Interleave / synthesize topHeadlines candidates across all batches
        max_batch_hl = max((len(b) for b in batch_headlines_list), default=0)
        interleaved_headlines: list[dict[str, Any]] = []
        for idx in range(max_batch_hl):
            for b in batch_headlines_list:
                if idx < len(b):
                    interleaved_headlines.append(b[idx])

        combined_raw = {
            "topHeadlines": interleaved_headlines,
            "articles": all_candidate_articles,
        }

        return self._normalize_briefing_payload(combined_raw, grouped, briefing_date_str)

    def extract_fallback_briefing(
        self,
        grouped_articles: dict[int, list[Article]],
        briefing_date: str | None = None,
    ) -> dict[str, Any]:
        """Generate an extractive fallback briefing without external LLM calls.

        Selects top candidate articles across categories and formats them into the
        exact dashboard schema (3 topHeadlines and categorized articles) to guarantee
        operational continuity.
        """
        if briefing_date is None:
            briefing_date = datetime.now(timezone.utc).isoformat()

        top_headlines: list[dict[str, Any]] = []
        articles_list: list[dict[str, Any]] = []
        chosen_article_ids: set[str] = set()

        # Round-robin category selection for Top 3 Headlines
        for cat_id in sorted(grouped_articles.keys()):
            cat_articles = grouped_articles[cat_id]
            if cat_articles and len(top_headlines) < 3:
                art = cat_articles[0]
                chosen_article_ids.add(art.id)
                top_headlines.append({
                    "id": len(top_headlines) + 1,
                    "categoryId": cat_id,
                    "headline": art.title,
                    "summary": art.summary or f"{art.outlet or '주요 언론'} 보도: {art.title}",
                    "impact": "해당 이슈가 사회 및 관련 산업 전반에 미치는 파급 효과에 주목이 쏠리고 있어요.",
                    "deepDive": make_default_deep_dive(cat_id, art.title, art.summary),
                    "links": [
                        {
                            "title": f"{art.outlet} - {art.title}" if art.outlet else art.title,
                            "url": art.url,
                        }
                    ],
                })

        # If fewer than 3 headlines, select from remaining articles
        if len(top_headlines) < 3:
            for cat_id in sorted(grouped_articles.keys()):
                for art in grouped_articles[cat_id]:
                    if len(top_headlines) >= 3:
                        break
                    if art.id not in chosen_article_ids:
                        chosen_article_ids.add(art.id)
                        top_headlines.append({
                            "id": len(top_headlines) + 1,
                            "categoryId": cat_id,
                            "headline": art.title,
                            "summary": art.summary or f"{art.outlet or '주요 언론'} 보도: {art.title}",
                            "impact": "관련 정책 및 시장 환경 변화에 지속적인 영향이 예상돼요.",
                            "deepDive": make_default_deep_dive(cat_id, art.title, art.summary),
                            "links": [
                                {
                                    "title": f"{art.outlet} - {art.title}" if art.outlet else art.title,
                                    "url": art.url,
                                }
                            ],
                        })

        # Category articles selection (up to 2 per category, continuing sequence from 4)
        art_counter = len(top_headlines) + 1
        for cat_id in sorted(grouped_articles.keys()):
            cat_articles = grouped_articles[cat_id]
            for art in cat_articles:
                if art.id in chosen_article_ids and len(cat_articles) > 1:
                    continue
                articles_list.append({
                    "id": art_counter,
                    "categoryId": cat_id,
                    "headline": art.title,
                    "summary": art.summary or f"{art.outlet or '언론사'} 보도: {art.title}",
                    "impact": "업계 동향 및 관련 시장 지표에 미치는 영향을 주시하고 있어요.",
                    "deepDive": make_default_deep_dive(cat_id, art.title, art.summary),
                    "links": [
                        {
                            "title": f"{art.outlet} - {art.title}" if art.outlet else art.title,
                            "url": art.url,
                        }
                    ],
                })
                art_counter += 1
                if len([a for a in articles_list if a["categoryId"] == cat_id]) >= 2:
                    break

        return {
            "briefingDate": briefing_date,
            "topHeadlines": top_headlines,
            "articles": articles_list,
        }

    def _normalize_deep_dive(
        self,
        deep_dive: Any,
        cat_id: int,
        headline: str = "",
        summary: str = "",
    ) -> dict[str, Any]:
        """Validate and normalize deepDive structure, ensuring compliance with category lenses."""
        lens = CATEGORY_LENSES.get(cat_id, CATEGORY_LENSES[1])
        default_lens_title = lens["lensTitle"]

        if isinstance(deep_dive, dict):
            lens_title = str(deep_dive.get("lensTitle", "")).strip() or default_lens_title
            raw_sections = deep_dive.get("sections")
            if isinstance(raw_sections, list) and raw_sections:
                normalized_sections: list[dict[str, str]] = []
                for sec in raw_sections:
                    if isinstance(sec, dict) and sec.get("label") and sec.get("content"):
                        normalized_sections.append({
                            "label": str(sec["label"]).strip(),
                            "content": str(sec["content"]).strip(),
                        })
                if normalized_sections:
                    return {
                        "lensTitle": lens_title,
                        "sections": normalized_sections,
                    }

        return make_default_deep_dive(cat_id, headline, summary)

    def _normalize_briefing_payload(
        self,
        raw_data: dict[str, Any],
        grouped_articles: dict[int, list[Article]],
        briefing_date: str,
    ) -> dict[str, Any]:
        """Normalize, sanitize, and validate briefing payload structure, deepDive, and links."""
        # Build candidate link pool for missing link fallback
        cat_links: dict[int, list[dict[str, str]]] = {}
        all_links: list[dict[str, str]] = []
        for cid, arts in grouped_articles.items():
            for art in arts:
                link = {
                    "title": f"{art.outlet} - {art.title}" if art.outlet else art.title,
                    "url": art.url,
                }
                cat_links.setdefault(cid, []).append(link)
                all_links.append(link)
                for rlink in getattr(art, "related_links", []) or []:
                    if isinstance(rlink, dict) and rlink.get("url"):
                        rl_entry = {
                            "title": rlink.get("title", ""),
                            "url": rlink["url"],
                        }
                        cat_links.setdefault(cid, []).append(rl_entry)
                        all_links.append(rl_entry)

        # Normalize topHeadlines
        raw_headlines = raw_data.get("topHeadlines")
        if not isinstance(raw_headlines, list):
            raw_headlines = []

        normalized_headlines: list[dict[str, Any]] = []
        for i, item in enumerate(raw_headlines):
            if not isinstance(item, dict):
                continue
            cid = self._coerce_category_id(item.get("categoryId"))
            links = self._sanitize_links(item.get("links"), cid, cat_links, all_links)
            hl = str(item.get("headline", "")).strip()
            sm = str(item.get("summary", "")).strip()
            dd = self._normalize_deep_dive(item.get("deepDive"), cid, headline=hl, summary=sm)

            normalized_headlines.append({
                "id": str(item.get("id") or f"top-{i+1}"),
                "categoryId": cid,
                "headline": hl,
                "summary": sm,
                "impact": str(item.get("impact", "")).strip(),
                "deepDive": dd,
                "links": links,
            })

        # De-duplicate headlines by title/headline
        seen_headlines: set[str] = set()
        deduped_headlines: list[dict[str, Any]] = []
        for h in normalized_headlines:
            key = h["headline"].strip()
            if key and key not in seen_headlines:
                seen_headlines.add(key)
                deduped_headlines.append(h)
        normalized_headlines = deduped_headlines

        # Cap topHeadlines at 3, supplement from extractive fallback if needed
        if len(normalized_headlines) > 3:
            normalized_headlines = normalized_headlines[:3]
        elif len(normalized_headlines) < 3:
            fallback = self.extract_fallback_briefing(grouped_articles, briefing_date=briefing_date)
            for fb_item in fallback.get("topHeadlines", []):
                if len(normalized_headlines) >= 3:
                    break
                if not any(h["headline"] == fb_item["headline"] for h in normalized_headlines):
                    copy_item = dict(fb_item)
                    copy_item["id"] = f"top-{len(normalized_headlines) + 1}"
                    normalized_headlines.append(copy_item)

        # Normalize category articles
        raw_articles = raw_data.get("articles")
        if not isinstance(raw_articles, list):
            raw_articles = []

        normalized_articles: list[dict[str, Any]] = []
        for i, item in enumerate(raw_articles):
            if not isinstance(item, dict):
                continue
            cid = self._coerce_category_id(item.get("categoryId"))
            links = self._sanitize_links(item.get("links"), cid, cat_links, all_links)
            hl = str(item.get("headline", "")).strip()
            sm = str(item.get("summary", "")).strip()
            dd = self._normalize_deep_dive(item.get("deepDive"), cid, headline=hl, summary=sm)

            normalized_articles.append({
                "id": str(item.get("id") or f"art-{i+1}"),
                "categoryId": cid,
                "headline": hl,
                "summary": sm,
                "impact": str(item.get("impact", "")).strip(),
                "deepDive": dd,
                "links": links,
            })

        # De-duplicate articles by headline
        seen_articles: set[str] = set()
        deduped_articles: list[dict[str, Any]] = []
        for a in normalized_articles:
            key = a["headline"].strip()
            if key and key not in seen_articles:
                seen_articles.add(key)
                deduped_articles.append(a)
        normalized_articles = deduped_articles

        # Assign continuous sequential integer IDs: 1..3 for top headlines, 4..N for articles
        for idx, item in enumerate(normalized_headlines, start=1):
            item["id"] = idx

        for idx, item in enumerate(normalized_articles, start=len(normalized_headlines) + 1):
            item["id"] = idx

        return {
            "briefingDate": briefing_date,
            "topHeadlines": normalized_headlines,
            "articles": normalized_articles,
        }

    def _coerce_category_id(self, val: Any) -> int:
        """Coerce raw category id to valid integer within configured categories."""
        if val is not None:
            try:
                cid = int(val)
                if cid in self.categories_map:
                    return cid
            except (ValueError, TypeError):
                pass
        return 1

    def _sanitize_links(
        self,
        links: Any,
        cat_id: int,
        cat_links: dict[int, list[dict[str, str]]],
        all_links: list[dict[str, str]],
    ) -> list[dict[str, str]]:
        """Ensure links is a non-empty list of {title, url} dicts, rejecting search query URLs."""
        search_domains = ("search.naver.com", "search.daum.net", "google.com/search")
        sanitized: list[dict[str, str]] = []
        if isinstance(links, list):
            for l in links:
                if isinstance(l, dict) and l.get("url"):
                    raw_url = str(l["url"]).strip()
                    # Strictly discard search engine query URLs
                    if any(domain in raw_url for domain in search_domains):
                        continue
                    sanitized.append({
                        "title": str(l.get("title", "")).strip() or "원문 기사",
                        "url": raw_url,
                    })

        if sanitized:
            return sanitized

        # Fallback to category candidate links or global candidate links
        if cat_id in cat_links and cat_links[cat_id]:
            return cat_links[cat_id][:2]
        if all_links:
            return all_links[:2]

        return [{"title": "원문 기사", "url": "https://news.naver.com"}]

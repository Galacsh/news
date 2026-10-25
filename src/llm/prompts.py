"""Prompt templates and structured schema definitions for Gemini news briefing summarizer."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from src.ingest.models import Article

# ============================================================================
# Default Categories & Fallbacks
# ============================================================================

DEFAULT_CATEGORIES: list[dict[str, Any]] = [
    {"id": 1, "name": "정치", "badgeColor": "blue"},
    {"id": 2, "name": "경제·금융", "badgeColor": "emerald"},
    {"id": 3, "name": "산업·기업", "badgeColor": "indigo"},
    {"id": 4, "name": "사회", "badgeColor": "violet"},
    {"id": 5, "name": "국제·글로벌", "badgeColor": "orange"},
    {"id": 6, "name": "AI·빅테크", "badgeColor": "cyan"},
    {"id": 7, "name": "IT·통신", "badgeColor": "teal"},
    {"id": 8, "name": "문화·콘텐츠", "badgeColor": "pink"},
    {"id": 9, "name": "스포츠", "badgeColor": "rose"},
    {"id": 10, "name": "라이프스타일", "badgeColor": "amber"},
]


def load_default_categories(categories_path: Path | str | None = None) -> list[dict[str, Any]]:
    """Load categories from data/categories.json or return default fallback categories."""
    if categories_path is None:
        categories_path = Path("data/categories.json")
    else:
        categories_path = Path(categories_path)

    if categories_path.is_file():
        try:
            with open(categories_path, encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict) and "categories" in data and isinstance(data["categories"], list):
                return data["categories"]
        except Exception:
            pass

    return DEFAULT_CATEGORIES


# ============================================================================
# System Prompt (English Instructions, Korean Output Mandate)
# ============================================================================

SYSTEM_PROMPT: str = (
    "You are the Editor-in-Chief and Senior Newsroom Desk Editor for a premier South Korean daily news briefing.\n"
    "Your mission is to analyze, synthesize, and curate candidate news articles from verified South Korean news "
    "outlets into a highly credible, approachable, and objective daily morning briefing.\n\n"
    "CRITICAL LANGUAGE & SPEECH STYLE MANDATE:\n"
    "- ALL generated narrative content ('headline', 'summary' [핵심], 'impact' [파급]) MUST be written in natural, fluent Korean (한국어).\n"
    "- TONE & SPEECH STYLE (해요체 필수):\n"
    "  * For 'summary' (핵심) and 'impact' (파급), you MUST strictly use the polite informal Korean speech style ('해요체', e.g., '~해요', '~돼요', '~있어요', '~이에요/예요', '~전망이에요', '~나타났어요').\n"
    "  * Strictly DO NOT use formal '하십시오체' ('~합니다', '~습니다', '~됩니다', '~전망입니다') or plain '해라체' ('~한다', '~이다').\n"
    "  * 'headline' must be a concise, standard Korean news headline title.\n"
    "- Only identifiers ('id', 'categoryId') and source 'url's should remain in their original formats.\n"
    "- DIRECT ARTICLE LINKS ONLY: In 'links', you MUST strictly copy the exact original article 'url' and 'title' from the candidate articles provided. NEVER invent, hallucinate, or substitute search engine links (e.g. search.naver.com, search.daum.net, google search). Only direct media outlet URLs are allowed.\n\n"
    "Editorial Guidelines:\n"
    "1. Neutrality & Tone: Maintain an objective, balanced journalistic tone while using friendly, polite '해요체'. Avoid sensationalism.\n"
    "2. Summary ('핵심'): Explain the core facts (who, what, when, where, why, how) in 1 to 2 complete Korean sentences ending strictly in '해요체'.\n"
    "3. Impact ('파급'): Analyze the broader societal, economic, policy, or everyday life implications in 1 to 2 complete Korean sentences ending strictly in '해요체'.\n"
    "4. Formatting: Write clean continuous prose. Do NOT include bullet points (-, *, •), lists, or markdown symbols inside 'summary' or 'impact'.\n"
    "5. Factual Grounding: Strictly avoid hallucination. Base every statement strictly on facts provided in candidate articles.\n"
    "6. JSON Schema: Strictly conform to the requested JSON response schema."
)


# ============================================================================
# Gemini Structured Response Schema
# ============================================================================

BRIEFING_RESPONSE_SCHEMA: dict[str, Any] = {
    "type": "OBJECT",
    "properties": {
        "topHeadlines": {
            "type": "ARRAY",
            "description": "The 3 most critical news headlines with highest national impact across all categories (must contain exactly 3 items). All text fields must be in Korean.",
            "items": {
                "type": "OBJECT",
                "properties": {
                    "id": {"type": "INTEGER", "description": "Unique sequential integer identifier (e.g. 1, 2, 3...)"},
                    "categoryId": {"type": "INTEGER", "description": "Integer category ID corresponding to categories.json"},
                    "headline": {"type": "STRING", "description": "Compelling, accurate Korean headline title"},
                    "summary": {"type": "STRING", "description": "Core factual summary (핵심) in 1-2 complete Korean sentences ending strictly in polite informal style (해요체, e.g. ~해요, ~돼요, ~있어요)"},
                    "impact": {"type": "STRING", "description": "Implications and societal/market impact (파급) in 1-2 complete Korean sentences ending strictly in polite informal style (해요체, e.g. ~전망이에요, ~있어요)"},
                    "links": {
                        "type": "ARRAY",
                        "description": "Source article links referenced for this briefing item",
                        "items": {
                            "type": "OBJECT",
                            "properties": {
                                "title": {"type": "STRING", "description": "Original article title in Korean"},
                                "url": {"type": "STRING", "description": "Original article URL"},
                            },
                            "required": ["title", "url"],
                        },
                    },
                },
                "required": ["id", "categoryId", "headline", "summary", "impact", "links"],
            },
        },
        "articles": {
            "type": "ARRAY",
            "description": "Curated in-depth briefing articles categorized by topic. All text fields must be in Korean.",
            "items": {
                "type": "OBJECT",
                "properties": {
                    "id": {"type": "INTEGER", "description": "Unique sequential integer identifier (e.g. 4, 5, 6...)"},
                    "categoryId": {"type": "INTEGER", "description": "Integer category ID corresponding to categories.json"},
                    "headline": {"type": "STRING", "description": "Clear, informative Korean article headline"},
                    "summary": {"type": "STRING", "description": "Core factual summary (핵심) in 1-2 complete Korean sentences ending strictly in polite informal style (해요체, e.g. ~해요, ~돼요, ~있어요)"},
                    "impact": {"type": "STRING", "description": "Implications and significance (파급) in 1-2 complete Korean sentences ending strictly in polite informal style (해요체, e.g. ~전망이에요, ~있어요)"},
                    "links": {
                        "type": "ARRAY",
                        "description": "Source article links referenced for this briefing item",
                        "items": {
                            "type": "OBJECT",
                            "properties": {
                                "title": {"type": "STRING", "description": "Original article title in Korean"},
                                "url": {"type": "STRING", "description": "Original article URL"},
                            },
                            "required": ["title", "url"],
                        },
                    },
                },
                "required": ["id", "categoryId", "headline", "summary", "impact", "links"],
            },
        },
    },
    "required": ["topHeadlines", "articles"],
}


# ============================================================================
# Prompt Formatter
# ============================================================================

def build_briefing_prompt(
    grouped_articles: dict[int, list[Article]],
    categories: list[dict[str, Any]] | None = None,
) -> str:
    """Format candidate articles grouped by category into a structured English briefing prompt with Korean output mandate."""
    cat_list = categories if categories is not None else load_default_categories()
    cat_names = {cat["id"]: cat.get("name", f"Category {cat['id']}") for cat in cat_list}

    total_articles = sum(len(articles) for articles in grouped_articles.values())

    lines: list[str] = [
        "Please synthesize the candidate news articles provided below into a comprehensive Daily Korea News Briefing.",
        "",
        "## Editorial & Synthesis Instructions",
        "1. [topHeadlines]: Select EXACTLY 3 of the most impactful, high-priority news stories across ALL categories for the top headlines.",
        "2. [articles]: For each category, curate 1 to 3 significant stories. Omit categories that have no candidate articles.",
        "3. CRITICAL LANGUAGE & SPEECH STYLE REQUIREMENT:",
        "   - All generated 'headline', 'summary' (핵심), and 'impact' (파급) values MUST be written in natural Korean (한국어).",
        "   - Both 'summary' (핵심) and 'impact' (파급) MUST be written strictly in polite informal style ('해요체', e.g. '~해요', '~돼요', '~있어요', '~전망이에요'). Do NOT use '~합니다' or '~습니다'.",
        "4. Required attributes for every item:",
        "   - id: Unique sequential integer ID (1, 2, 3 for topHeadlines, continuing 4, 5, 6... for articles)",
        "   - categoryId: Integer ID corresponding to the category of the news event",
        "   - headline: Accurate, engaging headline in Korean",
        "   - summary: Concise factual summary in 1-2 complete Korean sentences ending strictly in 해요체 (no bullet points or markdown lists)",
        "   - impact: Significance and societal/economic repercussions in 1-2 complete Korean sentences ending strictly in 해요체 (no bullet points)",
        "   - links: List of referenced source articles with their original Korean 'title' and direct article 'url' (copy directly from candidate articles, strictly DO NOT use search engine query links)",
        "5. Factual accuracy: Base all synthesis strictly on the provided candidate articles with zero hallucination.",
        "",
        f"## Ingested Candidate Articles (Total: {total_articles} articles)",
    ]

    if total_articles == 0:
        lines.append("(No candidate articles provided)")
        return "\n".join(lines)

    for cat_id in sorted(grouped_articles.keys()):
        articles = grouped_articles[cat_id]
        if not articles:
            continue
        cat_name = cat_names.get(cat_id, f"Category {cat_id}")
        lines.append(f"\n### [Category ID: {cat_id}] {cat_name} ({len(articles)} articles)")
        for art in articles:
            title = art.title.strip()
            summary = art.summary.strip().replace("\n", " ") if art.summary else ""
            if len(summary) > 200:
                summary = summary[:197] + "..."
            outlet = f"[{art.outlet}] " if art.outlet else ""
            lines.append(f"- Article ID: {art.id} | {outlet}{title}")
            if summary:
                lines.append(f"  Summary: {summary}")
            lines.append(f"  URL: {art.url}")

    lines.append("\nGenerate the briefing JSON adhering strictly to the response schema.")
    return "\n".join(lines)

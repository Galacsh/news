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

CATEGORY_LENSES: dict[int, dict[str, Any]] = {
    1: {"lensTitle": "의도와 실현 가능성", "sections": ["왜 지금 나왔나 (숨은 셈법)", "실제 통과·시행 가능성과 효력"]},
    2: {"lensTitle": "착시 제거 & 내 지갑 타격", "sections": ["지표·발표 이면의 맹점", "금리·물가·내 지갑에 미치는 영향"]},
    3: {"lensTitle": "보도자료 판독 & 승패 해부", "sections": ["홍보 거품 걷어낸 실제 현황", "웃는 기업(수혜) vs 우는 기업(피해)"]},
    4: {"lensTitle": "배경 맥락 & 행동 지침", "sections": ["사안의 구조적 배경", "시민이 챙겨야 할 실질적 체크포인트"]},
    5: {"lensTitle": "한국에 튀는 불똥", "sections": ["글로벌 갈등·사건의 본질", "한국 수출·환율·산업에 미칠 손익"]},
    6: {"lensTitle": "거품 vs 진짜 기술 변곡점", "sections": ["마케팅 빼고 진짜 바뀐 기술 본질", "개발자·실무·생태계 판도 변화"]},
    7: {"lensTitle": "기술 실효성 & 시장 판도", "sections": ["기존 서비스 대비 핵심 차이점", "소비자·통신·IT 업계 체감 변화"]},
    8: {"lensTitle": "흥행 맥락 & 관전 포인트", "sections": ["기록·트렌드의 산업적 의미", "향후 일정 및 핵심 관전 포인트"]},
    9: {"lensTitle": "승부처 분석 & 향후 일정", "sections": ["결정적 승부처와 기록의 의미", "다음 경기 일정 및 관전 포인트"]},
    10: {"lensTitle": "일상의 행동 법칙", "sections": ["트렌드·연구 결과의 팩트 체크", "일상에서 바로 적용할 행동 요령"]},
}


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
    "- ALL generated narrative content ('headline', 'summary' [핵심], 'impact' [파급], and 'deepDive' sections) MUST be written in natural, fluent Korean (한국어).\n"
    "- TONE & SPEECH STYLE (해요체 필수):\n"
    "  * For 'summary' (핵심), 'impact' (파급), and all 'deepDive' section contents, you MUST strictly use the polite informal Korean speech style ('해요체', e.g., '~해요', '~돼요', '~있어요', '~이에요/예요', '~전망이에요', '~나타났어요').\n"
    "  * Strictly DO NOT use formal '하십시오체' ('~합니다', '~습니다', '~됩니다', '~전망입니다') or plain '해라체' ('~한다', '~이다').\n"
    "  * 'headline' must be a concise, standard Korean news headline title.\n"
    "- Only identifiers ('id', 'categoryId') and source 'url's should remain in their original formats.\n"
    "- DIRECT ARTICLE LINKS ONLY: In 'links', you MUST strictly copy the exact original article 'url' and 'title' from the candidate articles provided. NEVER invent, hallucinate, or substitute search engine links (e.g. search.naver.com, search.daum.net, google search). Only direct media outlet URLs are allowed.\n\n"
    "Editorial Guidelines:\n"
    "1. Neutrality & Tone: Maintain an objective, balanced journalistic tone while using friendly, polite '해요체'. Avoid sensationalism.\n"
    "2. Summary ('핵심'): Explain the core facts (who, what, when, where, why, how) in 1 to 2 complete Korean sentences ending strictly in '해요체'.\n"
    "3. Impact ('파급'): Analyze the broader societal, economic, policy, or everyday life implications in 1 to 2 complete Korean sentences ending strictly in '해요체'.\n"
    "4. DeepDive ('심층 분석'): For each news item (both topHeadlines and articles), generate a 'deepDive' object matching the designated analytical lens (lensTitle and section labels) of its category. Each section content must be 1 to 2 insightful sentences in '해요체'.\n"
    "5. Formatting: Write clean continuous prose. Do NOT include bullet points (-, *, •), lists, or markdown symbols inside 'summary', 'impact', or 'deepDive' content.\n"
    "6. Factual Grounding: Strictly avoid hallucination. Base every statement strictly on facts provided in candidate articles.\n"
    "7. JSON Schema: Strictly conform to the requested JSON response schema."
)


# ============================================================================
# Gemini Structured Response Schema
# ============================================================================

DEEP_DIVE_SCHEMA: dict[str, Any] = {
    "type": "OBJECT",
    "description": "Category-tailored analytical deep dive",
    "properties": {
        "lensTitle": {"type": "STRING"},
        "sections": {
            "type": "ARRAY",
            "items": {
                "type": "OBJECT",
                "properties": {
                    "label": {"type": "STRING"},
                    "content": {"type": "STRING", "description": "Analysis in 해요체"},
                },
                "required": ["label", "content"],
            },
        },
    },
    "required": ["lensTitle", "sections"],
}

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
                    "deepDive": DEEP_DIVE_SCHEMA,
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
                "required": ["id", "categoryId", "headline", "summary", "impact", "deepDive", "links"],
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
                    "deepDive": DEEP_DIVE_SCHEMA,
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
                "required": ["id", "categoryId", "headline", "summary", "impact", "deepDive", "links"],
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
        "   - All generated 'headline', 'summary' (핵심), 'impact' (파급), and 'deepDive' values MUST be written in natural Korean (한국어).",
        "   - 'summary' (핵심), 'impact' (파급), and all 'deepDive' section contents MUST be written strictly in polite informal style ('해요체', e.g. '~해요', '~돼요', '~있어요', '~전망이에요'). Do NOT use '~합니다' or '~습니다'.",
        "4. Required attributes for every item:",
        "   - id: Unique sequential integer ID (1, 2, 3 for topHeadlines, continuing 4, 5, 6... for articles)",
        "   - categoryId: Integer ID corresponding to the category of the news event",
        "   - headline: Accurate, engaging headline in Korean",
        "   - summary: Concise factual summary in 1-2 complete Korean sentences ending strictly in 해요체 (no bullet points or markdown lists)",
        "   - impact: Significance and societal/economic repercussions in 1-2 complete Korean sentences ending strictly in 해요체 (no bullet points)",
        "   - deepDive: Category-tailored analytical deep dive object containing 'lensTitle' and 'sections' matching the category lens. Each section content must be 1-2 sentences in 해요체.",
        "   - links: List of referenced source articles with their original Korean 'title' and direct article 'url' (copy directly from candidate articles, strictly DO NOT use search engine query links)",
        "5. Factual accuracy: Base all synthesis strictly on the provided candidate articles with zero hallucination.",
        "",
        "## Category DeepDive Analytical Lenses (Mandatory):",
    ]

    for cid in sorted(grouped_articles.keys()):
        lens = CATEGORY_LENSES.get(cid, CATEGORY_LENSES[1])
        cname = cat_names.get(cid, f"Category {cid}")
        sections_str = ", ".join(f'"{s}"' for s in lens["sections"])
        lines.append(f"- Category {cid} ({cname}): lensTitle='{lens['lensTitle']}', sections=[{sections_str}]")

    lines.append(f"\n## Ingested Candidate Articles (Total: {total_articles} articles)")

    if total_articles == 0:
        lines.append("(No candidate articles provided)")
        return "\n".join(lines)

    for cat_id in sorted(grouped_articles.keys()):
        articles = grouped_articles[cat_id]
        if not articles:
            continue
        cat_name = cat_names.get(cat_id, f"Category {cat_id}")
        lens = CATEGORY_LENSES.get(cat_id, CATEGORY_LENSES[1])
        lines.append(f"\n### [Category ID: {cat_id}] {cat_name} ({len(articles)} articles)")
        lines.append(f"  Category Lens: {lens['lensTitle']}")
        for art in articles:
            title = art.title.strip()
            summary = art.summary.strip().replace("\n", " ") if art.summary else ""
            if len(summary) > 200:
                summary = summary[:197] + "..."
            outlet = f"[{art.outlet}] " if art.outlet else ""
            lines.append(f"- Article ID: {art.id} | {outlet}{title}")
            if summary:
                lines.append(f"  Summary: {summary}")
            body = getattr(art, "body", None)
            if body and isinstance(body, str) and body.strip():
                clean_body = body.strip().replace("\n", " ")
                if len(clean_body) > 300:
                    clean_body = clean_body[:297] + "..."
                lines.append(f"  Body Excerpt: {clean_body}")
            lines.append(f"  URL: {art.url}")

    lines.append("\nGenerate the briefing JSON adhering strictly to the response schema.")
    return "\n".join(lines)

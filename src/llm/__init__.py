"""LLM client, prompt templates, and synthesis summarizer for news briefing."""

from src.llm.client import GeminiAPIError, GeminiClient
from src.llm.prompts import (
    BRIEFING_RESPONSE_SCHEMA,
    DEFAULT_CATEGORIES,
    SYSTEM_PROMPT,
    build_briefing_prompt,
    load_default_categories,
)
from src.llm.summarizer import NewsSummarizer

__all__ = [
    "BRIEFING_RESPONSE_SCHEMA",
    "DEFAULT_CATEGORIES",
    "GeminiAPIError",
    "GeminiClient",
    "NewsSummarizer",
    "SYSTEM_PROMPT",
    "build_briefing_prompt",
    "load_default_categories",
]

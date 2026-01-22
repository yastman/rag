"""Context-Enabled Semantic Cache (CESC) personalizer.

2026 best practice: Lazy CESC routing - only run personalization
when query actually needs it (personal markers or user has preferences).
"""

import logging
import re
from typing import Any


logger = logging.getLogger(__name__)

# Personal markers that indicate query needs personalization (Russian + English)
PERSONAL_MARKERS = [
    # Russian markers
    r"\bмне\b",
    r"\bя предпочитаю\b",
    r"\bкак в прошлый раз\b",
    r"\bдля моего\b",
    r"\bмой бюджет\b",
    r"\bмоя\b",
    r"\bмои\b",
    r"\bпо моим\b",
    r"\bисходя из моих\b",
    r"\bучитывая мои\b",
    r"\bпод мои\b",
    # English markers (for bilingual users)
    r"\bfor me\b",
    r"\bi prefer\b",
    r"\bmy budget\b",
    r"\blike last time\b",
]

# Compile regex patterns for efficiency
_PERSONAL_PATTERNS = [re.compile(p, re.IGNORECASE) for p in PERSONAL_MARKERS]


def is_personalized_query(query: str, user_context: dict[str, Any] | None = None) -> bool:
    """Check if query needs CESC personalization.

    2026 best practice: Lazy routing - skip CESC entirely for generic queries.
    Only personalize when:
    1. Query contains personal markers ("мне", "я предпочитаю", etc.)
    2. User already has preferences in context

    Args:
        query: User query text
        user_context: Optional user context with preferences

    Returns:
        True if query needs personalization, False to skip CESC
    """
    # Rule 1: Check for personal markers in query
    query_lower = query.lower()
    for pattern in _PERSONAL_PATTERNS:
        if pattern.search(query_lower):
            logger.debug(f"Personal marker found in query: {pattern.pattern}")
            return True

    # Rule 2: Check if user has stored preferences
    if user_context:
        prefs = user_context.get("preferences", {})
        if prefs.get("cities") or prefs.get("budget_max") or prefs.get("property_types"):
            logger.debug("User has preferences, enabling personalization")
            return True

    logger.debug("Query is generic, skipping CESC")
    return False


class CESCPersonalizer:
    """Personalizes cached responses using user context.

    Uses Cerebras LLM to adapt generic cached responses to user preferences
    (cities, budget, property types). Keeps responses concise (~100 tokens).
    """

    PERSONALIZATION_PROMPT = """Персонализируй ответ под пользователя:

ОТВЕТ: {cached_response}

КОНТЕКСТ:
- Города: {cities}
- Бюджет: до {budget}€
- Тип: {property_types}
- История: {profile_summary}

Сохрани факты, адаптируй подачу. Русский язык."""

    def __init__(self, llm_service: Any) -> None:
        """Initialize with LLM service.

        Args:
            llm_service: LLM service for personalization (Cerebras).
        """
        self.llm = llm_service

    def should_personalize(self, user_context: dict[str, Any]) -> bool:
        """Check if personalization should be applied.

        Returns True if user has meaningful preferences (cities, budget,
        property types, or rooms).

        Args:
            user_context: User context with preferences.

        Returns:
            True if personalization should run.
        """
        prefs = user_context.get("preferences", {})
        return bool(
            prefs.get("cities")
            or prefs.get("budget_max")
            or prefs.get("property_types")
            or prefs.get("rooms")
        )

    def _build_prompt(self, cached_response: str, user_context: dict[str, Any]) -> str:
        """Build personalization prompt from context.

        Args:
            cached_response: Generic cached answer.
            user_context: User preferences and history.

        Returns:
            Formatted prompt string.
        """
        prefs = user_context.get("preferences", {})

        return self.PERSONALIZATION_PROMPT.format(
            cached_response=cached_response[:500],  # Limit to 500 chars
            cities=", ".join(prefs.get("cities", ["любой"])),
            budget=prefs.get("budget_max", "не указан"),
            property_types=", ".join(prefs.get("property_types", ["любой"])),
            profile_summary=user_context.get("profile_summary", "новый пользователь"),
        )

    async def personalize(
        self,
        cached_response: str,
        user_context: dict[str, Any],
        query: str,
    ) -> str:
        """Personalize cached response using user context.

        Args:
            cached_response: Generic cached answer.
            user_context: User preferences and history.
            query: Current user query (for logging).

        Returns:
            Personalized response, or original if personalization fails
            or no preferences exist.
        """
        prefs = user_context.get("preferences", {})

        # If no preferences, return cached response as-is
        if not prefs:
            logger.debug("No user preferences, returning cached response")
            return cached_response

        prompt = self._build_prompt(cached_response, user_context)

        try:
            personalized = await self.llm.generate(prompt, max_tokens=300)
            user_id = user_context.get("user_id", "unknown")
            logger.info(f"CESC personalized response for user {user_id}")
            return personalized.strip()
        except Exception as e:
            logger.error(f"CESC personalization failed: {e}")
            return cached_response  # Fallback to cached

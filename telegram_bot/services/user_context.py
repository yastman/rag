"""User context management with LLM-based preference extraction."""

import json
import logging
from datetime import UTC, datetime
from typing import Any


logger = logging.getLogger(__name__)


class UserContextService:
    """Manages user context with LLM-based preference extraction.

    Extracts user preferences (cities, budget, property types) from queries
    every 3rd interaction using LLM. Stores context in Redis JSON with 30-day TTL.
    """

    EXTRACTION_PROMPT = """Проанализируй запрос пользователя и извлеки/обнови предпочтения:

Текущие предпочтения:
{current_preferences}

Новый запрос: {query}

Извлеки и верни JSON:
{{
    "cities": ["город1", "город2"],
    "budget_max": 100000,
    "property_types": ["apartment"],
    "rooms": 2,
    "distance_to_sea": 500
}}

Правила:
- Сохраняй существующие значения если новых нет
- Добавляй новые города к существующим
- Обновляй бюджет/комнаты если явно указаны
- Верни ТОЛЬКО JSON без пояснений"""

    def __init__(
        self,
        cache_service: Any,
        llm_service: Any,
        context_ttl: int = 30 * 24 * 3600,
        extraction_frequency: int = 3,
    ) -> None:
        """Initialize with cache and LLM services.

        Args:
            cache_service: Redis cache service for storing context.
            llm_service: LLM service for preference extraction.
            context_ttl: TTL for user context in Redis (default: 30 days).
            extraction_frequency: Extract preferences every N queries (default: 3).
        """
        self.cache = cache_service
        self.llm = llm_service
        self.context_ttl = context_ttl
        self.extraction_frequency = extraction_frequency

    def _default_context(self, user_id: int) -> dict[str, Any]:
        """Return default context for new users.

        Args:
            user_id: Telegram user ID.

        Returns:
            Default context dictionary with empty preferences.
        """
        now = datetime.now(UTC).isoformat()
        return {
            "user_id": user_id,
            "language": "ru",
            "preferences": {},
            "profile_summary": "",
            "interaction_count": 0,
            "last_queries": [],
            "created_at": now,
            "updated_at": now,
        }

    def _merge_preferences(self, old: dict[str, Any], new: dict[str, Any]) -> dict[str, Any]:
        """Merge new preferences with existing ones.

        Cities are merged and deduplicated. Scalar values are overwritten.
        None values in new dict are ignored.

        Args:
            old: Existing preferences.
            new: New preferences to merge.

        Returns:
            Merged preferences dictionary.
        """
        merged = old.copy()

        for key, value in new.items():
            if value is None:
                continue
            if key == "cities" and isinstance(value, list):
                existing = set(merged.get("cities", []))
                merged["cities"] = list(existing | set(value))
            else:
                merged[key] = value

        return merged

    def _generate_summary(self, context: dict[str, Any]) -> str:
        """Generate profile summary from preferences.

        Args:
            context: Full user context with preferences.

        Returns:
            Human-readable summary string.
        """
        prefs = context.get("preferences", {})
        parts = []

        if prefs.get("cities"):
            cities_str = ", ".join(prefs["cities"][:3])
            parts.append(f"Интересуется: {cities_str}")
        if prefs.get("budget_max"):
            parts.append(f"Бюджет до {prefs['budget_max']}€")
        if prefs.get("rooms"):
            parts.append(f"{prefs['rooms']}-комнатные")
        if prefs.get("property_types"):
            types_str = ", ".join(prefs["property_types"])
            parts.append(f"Тип: {types_str}")

        return ". ".join(parts) if parts else "Новый пользователь"

    def _should_extract(self, interaction_count: int, preferences: dict) -> bool:
        """Check if preferences should be extracted.

        Extraction triggers on first query (count % frequency == 1) or if preferences empty.

        Args:
            interaction_count: Current interaction count (already incremented).
            preferences: Current user preferences.

        Returns:
            True if extraction should run.
        """
        return interaction_count % self.extraction_frequency == 1 or not preferences

    async def get_context(self, user_id: int) -> dict[str, Any]:
        """Get full user context from Redis.

        Args:
            user_id: Telegram user ID.

        Returns:
            User context dictionary. Default context if not found.
        """
        if not self.cache or not hasattr(self.cache, "redis_client"):
            return self._default_context(user_id)

        if not self.cache.redis_client:
            return self._default_context(user_id)

        key = f"user_context:{user_id}"
        try:
            data = await self.cache.redis_client.get(key)
            if data:
                return json.loads(data)
        except Exception as e:
            logger.warning(f"Failed to get user context: {e}")

        return self._default_context(user_id)

    async def update_from_query(self, user_id: int, query: str) -> dict[str, Any]:
        """Extract preferences from query and update context.

        Updates interaction stats, extracts preferences every 3rd query,
        and regenerates profile summary after 5+ interactions.

        Args:
            user_id: Telegram user ID.
            query: User's query text.

        Returns:
            Updated user context dictionary.
        """
        context = await self.get_context(user_id)

        # Update interaction stats
        context["interaction_count"] += 1
        context["last_queries"] = [query, *context["last_queries"][:4]]
        context["updated_at"] = datetime.now(UTC).isoformat()

        # Extract preferences every 3rd query or if empty
        if self._should_extract(context["interaction_count"], context["preferences"]):
            try:
                new_prefs = await self._extract_preferences(query, context["preferences"])
                context["preferences"] = self._merge_preferences(context["preferences"], new_prefs)
                logger.info(f"Extracted preferences for user {user_id}: {new_prefs}")
            except Exception as e:
                logger.warning(f"Preference extraction failed: {e}")

            # Update profile summary after 5+ interactions
            if context["interaction_count"] >= 5:
                context["profile_summary"] = self._generate_summary(context)

        # Save to Redis
        await self._save_context(user_id, context)

        return context

    async def _extract_preferences(self, query: str, current: dict[str, Any]) -> dict[str, Any]:
        """Use LLM to extract preferences from query.

        Args:
            query: User's query text.
            current: Current preferences for context.

        Returns:
            Extracted preferences dictionary.

        Raises:
            json.JSONDecodeError: If LLM response is not valid JSON.
        """
        prompt = self.EXTRACTION_PROMPT.format(
            current_preferences=json.dumps(current, ensure_ascii=False),
            query=query,
        )

        response = await self.llm.generate(prompt, max_tokens=200)

        # Parse JSON from response
        response_clean = response.strip()
        # Handle markdown code blocks
        if response_clean.startswith("```"):
            lines = response_clean.split("\n")
            # Find content between ``` markers
            json_lines = []
            in_block = False
            for line in lines:
                if line.startswith("```"):
                    if in_block:
                        break
                    in_block = True
                    continue
                if in_block:
                    json_lines.append(line)
            response_clean = "\n".join(json_lines)

        return json.loads(response_clean)

    async def _save_context(self, user_id: int, context: dict[str, Any]) -> None:
        """Save context to Redis with TTL.

        Args:
            user_id: Telegram user ID.
            context: Context dictionary to save.
        """
        if not self.cache or not hasattr(self.cache, "redis_client"):
            return
        if not self.cache.redis_client:
            return

        key = f"user_context:{user_id}"
        try:
            await self.cache.redis_client.setex(
                key,
                self.context_ttl,
                json.dumps(context, ensure_ascii=False),
            )
        except Exception as e:
            logger.warning(f"Failed to save user context: {e}")

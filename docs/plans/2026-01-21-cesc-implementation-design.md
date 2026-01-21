# CESC (Context-Enabled Semantic Cache) Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Personalize cached RAG responses using user context extracted from conversation history via Cerebras LLM.

**Architecture:** On cache HIT, pass the generic cached response through a lightweight LLM call (~100 tokens) that adapts the response to user preferences (cities, budget, property types). User preferences are extracted every 3rd query and stored in Redis JSON with 30-day TTL.

**Tech Stack:** Redis JSON for context storage, Cerebras LLM (existing provider), Python 3.12+, pytest for testing.

---

## Task 1: Create UserContextService with Tests

**Files:**
- Create: `telegram_bot/services/user_context.py`
- Create: `tests/test_user_context.py`

### Step 1: Write the failing tests for UserContextService

```python
# tests/test_user_context.py
"""Tests for UserContextService."""

import pytest
from telegram_bot.services.user_context import UserContextService


class TestUserContextService:
    """Tests for user context management."""

    def test_default_context_structure(self):
        """Test default context has required fields."""
        service = UserContextService(cache_service=None, llm_service=None)
        context = service._default_context(user_id=12345)

        assert context["user_id"] == 12345
        assert context["language"] == "ru"
        assert context["preferences"] == {}
        assert context["profile_summary"] == ""
        assert context["interaction_count"] == 0
        assert context["last_queries"] == []
        assert "created_at" in context
        assert "updated_at" in context

    def test_merge_preferences_cities_dedup(self):
        """Test merging cities deduplicates correctly."""
        service = UserContextService(cache_service=None, llm_service=None)
        old = {"cities": ["Бургас", "Несебр"]}
        new = {"cities": ["Несебр", "Варна"]}

        merged = service._merge_preferences(old, new)

        assert set(merged["cities"]) == {"Бургас", "Несебр", "Варна"}

    def test_merge_preferences_overwrites_scalar(self):
        """Test scalar values are overwritten."""
        service = UserContextService(cache_service=None, llm_service=None)
        old = {"budget_max": 100000, "rooms": 2}
        new = {"budget_max": 80000}

        merged = service._merge_preferences(old, new)

        assert merged["budget_max"] == 80000
        assert merged["rooms"] == 2

    def test_merge_preferences_ignores_none(self):
        """Test None values are ignored."""
        service = UserContextService(cache_service=None, llm_service=None)
        old = {"budget_max": 100000}
        new = {"budget_max": None, "rooms": 2}

        merged = service._merge_preferences(old, new)

        assert merged["budget_max"] == 100000
        assert merged["rooms"] == 2

    def test_generate_summary_full(self):
        """Test summary generation with full preferences."""
        service = UserContextService(cache_service=None, llm_service=None)
        context = {
            "preferences": {
                "cities": ["Бургас", "Несебр", "Варна"],
                "budget_max": 100000,
                "rooms": 2,
                "property_types": ["apartment", "studio"],
            }
        }

        summary = service._generate_summary(context)

        assert "Бургас" in summary
        assert "100000" in summary
        assert "2-комнатные" in summary
        assert "apartment" in summary

    def test_generate_summary_empty(self):
        """Test summary generation with no preferences."""
        service = UserContextService(cache_service=None, llm_service=None)
        context = {"preferences": {}}

        summary = service._generate_summary(context)

        assert summary == "Новый пользователь"

    def test_should_extract_on_first_query(self):
        """Test extraction triggers on first query (count % 3 == 1)."""
        service = UserContextService(cache_service=None, llm_service=None)

        # interaction_count will be 1 after first query
        assert service._should_extract(interaction_count=1, preferences={})

    def test_should_extract_on_empty_prefs(self):
        """Test extraction triggers when preferences empty."""
        service = UserContextService(cache_service=None, llm_service=None)

        assert service._should_extract(interaction_count=5, preferences={})

    def test_should_not_extract_mid_cycle(self):
        """Test extraction skipped in middle of 3-query cycle."""
        service = UserContextService(cache_service=None, llm_service=None)

        assert not service._should_extract(
            interaction_count=2, preferences={"cities": ["Бургас"]}
        )
        assert not service._should_extract(
            interaction_count=3, preferences={"cities": ["Бургас"]}
        )
```

### Step 2: Run tests to verify they fail

Run: `pytest tests/test_user_context.py -v`
Expected: FAIL with "ModuleNotFoundError: No module named 'telegram_bot.services.user_context'"

### Step 3: Write minimal UserContextService implementation

```python
# telegram_bot/services/user_context.py
"""User context management with LLM-based preference extraction."""

import json
import logging
from datetime import datetime, timezone
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

    def __init__(self, cache_service: Any, llm_service: Any) -> None:
        """Initialize with cache and LLM services.

        Args:
            cache_service: Redis cache service for storing context.
            llm_service: LLM service for preference extraction.
        """
        self.cache = cache_service
        self.llm = llm_service
        self.context_ttl = 30 * 24 * 3600  # 30 days

    def _default_context(self, user_id: int) -> dict[str, Any]:
        """Return default context for new users.

        Args:
            user_id: Telegram user ID.

        Returns:
            Default context dictionary with empty preferences.
        """
        now = datetime.now(timezone.utc).isoformat()
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

    def _merge_preferences(
        self, old: dict[str, Any], new: dict[str, Any]
    ) -> dict[str, Any]:
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

        Extraction triggers on first query (count % 3 == 1) or if preferences empty.

        Args:
            interaction_count: Current interaction count (already incremented).
            preferences: Current user preferences.

        Returns:
            True if extraction should run.
        """
        return interaction_count % 3 == 1 or not preferences

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

    async def update_from_query(
        self, user_id: int, query: str
    ) -> dict[str, Any]:
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
        context["last_queries"] = [query] + context["last_queries"][:4]
        context["updated_at"] = datetime.now(timezone.utc).isoformat()

        # Extract preferences every 3rd query or if empty
        if self._should_extract(
            context["interaction_count"], context["preferences"]
        ):
            try:
                new_prefs = await self._extract_preferences(
                    query, context["preferences"]
                )
                context["preferences"] = self._merge_preferences(
                    context["preferences"], new_prefs
                )
                logger.info(
                    f"Extracted preferences for user {user_id}: {new_prefs}"
                )
            except Exception as e:
                logger.warning(f"Preference extraction failed: {e}")

            # Update profile summary after 5+ interactions
            if context["interaction_count"] >= 5:
                context["profile_summary"] = self._generate_summary(context)

        # Save to Redis
        await self._save_context(user_id, context)

        return context

    async def _extract_preferences(
        self, query: str, current: dict[str, Any]
    ) -> dict[str, Any]:
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

    async def _save_context(
        self, user_id: int, context: dict[str, Any]
    ) -> None:
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
```

### Step 4: Run tests to verify they pass

Run: `pytest tests/test_user_context.py -v`
Expected: All 8 tests PASS

### Step 5: Commit

```bash
git add telegram_bot/services/user_context.py tests/test_user_context.py
git commit -m "feat(cesc): add UserContextService with preference extraction"
```

---

## Task 2: Create CESCPersonalizer with Tests

**Files:**
- Create: `telegram_bot/services/cesc.py`
- Create: `tests/test_cesc.py`

### Step 1: Write the failing tests for CESCPersonalizer

```python
# tests/test_cesc.py
"""Tests for CESCPersonalizer."""

import pytest
from telegram_bot.services.cesc import CESCPersonalizer


class TestCESCPersonalizer:
    """Tests for CESC personalization logic."""

    def test_should_personalize_with_cities(self):
        """Test personalization enabled when cities present."""
        personalizer = CESCPersonalizer(llm_service=None)
        context = {"preferences": {"cities": ["Бургас"]}}

        assert personalizer.should_personalize(context) is True

    def test_should_personalize_with_budget(self):
        """Test personalization enabled when budget present."""
        personalizer = CESCPersonalizer(llm_service=None)
        context = {"preferences": {"budget_max": 100000}}

        assert personalizer.should_personalize(context) is True

    def test_should_personalize_with_property_types(self):
        """Test personalization enabled when property types present."""
        personalizer = CESCPersonalizer(llm_service=None)
        context = {"preferences": {"property_types": ["apartment"]}}

        assert personalizer.should_personalize(context) is True

    def test_should_personalize_with_rooms(self):
        """Test personalization enabled when rooms present."""
        personalizer = CESCPersonalizer(llm_service=None)
        context = {"preferences": {"rooms": 2}}

        assert personalizer.should_personalize(context) is True

    def test_should_not_personalize_empty_prefs(self):
        """Test personalization disabled when preferences empty."""
        personalizer = CESCPersonalizer(llm_service=None)
        context = {"preferences": {}}

        assert personalizer.should_personalize(context) is False

    def test_should_not_personalize_no_prefs_key(self):
        """Test personalization disabled when no preferences key."""
        personalizer = CESCPersonalizer(llm_service=None)
        context = {}

        assert personalizer.should_personalize(context) is False

    def test_build_prompt_with_full_context(self):
        """Test prompt building with full user context."""
        personalizer = CESCPersonalizer(llm_service=None)
        context = {
            "preferences": {
                "cities": ["Бургас", "Несебр"],
                "budget_max": 100000,
                "property_types": ["apartment", "studio"],
            },
            "profile_summary": "Ищет квартиры у моря",
        }
        cached_response = "Вот информация о недвижимости."

        prompt = personalizer._build_prompt(cached_response, context)

        assert "Бургас" in prompt
        assert "Несебр" in prompt
        assert "100000" in prompt
        assert "apartment" in prompt
        assert "Ищет квартиры у моря" in prompt
        assert "Вот информация о недвижимости" in prompt

    def test_build_prompt_with_missing_fields(self):
        """Test prompt building gracefully handles missing fields."""
        personalizer = CESCPersonalizer(llm_service=None)
        context = {"preferences": {"cities": ["Бургас"]}}
        cached_response = "Ответ"

        prompt = personalizer._build_prompt(cached_response, context)

        assert "Бургас" in prompt
        assert "не указан" in prompt  # Default for missing budget
        assert "новый пользователь" in prompt  # Default for missing summary
```

### Step 2: Run tests to verify they fail

Run: `pytest tests/test_cesc.py -v`
Expected: FAIL with "ModuleNotFoundError: No module named 'telegram_bot.services.cesc'"

### Step 3: Write minimal CESCPersonalizer implementation

```python
# telegram_bot/services/cesc.py
"""Context-Enabled Semantic Cache (CESC) personalizer."""

import logging
from typing import Any

logger = logging.getLogger(__name__)


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

    def _build_prompt(
        self, cached_response: str, user_context: dict[str, Any]
    ) -> str:
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
            profile_summary=user_context.get(
                "profile_summary", "новый пользователь"
            ),
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
```

### Step 4: Run tests to verify they pass

Run: `pytest tests/test_cesc.py -v`
Expected: All 8 tests PASS

### Step 5: Commit

```bash
git add telegram_bot/services/cesc.py tests/test_cesc.py
git commit -m "feat(cesc): add CESCPersonalizer for cache response personalization"
```

---

## Task 3: Update services/__init__.py

**Files:**
- Modify: `telegram_bot/services/__init__.py`

### Step 1: Read current file to understand exports

Run: `cat telegram_bot/services/__init__.py`

### Step 2: Add new exports

Add to `telegram_bot/services/__init__.py`:

```python
from .user_context import UserContextService
from .cesc import CESCPersonalizer
```

And add to `__all__` list:

```python
__all__ = [
    # ... existing exports ...
    "UserContextService",
    "CESCPersonalizer",
]
```

### Step 3: Verify imports work

Run: `python -c "from telegram_bot.services import UserContextService, CESCPersonalizer; print('OK')"`
Expected: `OK`

### Step 4: Commit

```bash
git add telegram_bot/services/__init__.py
git commit -m "feat(cesc): export UserContextService and CESCPersonalizer"
```

---

## Task 4: Add CESC Configuration

**Files:**
- Modify: `telegram_bot/config.py`

### Step 1: Read current config structure

Run: `cat telegram_bot/config.py`

### Step 2: Add CESC settings to BotSettings class

Add these fields to the settings class:

```python
# CESC Configuration
cesc_enabled: bool = True
cesc_extraction_frequency: int = 3  # Extract preferences every N queries
user_context_ttl: int = 30 * 24 * 3600  # 30 days in seconds
```

### Step 3: Verify config loads

Run: `python -c "from telegram_bot.config import settings; print(f'CESC enabled: {settings.cesc_enabled}')"`
Expected: `CESC enabled: True`

### Step 4: Commit

```bash
git add telegram_bot/config.py
git commit -m "feat(cesc): add CESC configuration settings"
```

---

## Task 5: Integrate CESC into PropertyBot

**Files:**
- Modify: `telegram_bot/bot.py`

### Step 1: Read current bot.py to understand handle_query flow

Run: Examine `telegram_bot/bot.py`, specifically the `handle_query` method.

### Step 2: Add imports

Add at top of file:

```python
from .services import UserContextService, CESCPersonalizer
```

### Step 3: Initialize CESC services in __init__

Add after cache_service initialization:

```python
self.user_context_service = UserContextService(
    cache_service=self.cache_service,
    llm_service=self.llm_service,
)
self.cesc_personalizer = CESCPersonalizer(
    llm_service=self.llm_service,
)
```

### Step 4: Update handle_query method

In the `handle_query` method, after cache check and before returning cached response:

```python
# After getting cached_answer from cache_service.check_semantic_cache
if cached_answer:
    # CESC: Personalize if user has preferences
    user_context = await self.user_context_service.get_context(user_id)
    if self.cesc_personalizer.should_personalize(user_context):
        answer = await self.cesc_personalizer.personalize(
            cached_response=cached_answer,
            user_context=user_context,
            query=query,
        )
    else:
        answer = cached_answer
    # ... send answer
```

Also update context on every query:

```python
# At start of handle_query, after getting user_id and query
await self.user_context_service.update_from_query(user_id, query)
```

### Step 5: Run smoke test

Run: `python -c "from telegram_bot.bot import PropertyBot; print('Import OK')"`
Expected: `Import OK`

### Step 6: Commit

```bash
git add telegram_bot/bot.py
git commit -m "feat(cesc): integrate CESC into PropertyBot query handling"
```

---

## Task 6: Add Integration Tests

**Files:**
- Create: `tests/test_cesc_integration.py`

### Step 1: Write integration tests

```python
# tests/test_cesc_integration.py
"""Integration tests for CESC flow."""

import pytest
from unittest.mock import AsyncMock, MagicMock

from telegram_bot.services.user_context import UserContextService
from telegram_bot.services.cesc import CESCPersonalizer


class TestCESCIntegration:
    """Integration tests for full CESC flow."""

    @pytest.fixture
    def mock_cache_service(self):
        """Create mock cache service."""
        cache = MagicMock()
        cache.redis_client = AsyncMock()
        cache.redis_client.get = AsyncMock(return_value=None)
        cache.redis_client.setex = AsyncMock()
        return cache

    @pytest.fixture
    def mock_llm_service(self):
        """Create mock LLM service."""
        llm = MagicMock()
        llm.generate = AsyncMock(
            return_value='{"cities": ["Бургас"], "budget_max": 80000}'
        )
        return llm

    @pytest.mark.asyncio
    async def test_full_flow_new_user(
        self, mock_cache_service, mock_llm_service
    ):
        """Test complete flow for new user."""
        user_context_service = UserContextService(
            cache_service=mock_cache_service,
            llm_service=mock_llm_service,
        )

        # First query - should extract preferences
        context = await user_context_service.update_from_query(
            user_id=12345,
            query="квартиры в Бургасе до 80000",
        )

        assert context["interaction_count"] == 1
        assert "Бургас" in context["preferences"].get("cities", [])
        assert context["preferences"].get("budget_max") == 80000

    @pytest.mark.asyncio
    async def test_personalization_applied(self, mock_llm_service):
        """Test personalization is applied to cached response."""
        mock_llm_service.generate = AsyncMock(
            return_value="Персонализированный ответ для Бургаса"
        )
        personalizer = CESCPersonalizer(llm_service=mock_llm_service)

        user_context = {
            "user_id": 12345,
            "preferences": {
                "cities": ["Бургас"],
                "budget_max": 80000,
            },
            "profile_summary": "Ищет квартиры в Бургасе",
        }

        result = await personalizer.personalize(
            cached_response="Общая информация о недвижимости",
            user_context=user_context,
            query="расскажи о ценах",
        )

        assert "Персонализированный" in result
        mock_llm_service.generate.assert_called_once()

    @pytest.mark.asyncio
    async def test_personalization_skipped_no_prefs(self, mock_llm_service):
        """Test personalization skipped when no preferences."""
        personalizer = CESCPersonalizer(llm_service=mock_llm_service)

        user_context = {"user_id": 12345, "preferences": {}}
        cached = "Оригинальный ответ"

        result = await personalizer.personalize(
            cached_response=cached,
            user_context=user_context,
            query="вопрос",
        )

        assert result == cached
        mock_llm_service.generate.assert_not_called()
```

### Step 2: Run integration tests

Run: `pytest tests/test_cesc_integration.py -v`
Expected: All 3 tests PASS

### Step 3: Run full test suite

Run: `pytest tests/test_user_context.py tests/test_cesc.py tests/test_cesc_integration.py -v`
Expected: All 19 tests PASS

### Step 4: Commit

```bash
git add tests/test_cesc_integration.py
git commit -m "test(cesc): add integration tests for CESC flow"
```

---

## Task 7: Run Full QA and Final Commit

### Step 1: Run linting

Run: `make lint`
Expected: No errors

### Step 2: Run type checking

Run: `make type-check`
Expected: No errors (or pre-existing errors only)

### Step 3: Run all tests

Run: `make test`
Expected: All tests pass

### Step 4: Final integration test with bot

Run: `python -c "from telegram_bot.bot import PropertyBot; print('Bot loads OK')"`
Expected: `Bot loads OK`

### Step 5: Create summary commit if any fixes were needed

```bash
git add -A
git commit -m "chore(cesc): finalize CESC implementation"
```

---

## Success Criteria

- [ ] `UserContextService` stores/retrieves context from Redis
- [ ] Preferences extracted every 3rd query via LLM
- [ ] `CESCPersonalizer` personalizes cached responses
- [ ] Integration into `PropertyBot.handle_query` complete
- [ ] All unit tests pass (19 tests)
- [ ] Linting and type checking pass
- [ ] Bot imports and initializes correctly

## References

- [Redis CESC Blog](https://redis.io/blog/building-a-context-enabled-semantic-cache-with-redis/)
- [Mem0 Memory Library](https://github.com/mem0ai/mem0)
- [LangMem by LangChain](https://github.com/langchain-ai/langmem)

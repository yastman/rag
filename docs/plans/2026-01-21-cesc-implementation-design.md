# CESC Implementation Design Plan

**Date:** 2026-01-21
**Status:** Ready for Implementation
**Author:** Claude + User

## 1. Overview

Реализация Context-Enabled Semantic Cache (CESC) для персонализации кешированных ответов в Telegram боте по недвижимости Болгарии.

### Цель

При cache HIT — персонализировать generic ответ под контекст пользователя через Cerebras LLM (~100ms, ~100 токенов).

### Ожидаемые результаты

| Метрика | Без CESC | С CESC |
|---------|----------|--------|
| Cache HIT latency | <1ms (generic) | ~100ms (personalized) |
| Токены на HIT | 0 | ~100 |
| Персонализация | Нет | Да |
| User satisfaction | Базовый | Повышенный |

---

## 2. Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                         USER QUERY                              │
└───────────────────────────┬─────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│  1. UPDATE USER CONTEXT                                         │
│     └── Every 3rd query: LLM extracts preferences               │
│     └── Store in Redis JSON (TTL: 30 days)                      │
└───────────────────────────┬─────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│  2. SEMANTIC CACHE CHECK                                        │
│     └── langcache-embed-v1 (256-dim)                            │
│     └── filter: user_id + language                              │
└───────────────────────────┬─────────────────────────────────────┘
                            │
              ┌─────────────┴─────────────┐
              │                           │
           HIT ▼                       MISS ▼
┌─────────────────────────┐   ┌─────────────────────────┐
│  3. CESC PERSONALIZE    │   │  4. FULL RAG PIPELINE   │
│     └── Cerebras LLM    │   │     └── BGE-M3 embed    │
│     └── ~100 tokens     │   │     └── Qdrant search   │
│     └── ~100ms          │   │     └── Cerebras LLM    │
└───────────────────────────┘ │     └── 2-3s           │
              │                 └───────────┬─────────────┘
              │                             │
              │                             ▼
              │                 ┌─────────────────────────┐
              │                 │  5. STORE IN CACHE      │
              │                 │     └── + user context  │
              │                 └───────────┬─────────────┘
              │                             │
              └──────────────┬──────────────┘
                             ▼
                    [PERSONALIZED RESPONSE]
```

---

## 3. User Context Schema

### 3.1 Full Schema

```python
user_context = {
    # === Identity ===
    "user_id": 12345,
    "language": "ru",
    "created_at": "2026-01-15T10:00:00Z",
    "updated_at": "2026-01-21T14:30:00Z",

    # === Extracted Preferences (LLM-generated) ===
    "preferences": {
        "cities": ["Солнечный берег", "Несебр", "Бургас"],
        "budget_min": 50000,
        "budget_max": 100000,
        "property_types": ["apartment", "studio"],
        "distance_to_sea_max": 500,
        "rooms_min": 1,
        "rooms_max": 3,
    },

    # === Profile Summary (LLM-generated) ===
    "profile_summary": "Ищет 2-комнатные квартиры у моря до 100к€",

    # === Interaction Stats ===
    "interaction_count": 15,
    "last_queries": [
        "квартиры в Солнечном береге",
        "студии до 60000 евро",
        "2-комнатные у моря",
    ],
}
```

### 3.2 Storage

- **Key:** `user_context:{user_id}`
- **Type:** Redis JSON
- **TTL:** 30 days (2592000 seconds)

---

## 4. Components

### 4.1 UserContextService

**File:** `telegram_bot/services/user_context.py`

**Responsibilities:**
- Get/store user context in Redis
- Extract preferences via LLM (every 3rd query)
- Generate profile summary
- Merge preferences incrementally

**Key Methods:**

```python
class UserContextService:
    async def get_context(self, user_id: int) -> dict
    async def update_from_query(self, user_id: int, query: str) -> dict
    async def _extract_preferences(self, query: str, current: dict) -> dict
    def _merge_preferences(self, old: dict, new: dict) -> dict
    async def _generate_summary(self, context: dict) -> str
```

### 4.2 CESCPersonalizer

**File:** `telegram_bot/services/cesc.py`

**Responsibilities:**
- Personalize cached responses using user context
- Use Cerebras LLM (same provider as main LLM)
- Keep responses concise (~100 tokens)

**Key Methods:**

```python
class CESCPersonalizer:
    async def personalize(
        self,
        cached_response: str,
        user_context: dict,
        query: str,
    ) -> str
```

---

## 5. Prompts

### 5.1 Preference Extraction Prompt

```
Проанализируй запрос пользователя и извлеки/обнови предпочтения:

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
- Верни ТОЛЬКО JSON без пояснений
```

### 5.2 CESC Personalization Prompt (Structured, ~100 tokens)

```
Персонализируй ответ под пользователя:

ОТВЕТ: {cached_response}

КОНТЕКСТ:
- Города: {preferences.cities}
- Бюджет: до {preferences.budget_max}€
- Тип: {preferences.property_types}
- История: {profile_summary}

Сохрани факты, адаптируй подачу. Русский язык.
```

---

## 6. Implementation Plan

### Task 1: Create UserContextService

**File:** `telegram_bot/services/user_context.py`

```python
"""User context management with LLM-based preference extraction."""

import json
import logging
from datetime import datetime
from typing import Any, Optional

logger = logging.getLogger(__name__)


class UserContextService:
    """Manages user context with LLM-based preference extraction."""

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

    def __init__(self, cache_service, llm_service):
        """Initialize with cache and LLM services."""
        self.cache = cache_service
        self.llm = llm_service
        self.context_ttl = 30 * 24 * 3600  # 30 days

    async def get_context(self, user_id: int) -> dict[str, Any]:
        """Get full user context from Redis."""
        if not self.cache.redis_client:
            return self._default_context(user_id)

        key = f"user_context:{user_id}"
        data = await self.cache.redis_client.get(key)

        if data:
            return json.loads(data)

        return self._default_context(user_id)

    def _default_context(self, user_id: int) -> dict[str, Any]:
        """Return default context for new users."""
        return {
            "user_id": user_id,
            "language": "ru",
            "preferences": {},
            "profile_summary": "",
            "interaction_count": 0,
            "last_queries": [],
            "created_at": datetime.utcnow().isoformat(),
            "updated_at": datetime.utcnow().isoformat(),
        }

    async def update_from_query(self, user_id: int, query: str) -> dict[str, Any]:
        """Extract preferences from query and update context."""
        context = await self.get_context(user_id)

        # Update interaction stats
        context["interaction_count"] += 1
        context["last_queries"] = [query] + context["last_queries"][:4]
        context["updated_at"] = datetime.utcnow().isoformat()

        # Extract preferences every 3rd query or if empty
        should_extract = (
            context["interaction_count"] % 3 == 1
            or not context["preferences"]
        )

        if should_extract:
            try:
                new_prefs = await self._extract_preferences(
                    query, context["preferences"]
                )
                context["preferences"] = self._merge_preferences(
                    context["preferences"], new_prefs
                )
                logger.info(f"Extracted preferences for user {user_id}: {new_prefs}")
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
        """Use LLM to extract preferences from query."""
        prompt = self.EXTRACTION_PROMPT.format(
            current_preferences=json.dumps(current, ensure_ascii=False),
            query=query,
        )

        response = await self.llm.generate(prompt, max_tokens=200)

        # Parse JSON from response
        response_clean = response.strip()
        # Handle markdown code blocks
        if response_clean.startswith("```"):
            response_clean = response_clean.split("```")[1]
            if response_clean.startswith("json"):
                response_clean = response_clean[4:]

        return json.loads(response_clean)

    def _merge_preferences(
        self, old: dict[str, Any], new: dict[str, Any]
    ) -> dict[str, Any]:
        """Merge new preferences with existing ones."""
        merged = old.copy()

        for key, value in new.items():
            if value is None:
                continue
            if key == "cities" and isinstance(value, list):
                # Merge cities, deduplicate
                existing = set(merged.get("cities", []))
                merged["cities"] = list(existing | set(value))
            else:
                merged[key] = value

        return merged

    def _generate_summary(self, context: dict[str, Any]) -> str:
        """Generate profile summary from preferences."""
        prefs = context["preferences"]
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

    async def _save_context(self, user_id: int, context: dict[str, Any]):
        """Save context to Redis."""
        if not self.cache.redis_client:
            return

        key = f"user_context:{user_id}"
        await self.cache.redis_client.setex(
            key,
            self.context_ttl,
            json.dumps(context, ensure_ascii=False),
        )
```

---

### Task 2: Create CESCPersonalizer

**File:** `telegram_bot/services/cesc.py`

```python
"""Context-Enabled Semantic Cache (CESC) personalizer."""

import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)


class CESCPersonalizer:
    """Personalizes cached responses using user context."""

    PERSONALIZATION_PROMPT = """Персонализируй ответ под пользователя:

ОТВЕТ: {cached_response}

КОНТЕКСТ:
- Города: {cities}
- Бюджет: до {budget}€
- Тип: {property_types}
- История: {profile_summary}

Сохрани факты, адаптируй подачу. Русский язык."""

    def __init__(self, llm_service):
        """Initialize with LLM service (Cerebras)."""
        self.llm = llm_service

    async def personalize(
        self,
        cached_response: str,
        user_context: dict[str, Any],
        query: str,
    ) -> str:
        """Personalize cached response using user context.

        Args:
            cached_response: Generic cached answer
            user_context: User preferences and history
            query: Current user query

        Returns:
            Personalized response
        """
        prefs = user_context.get("preferences", {})

        # If no preferences, return cached response as-is
        if not prefs:
            logger.debug("No user preferences, returning cached response")
            return cached_response

        # Build personalization prompt
        prompt = self.PERSONALIZATION_PROMPT.format(
            cached_response=cached_response[:500],  # Limit to 500 chars
            cities=", ".join(prefs.get("cities", ["любой"])),
            budget=prefs.get("budget_max", "не указан"),
            property_types=", ".join(prefs.get("property_types", ["любой"])),
            profile_summary=user_context.get("profile_summary", "новый пользователь"),
        )

        try:
            personalized = await self.llm.generate(prompt, max_tokens=300)
            logger.info(
                f"CESC personalized response for user {user_context.get('user_id')}"
            )
            return personalized.strip()
        except Exception as e:
            logger.error(f"CESC personalization failed: {e}")
            return cached_response  # Fallback to cached

    def should_personalize(self, user_context: dict[str, Any]) -> bool:
        """Check if personalization should be applied.

        Returns True if user has meaningful preferences.
        """
        prefs = user_context.get("preferences", {})
        return bool(
            prefs.get("cities")
            or prefs.get("budget_max")
            or prefs.get("property_types")
            or prefs.get("rooms")
        )
```

---

### Task 3: Update Services __init__.py

**File:** `telegram_bot/services/__init__.py`

Add exports:

```python
from .user_context import UserContextService
from .cesc import CESCPersonalizer
```

---

### Task 4: Integrate into PropertyBot

**File:** `telegram_bot/bot.py`

**Changes:**

1. Add imports:
```python
from .services import UserContextService, CESCPersonalizer
```

2. Initialize services in `__init__`:
```python
self.user_context_service = UserContextService(
    cache_service=self.cache_service,
    llm_service=self.llm_service,
)
self.cesc_personalizer = CESCPersonalizer(
    llm_service=self.llm_service,
)
```

3. Update `handle_query` method:
```python
async def handle_query(self, message: Message):
    user_id = message.from_user.id
    query = message.text

    # Initialize cache on first query
    if not self._cache_initialized:
        await self.cache_service.initialize()
        self._cache_initialized = True

    await message.bot.send_chat_action(message.chat.id, "typing")

    # 1. Update user context (extracts preferences every 3rd query)
    user_context = await self.user_context_service.update_from_query(
        user_id, query
    )

    # 2. Check semantic cache
    cached_answer = await self.cache_service.check_semantic_cache(
        query,
        user_id=user_id,
        language=user_context.get("language", "ru"),
    )

    if cached_answer:
        # 3. CESC: Personalize if user has preferences
        if self.cesc_personalizer.should_personalize(user_context):
            answer = await self.cesc_personalizer.personalize(
                cached_response=cached_answer,
                user_context=user_context,
                query=query,
            )
        else:
            answer = cached_answer

        await message.answer(answer)
        self.cache_service.log_metrics()
        return

    # ... rest of RAG pipeline unchanged
```

---

### Task 5: Add Configuration

**File:** `.env`

```bash
# CESC Configuration
CESC_ENABLED=true
CESC_EXTRACTION_FREQUENCY=3  # Extract preferences every N queries
USER_CONTEXT_TTL=2592000     # 30 days in seconds
```

**File:** `telegram_bot/config.py`

Add:
```python
cesc_enabled: bool = True
cesc_extraction_frequency: int = 3
user_context_ttl: int = 30 * 24 * 3600
```

---

### Task 6: Add Tests

**File:** `tests/test_cesc.py`

```python
"""Tests for CESC components."""

import pytest
from telegram_bot.services.user_context import UserContextService
from telegram_bot.services.cesc import CESCPersonalizer


class TestUserContextService:
    def test_merge_preferences_cities(self):
        service = UserContextService(None, None)
        old = {"cities": ["Бургас"]}
        new = {"cities": ["Несебр", "Бургас"]}
        merged = service._merge_preferences(old, new)
        assert set(merged["cities"]) == {"Бургас", "Несебр"}

    def test_merge_preferences_budget(self):
        service = UserContextService(None, None)
        old = {"budget_max": 100000}
        new = {"budget_max": 80000}
        merged = service._merge_preferences(old, new)
        assert merged["budget_max"] == 80000

    def test_generate_summary(self):
        service = UserContextService(None, None)
        context = {
            "preferences": {
                "cities": ["Бургас", "Несебр"],
                "budget_max": 100000,
                "rooms": 2,
            }
        }
        summary = service._generate_summary(context)
        assert "Бургас" in summary
        assert "100000" in summary


class TestCESCPersonalizer:
    def test_should_personalize_with_prefs(self):
        personalizer = CESCPersonalizer(None)
        context = {"preferences": {"cities": ["Бургас"]}}
        assert personalizer.should_personalize(context) is True

    def test_should_personalize_empty(self):
        personalizer = CESCPersonalizer(None)
        context = {"preferences": {}}
        assert personalizer.should_personalize(context) is False
```

---

## 7. Metrics & Monitoring

### 7.1 New Metrics

```python
metrics = {
    "cesc": {
        "personalizations": 0,      # Total CESC calls
        "skipped": 0,               # No preferences, skipped
        "errors": 0,                # Personalization failures
        "avg_latency_ms": 0,        # Average personalization time
    },
    "user_context": {
        "extractions": 0,           # LLM preference extractions
        "extraction_errors": 0,     # Failed extractions
        "contexts_stored": 0,       # Unique users with context
    },
}
```

### 7.2 Logging

```python
# On CESC personalization
logger.info(f"CESC: personalized for user {user_id} in {latency_ms}ms")

# On preference extraction
logger.info(f"Extracted preferences for user {user_id}: {new_prefs}")

# On cache hit without personalization
logger.debug(f"Cache HIT for user {user_id}, no preferences to personalize")
```

---

## 8. Rollout Plan

### Phase 1: Implementation (Day 1-2)
- [ ] Create `UserContextService`
- [ ] Create `CESCPersonalizer`
- [ ] Update `services/__init__.py`
- [ ] Add unit tests

### Phase 2: Integration (Day 2-3)
- [ ] Integrate into `PropertyBot`
- [ ] Add configuration
- [ ] Test end-to-end flow

### Phase 3: Testing (Day 3-4)
- [ ] Manual testing with real queries
- [ ] Verify preference extraction
- [ ] Verify personalization quality
- [ ] Performance benchmarks

### Phase 4: Monitoring (Day 4-5)
- [ ] Add metrics collection
- [ ] Set up logging
- [ ] Monitor cache hit rates
- [ ] Monitor personalization latency

---

## 9. Success Criteria

- [ ] User context stored in Redis (`user_context:*` keys exist)
- [ ] Preferences extracted from queries (every 3rd query)
- [ ] CESC personalization works on cache HIT
- [ ] Personalization latency < 150ms
- [ ] No regression in RAG pipeline
- [ ] All tests pass

---

## 10. References

- [Redis CESC Blog](https://redis.io/blog/building-a-context-enabled-semantic-cache-with-redis/)
- [Mem0 Memory Library](https://github.com/mem0ai/mem0)
- [LangMem by LangChain](https://github.com/langchain-ai/langmem)
- [RedisVL SemanticCache](https://docs.redisvl.com/)
- [Personalized RAG Survey](https://arxiv.org/abs/2504.10147)

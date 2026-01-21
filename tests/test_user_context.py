"""Tests for UserContextService."""

import importlib.util
from pathlib import Path

import pytest


# Direct import to avoid __init__.py dependency chain
_module_path = Path(__file__).parent.parent / "telegram_bot" / "services" / "user_context.py"
_spec = importlib.util.spec_from_file_location("user_context", _module_path)
_module = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_module)
UserContextService = _module.UserContextService


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

        assert not service._should_extract(interaction_count=2, preferences={"cities": ["Бургас"]})
        assert not service._should_extract(interaction_count=3, preferences={"cities": ["Бургас"]})

    def test_should_extract_every_third_query(self):
        """Test extraction triggers every 3rd query (count % 3 == 1)."""
        service = UserContextService(cache_service=None, llm_service=None)
        prefs = {"cities": ["Бургас"]}

        # Should extract on queries 1, 4, 7, 10...
        assert service._should_extract(interaction_count=1, preferences=prefs)
        assert service._should_extract(interaction_count=4, preferences=prefs)
        assert service._should_extract(interaction_count=7, preferences=prefs)
        assert service._should_extract(interaction_count=10, preferences=prefs)

        # Should NOT extract on queries 2, 3, 5, 6, 8, 9...
        assert not service._should_extract(interaction_count=2, preferences=prefs)
        assert not service._should_extract(interaction_count=3, preferences=prefs)
        assert not service._should_extract(interaction_count=5, preferences=prefs)
        assert not service._should_extract(interaction_count=6, preferences=prefs)

    def test_merge_preferences_empty_old(self):
        """Test merging when old preferences are empty."""
        service = UserContextService(cache_service=None, llm_service=None)
        old = {}
        new = {"cities": ["Варна"], "budget_max": 50000}

        merged = service._merge_preferences(old, new)

        assert merged["cities"] == ["Варна"]
        assert merged["budget_max"] == 50000

    def test_merge_preferences_empty_new(self):
        """Test merging when new preferences are empty."""
        service = UserContextService(cache_service=None, llm_service=None)
        old = {"cities": ["Бургас"], "budget_max": 100000}
        new = {}

        merged = service._merge_preferences(old, new)

        assert merged["cities"] == ["Бургас"]
        assert merged["budget_max"] == 100000

    def test_generate_summary_partial(self):
        """Test summary generation with partial preferences."""
        service = UserContextService(cache_service=None, llm_service=None)
        context = {
            "preferences": {
                "cities": ["София"],
                "rooms": 3,
            }
        }

        summary = service._generate_summary(context)

        assert "София" in summary
        assert "3-комнатные" in summary
        # Should not contain budget or property types
        assert "€" not in summary
        assert "Тип:" not in summary


class TestUserContextServiceAsync:
    """Async tests for UserContextService."""

    @pytest.mark.asyncio
    async def test_get_context_without_cache(self):
        """Test get_context returns default when cache is None."""
        service = UserContextService(cache_service=None, llm_service=None)
        context = await service.get_context(user_id=12345)

        assert context["user_id"] == 12345
        assert context["preferences"] == {}

    @pytest.mark.asyncio
    async def test_get_context_without_redis_client(self):
        """Test get_context returns default when redis_client is None."""

        class MockCache:
            redis_client = None

        service = UserContextService(cache_service=MockCache(), llm_service=None)
        context = await service.get_context(user_id=12345)

        assert context["user_id"] == 12345
        assert context["preferences"] == {}

    @pytest.mark.asyncio
    async def test_save_context_without_cache(self):
        """Test _save_context handles None cache gracefully."""
        service = UserContextService(cache_service=None, llm_service=None)
        context = service._default_context(user_id=12345)

        # Should not raise
        await service._save_context(user_id=12345, context=context)

    @pytest.mark.asyncio
    async def test_update_from_query_increments_count(self):
        """Test update_from_query increments interaction count."""
        service = UserContextService(cache_service=None, llm_service=None)

        context = await service.update_from_query(user_id=12345, query="квартира в Бургасе")

        assert context["interaction_count"] == 1
        assert "квартира в Бургасе" in context["last_queries"]

    @pytest.mark.asyncio
    async def test_update_from_query_stores_last_queries(self):
        """Test update_from_query maintains last 5 queries (with mock cache)."""

        class MockRedisClient:
            """Mock Redis client for testing context persistence."""

            def __init__(self):
                self.store = {}

            async def get(self, key: str):
                return self.store.get(key)

            async def setex(self, key: str, ttl: int, value: str):
                self.store[key] = value

        class MockCache:
            def __init__(self):
                self.redis_client = MockRedisClient()

        service = UserContextService(cache_service=MockCache(), llm_service=None)

        # Simulate 6 queries
        for i in range(6):
            context = await service.update_from_query(user_id=12345, query=f"запрос {i + 1}")

        # Should only keep last 5
        assert len(context["last_queries"]) == 5
        assert context["last_queries"][0] == "запрос 6"
        assert context["last_queries"][4] == "запрос 2"

    @pytest.mark.asyncio
    async def test_update_from_query_no_cache_single_query(self):
        """Test update_from_query handles single query without cache."""
        service = UserContextService(cache_service=None, llm_service=None)

        context = await service.update_from_query(user_id=12345, query="квартира в Бургасе")

        # Without cache, only current query is in context
        assert context["interaction_count"] == 1
        assert len(context["last_queries"]) == 1
        assert context["last_queries"][0] == "квартира в Бургасе"

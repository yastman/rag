"""Tests for UserContextService."""

import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from telegram_bot.services.user_context import UserContextService


class TestUserContextServiceInit:
    """Tests for UserContextService initialization."""

    def test_init_with_defaults(self):
        """Test initialization with default values."""
        mock_cache = MagicMock()
        mock_llm = MagicMock()

        service = UserContextService(cache_service=mock_cache, llm_service=mock_llm)

        assert service.cache is mock_cache
        assert service.llm is mock_llm
        assert service.context_ttl == 30 * 24 * 3600  # 30 days
        assert service.extraction_frequency == 3

    def test_init_with_custom_values(self):
        """Test initialization with custom values."""
        mock_cache = MagicMock()
        mock_llm = MagicMock()

        service = UserContextService(
            cache_service=mock_cache,
            llm_service=mock_llm,
            context_ttl=7200,
            extraction_frequency=5,
        )

        assert service.context_ttl == 7200
        assert service.extraction_frequency == 5


class TestUserContextServiceGetContext:
    """Tests for get_context method."""

    @pytest.fixture
    def mock_cache(self):
        cache = MagicMock()
        cache.redis_client = AsyncMock()
        return cache

    @pytest.fixture
    def mock_llm(self):
        return MagicMock()

    @pytest.fixture
    def service(self, mock_cache, mock_llm):
        return UserContextService(cache_service=mock_cache, llm_service=mock_llm)

    @pytest.mark.asyncio
    async def test_get_context_new_user(self, service, mock_cache):
        """Test getting context for new user returns default."""
        mock_cache.redis_client.get = AsyncMock(return_value=None)

        result = await service.get_context(user_id=123)

        assert result["user_id"] == 123
        assert result["language"] == "ru"
        assert result["preferences"] == {}
        assert result["interaction_count"] == 0

    @pytest.mark.asyncio
    async def test_get_context_existing_user(self, service, mock_cache):
        """Test getting context for existing user."""
        stored_context = {
            "user_id": 123,
            "language": "ru",
            "preferences": {"cities": ["Бургас"]},
            "interaction_count": 5,
            "last_queries": ["test query"],
            "profile_summary": "",
            "created_at": "2025-01-01T00:00:00Z",
            "updated_at": "2025-01-01T00:00:00Z",
        }
        mock_cache.redis_client.get = AsyncMock(return_value=json.dumps(stored_context))

        result = await service.get_context(user_id=123)

        assert result["user_id"] == 123
        assert result["preferences"]["cities"] == ["Бургас"]
        assert result["interaction_count"] == 5

    @pytest.mark.asyncio
    async def test_get_context_no_cache(self, mock_llm):
        """Test get_context returns default when cache is None."""
        service = UserContextService(cache_service=None, llm_service=mock_llm)

        result = await service.get_context(user_id=123)

        assert result["user_id"] == 123
        assert result["preferences"] == {}

    @pytest.mark.asyncio
    async def test_get_context_no_redis_client(self, mock_llm):
        """Test get_context returns default when redis_client is None."""
        mock_cache = MagicMock()
        mock_cache.redis_client = None
        service = UserContextService(cache_service=mock_cache, llm_service=mock_llm)

        result = await service.get_context(user_id=123)

        assert result["user_id"] == 123
        assert result["preferences"] == {}

    @pytest.mark.asyncio
    async def test_get_context_redis_error(self, service, mock_cache):
        """Test get_context handles Redis errors gracefully."""
        mock_cache.redis_client.get = AsyncMock(side_effect=Exception("Redis error"))

        result = await service.get_context(user_id=123)

        # Should return default context on error
        assert result["user_id"] == 123
        assert result["preferences"] == {}


class TestUserContextServiceUpdateFromQuery:
    """Tests for update_from_query method."""

    @pytest.fixture
    def mock_cache(self):
        cache = MagicMock()
        cache.redis_client = AsyncMock()
        cache.redis_client.get = AsyncMock(return_value=None)
        cache.redis_client.setex = AsyncMock()
        return cache

    @pytest.fixture
    def mock_llm(self):
        llm = MagicMock()
        llm.generate = AsyncMock(return_value='{"cities": ["Бургас"], "budget_max": 100000}')
        return llm

    @pytest.fixture
    def service(self, mock_cache, mock_llm):
        return UserContextService(cache_service=mock_cache, llm_service=mock_llm)

    @pytest.mark.asyncio
    async def test_update_from_query_increments_count(self, service, mock_cache):
        """Test that update_from_query increments interaction count."""
        result = await service.update_from_query(user_id=123, query="test query")

        assert result["interaction_count"] == 1

    @pytest.mark.asyncio
    async def test_update_from_query_stores_query(self, service, mock_cache):
        """Test that update_from_query stores query in last_queries."""
        result = await service.update_from_query(user_id=123, query="квартиры в Бургасе")

        assert "квартиры в Бургасе" in result["last_queries"]

    @pytest.mark.asyncio
    async def test_update_from_query_extracts_on_first(self, service, mock_llm):
        """Test that preferences are extracted on first query."""
        await service.update_from_query(user_id=123, query="квартиры в Бургасе")

        # First query (count=1, 1 % 3 == 1) should trigger extraction
        mock_llm.generate.assert_called_once()

    @pytest.mark.asyncio
    async def test_update_from_query_extracts_every_third(self, service, mock_cache, mock_llm):
        """Test that preferences are extracted every 3rd query."""
        # Simulate user with 3 interactions (next will be 4th, then 5th...)
        stored_context = {
            "user_id": 123,
            "language": "ru",
            "preferences": {"cities": ["Бургас"]},
            "interaction_count": 3,
            "last_queries": [],
            "profile_summary": "",
            "created_at": "2025-01-01T00:00:00Z",
            "updated_at": "2025-01-01T00:00:00Z",
        }
        mock_cache.redis_client.get = AsyncMock(return_value=json.dumps(stored_context))

        # 4th query (4 % 3 == 1) should trigger extraction
        await service.update_from_query(user_id=123, query="дома в Несебре")

        mock_llm.generate.assert_called_once()

    @pytest.mark.asyncio
    async def test_update_from_query_skips_extraction_on_second(
        self, service, mock_cache, mock_llm
    ):
        """Test that preferences extraction is skipped on 2nd query."""
        stored_context = {
            "user_id": 123,
            "language": "ru",
            "preferences": {"cities": ["Бургас"]},
            "interaction_count": 1,
            "last_queries": [],
            "profile_summary": "",
            "created_at": "2025-01-01T00:00:00Z",
            "updated_at": "2025-01-01T00:00:00Z",
        }
        mock_cache.redis_client.get = AsyncMock(return_value=json.dumps(stored_context))

        # 2nd query (2 % 3 == 2) should NOT trigger extraction
        await service.update_from_query(user_id=123, query="test")

        mock_llm.generate.assert_not_called()

    @pytest.mark.asyncio
    async def test_update_from_query_merges_preferences(self, service, mock_cache, mock_llm):
        """Test that new preferences are merged with existing."""
        stored_context = {
            "user_id": 123,
            "language": "ru",
            "preferences": {"cities": ["Бургас"]},
            "interaction_count": 0,
            "last_queries": [],
            "profile_summary": "",
            "created_at": "2025-01-01T00:00:00Z",
            "updated_at": "2025-01-01T00:00:00Z",
        }
        mock_cache.redis_client.get = AsyncMock(return_value=json.dumps(stored_context))
        mock_llm.generate = AsyncMock(return_value='{"cities": ["Несебр"], "budget_max": 50000}')

        result = await service.update_from_query(user_id=123, query="дома в Несебре до 50000")

        # Cities should be merged
        assert "Бургас" in result["preferences"]["cities"]
        assert "Несебр" in result["preferences"]["cities"]
        assert result["preferences"]["budget_max"] == 50000

    @pytest.mark.asyncio
    async def test_update_from_query_handles_llm_error(self, service, mock_llm):
        """Test that LLM errors are handled gracefully."""
        mock_llm.generate = AsyncMock(side_effect=Exception("LLM error"))

        # Should not raise
        result = await service.update_from_query(user_id=123, query="test query")

        assert result["interaction_count"] == 1

    @pytest.mark.asyncio
    async def test_update_from_query_generates_summary_after_5(self, service, mock_cache, mock_llm):
        """Test that profile summary is generated after 5 interactions."""
        stored_context = {
            "user_id": 123,
            "language": "ru",
            "preferences": {"cities": ["Бургас"], "budget_max": 100000},
            "interaction_count": 3,
            "last_queries": [],
            "profile_summary": "",
            "created_at": "2025-01-01T00:00:00Z",
            "updated_at": "2025-01-01T00:00:00Z",
        }
        mock_cache.redis_client.get = AsyncMock(return_value=json.dumps(stored_context))

        # 4th query triggers extraction (4 % 3 == 1)
        result = await service.update_from_query(user_id=123, query="test")

        # After 5+ interactions, summary should be generated
        # (count was 3, now 4, but summary is generated when >= 5)
        # Let's test with count=4 (next will be 5)
        stored_context["interaction_count"] = 4
        mock_cache.redis_client.get = AsyncMock(return_value=json.dumps(stored_context))

        result = await service.update_from_query(user_id=123, query="test")

        # Now count=5, and since 5 % 3 != 1, no extraction, no summary update
        # Let's test with count=6 (7 % 3 == 1 triggers extraction)
        stored_context["interaction_count"] = 6
        mock_cache.redis_client.get = AsyncMock(return_value=json.dumps(stored_context))

        result = await service.update_from_query(user_id=123, query="test")

        # count=7 >= 5 and 7 % 3 == 1, so summary should be generated
        assert result["profile_summary"] != ""


class TestUserContextServiceHelpers:
    """Tests for helper methods."""

    @pytest.fixture
    def service(self):
        return UserContextService(cache_service=MagicMock(), llm_service=MagicMock())

    def test_default_context(self, service):
        """Test _default_context returns correct structure."""
        context = service._default_context(user_id=123)

        assert context["user_id"] == 123
        assert context["language"] == "ru"
        assert context["preferences"] == {}
        assert context["profile_summary"] == ""
        assert context["interaction_count"] == 0
        assert context["last_queries"] == []
        assert "created_at" in context
        assert "updated_at" in context

    def test_merge_preferences_cities(self, service):
        """Test _merge_preferences merges cities."""
        old = {"cities": ["Бургас", "Варна"]}
        new = {"cities": ["Несебр", "Бургас"]}

        result = service._merge_preferences(old, new)

        assert set(result["cities"]) == {"Бургас", "Варна", "Несебр"}

    def test_merge_preferences_overwrites_scalar(self, service):
        """Test _merge_preferences overwrites scalar values."""
        old = {"budget_max": 50000, "rooms": 1}
        new = {"budget_max": 100000}

        result = service._merge_preferences(old, new)

        assert result["budget_max"] == 100000
        assert result["rooms"] == 1

    def test_merge_preferences_ignores_none(self, service):
        """Test _merge_preferences ignores None values."""
        old = {"budget_max": 50000}
        new = {"budget_max": None, "rooms": 2}

        result = service._merge_preferences(old, new)

        assert result["budget_max"] == 50000
        assert result["rooms"] == 2

    def test_generate_summary_with_preferences(self, service):
        """Test _generate_summary generates correct summary."""
        context = {
            "preferences": {
                "cities": ["Бургас", "Несебр"],
                "budget_max": 100000,
                "rooms": 2,
                "property_types": ["apartment"],
            }
        }

        result = service._generate_summary(context)

        assert "Бургас" in result
        assert "100000€" in result
        assert "2-комнатные" in result
        assert "apartment" in result

    def test_generate_summary_empty_preferences(self, service):
        """Test _generate_summary with empty preferences."""
        context = {"preferences": {}}

        result = service._generate_summary(context)

        assert result == "Новый пользователь"

    def test_should_extract_first_query(self, service):
        """Test _should_extract returns True for first query."""
        assert service._should_extract(interaction_count=1, preferences={}) is True

    def test_should_extract_empty_preferences(self, service):
        """Test _should_extract returns True for empty preferences."""
        assert service._should_extract(interaction_count=2, preferences={}) is True

    def test_should_extract_every_third(self, service):
        """Test _should_extract returns True every 3rd query."""
        assert service._should_extract(interaction_count=1, preferences={"cities": []}) is True
        assert service._should_extract(interaction_count=2, preferences={"cities": []}) is False
        assert service._should_extract(interaction_count=3, preferences={"cities": []}) is False
        assert service._should_extract(interaction_count=4, preferences={"cities": []}) is True


class TestUserContextServiceExtractPreferences:
    """Tests for _extract_preferences method."""

    @pytest.fixture
    def mock_llm(self):
        return MagicMock()

    @pytest.fixture
    def service(self, mock_llm):
        return UserContextService(cache_service=MagicMock(), llm_service=mock_llm)

    @pytest.mark.asyncio
    async def test_extract_preferences_basic(self, service, mock_llm):
        """Test basic preference extraction."""
        mock_llm.generate = AsyncMock(return_value='{"cities": ["Бургас"], "budget_max": 50000}')

        result = await service._extract_preferences("квартиры в Бургасе до 50000", {})

        assert result["cities"] == ["Бургас"]
        assert result["budget_max"] == 50000

    @pytest.mark.asyncio
    async def test_extract_preferences_with_markdown(self, service, mock_llm):
        """Test extraction handles markdown code blocks."""
        mock_llm.generate = AsyncMock(return_value='```json\n{"cities": ["Несебр"]}\n```')

        result = await service._extract_preferences("test", {})

        assert result["cities"] == ["Несебр"]

    @pytest.mark.asyncio
    async def test_extract_preferences_invalid_json(self, service, mock_llm):
        """Test extraction raises on invalid JSON."""
        import json

        mock_llm.generate = AsyncMock(return_value="not valid json")

        with pytest.raises(json.JSONDecodeError):
            await service._extract_preferences("test", {})

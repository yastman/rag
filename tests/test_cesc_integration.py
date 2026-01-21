"""Integration tests for CESC flow."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from telegram_bot.services.cesc import CESCPersonalizer
from telegram_bot.services.user_context import UserContextService


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
        llm.generate = AsyncMock(return_value='{"cities": ["Бургас"], "budget_max": 80000}')
        return llm

    @pytest.mark.asyncio
    async def test_full_flow_new_user(self, mock_cache_service, mock_llm_service):
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
        mock_llm_service.generate = AsyncMock(return_value="Персонализированный ответ для Бургаса")
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

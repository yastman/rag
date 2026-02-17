"""Integration tests for bot hybrid search pipeline."""

import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# Mock aiogram before importing bot
mock_aiogram = MagicMock()
mock_aiogram.Bot = MagicMock()
mock_aiogram.Dispatcher = MagicMock()
mock_aiogram.F = MagicMock()
sys.modules["aiogram"] = mock_aiogram
sys.modules["aiogram.filters"] = MagicMock()
sys.modules["aiogram.types"] = MagicMock()


@pytest.fixture(autouse=True)
def reset_bot_module():
    """Reset bot module before each test."""
    # Remove cached bot module to get fresh import
    modules_to_remove = [k for k in sys.modules if k.startswith("telegram_bot.bot")]
    for mod in modules_to_remove:
        del sys.modules[mod]
    yield


class TestBotHybridSearch:
    """Test bot uses QdrantService for hybrid search."""

    def test_bot_initializes_qdrant_service(self):
        """Bot should initialize QdrantService instead of RetrieverService."""
        with (
            patch("telegram_bot.bot.setup_throttling_middleware"),
            patch("telegram_bot.bot.setup_error_middleware"),
            patch("telegram_bot.bot.QdrantService") as mock_qdrant,
            patch("telegram_bot.bot.VoyageService"),
            patch("telegram_bot.bot.CacheService"),
            patch("telegram_bot.bot.LLMService"),
            patch("telegram_bot.bot.QueryAnalyzer"),
            patch("telegram_bot.bot.UserContextService"),
            patch("telegram_bot.bot.CESCPersonalizer"),
        ):
            from telegram_bot.bot import PropertyBot
            from telegram_bot.config import BotConfig

            config = BotConfig()
            config.telegram_token = "test:token"
            bot = PropertyBot(config)

            mock_qdrant.assert_called_once()
            assert hasattr(bot, "qdrant_service")


class TestBotGetSparseVector:
    """Test sparse vector generation via HTTP."""

    async def test_get_sparse_vector_calls_http_service(self):
        """_get_sparse_vector should call BGE-M3 HTTP service."""
        with (
            patch("telegram_bot.bot.setup_throttling_middleware"),
            patch("telegram_bot.bot.setup_error_middleware"),
            patch("telegram_bot.bot.QdrantService"),
            patch("telegram_bot.bot.VoyageService"),
            patch("telegram_bot.bot.CacheService"),
            patch("telegram_bot.bot.LLMService"),
            patch("telegram_bot.bot.QueryAnalyzer"),
            patch("telegram_bot.bot.UserContextService"),
            patch("telegram_bot.bot.CESCPersonalizer"),
            patch("telegram_bot.bot.httpx.AsyncClient") as mock_client,
        ):
            # Mock HTTP response
            mock_response = MagicMock()
            mock_response.json.return_value = {
                "indices": [1, 5, 10],
                "values": [0.5, 0.3, 0.2],
            }
            mock_response.raise_for_status = MagicMock()
            mock_client.return_value.post = AsyncMock(return_value=mock_response)

            from telegram_bot.bot import PropertyBot
            from telegram_bot.config import BotConfig

            config = BotConfig()
            config.telegram_token = "test:token"
            bot = PropertyBot(config)

            result = await bot._get_sparse_vector("test query")

            assert result["indices"] == [1, 5, 10]
            assert result["values"] == [0.5, 0.3, 0.2]

    async def test_get_sparse_vector_handles_error_gracefully(self):
        """_get_sparse_vector should return empty vector on error."""
        with (
            patch("telegram_bot.bot.setup_throttling_middleware"),
            patch("telegram_bot.bot.setup_error_middleware"),
            patch("telegram_bot.bot.QdrantService"),
            patch("telegram_bot.bot.VoyageService"),
            patch("telegram_bot.bot.CacheService"),
            patch("telegram_bot.bot.LLMService"),
            patch("telegram_bot.bot.QueryAnalyzer"),
            patch("telegram_bot.bot.UserContextService"),
            patch("telegram_bot.bot.CESCPersonalizer"),
            patch("telegram_bot.bot.httpx.AsyncClient") as mock_client,
        ):
            # Mock HTTP error
            mock_client.return_value.post = AsyncMock(side_effect=Exception("Connection refused"))

            from telegram_bot.bot import PropertyBot
            from telegram_bot.config import BotConfig

            config = BotConfig()
            config.telegram_token = "test:token"
            bot = PropertyBot(config)

            result = await bot._get_sparse_vector("test query")

            # Should return empty vector, not raise
            assert result == {"indices": [], "values": []}

"""Integration tests for bot hybrid search pipeline."""

import sys
from unittest.mock import MagicMock, patch

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
            patch("telegram_bot.bot.SparseTextEmbedding"),
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

    def test_bot_initializes_sparse_embedder(self):
        """Bot should initialize SparseTextEmbedding for BM42."""
        with (
            patch("telegram_bot.bot.setup_throttling_middleware"),
            patch("telegram_bot.bot.setup_error_middleware"),
            patch("telegram_bot.bot.QdrantService"),
            patch("telegram_bot.bot.VoyageService"),
            patch("telegram_bot.bot.CacheService"),
            patch("telegram_bot.bot.LLMService"),
            patch("telegram_bot.bot.QueryAnalyzer"),
            patch("telegram_bot.bot.SparseTextEmbedding") as mock_sparse,
            patch("telegram_bot.bot.UserContextService"),
            patch("telegram_bot.bot.CESCPersonalizer"),
        ):
            from telegram_bot.bot import PropertyBot
            from telegram_bot.config import BotConfig

            config = BotConfig()
            config.telegram_token = "test:token"
            bot = PropertyBot(config)

            mock_sparse.assert_called_once_with(
                model_name="Qdrant/bm42-all-minilm-l6-v2-attentions"
            )
            assert hasattr(bot, "sparse_embedder")


class TestBotGetSparseVector:
    """Test sparse vector generation."""

    def test_get_sparse_vector_returns_dict(self):
        """_get_sparse_vector should return dict with indices and values."""
        # Mock sparse embedding result
        mock_result = MagicMock()
        mock_result.indices.tolist.return_value = [1, 5, 10]
        mock_result.values.tolist.return_value = [0.5, 0.3, 0.2]

        with (
            patch("telegram_bot.bot.setup_throttling_middleware"),
            patch("telegram_bot.bot.setup_error_middleware"),
            patch("telegram_bot.bot.QdrantService"),
            patch("telegram_bot.bot.VoyageService"),
            patch("telegram_bot.bot.CacheService"),
            patch("telegram_bot.bot.LLMService"),
            patch("telegram_bot.bot.QueryAnalyzer"),
            patch("telegram_bot.bot.SparseTextEmbedding") as mock_sparse,
            patch("telegram_bot.bot.UserContextService"),
            patch("telegram_bot.bot.CESCPersonalizer"),
        ):
            mock_sparse.return_value.embed.return_value = iter([mock_result])

            from telegram_bot.bot import PropertyBot
            from telegram_bot.config import BotConfig

            config = BotConfig()
            config.telegram_token = "test:token"
            bot = PropertyBot(config)

            result = bot._get_sparse_vector("test query")

            assert "indices" in result
            assert "values" in result
            assert result["indices"] == [1, 5, 10]
            assert result["values"] == [0.5, 0.3, 0.2]

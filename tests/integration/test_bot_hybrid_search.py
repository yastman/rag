"""Integration-style tests for PropertyBot hybrid dependency wiring.

These tests keep real module imports and only mock external services, so they
catch wiring regressions without mutating sys.modules.
"""

from unittest.mock import patch

import pytest


# This suite validates real telegram_bot.bot imports; skip cleanly if optional
# Telegram runtime dependency is not installed in the environment.
pytest.importorskip("aiogram", reason="aiogram not installed")

from telegram_bot.bot import PropertyBot
from telegram_bot.config import BotConfig


def _make_config() -> BotConfig:
    """Create deterministic config for bot initialization tests."""
    return BotConfig(
        telegram_token="123456:TESTTOKEN",
        llm_api_key="test-llm-key",
        llm_base_url="https://api.example.com/v1",
        llm_model="test-model",
        qdrant_url="http://localhost:6333",
        qdrant_api_key="",
        qdrant_collection="test_collection",
        redis_url="redis://localhost:6379",
        bge_m3_url="http://localhost:8000",
        rerank_provider="none",
        qdrant_timeout=7,
    )


class TestBotHybridSearch:
    """Validate bot service wiring for hybrid retrieval pipeline."""

    def test_bot_initializes_qdrant_service(self):
        """PropertyBot must initialize primary + apartments Qdrant services."""
        with (
            patch("telegram_bot.bot.Bot"),
            patch("telegram_bot.bot.setup_throttling_middleware"),
            patch("telegram_bot.bot.setup_error_handler"),
            patch.object(PropertyBot, "_register_handlers"),
            patch("telegram_bot.integrations.cache.CacheLayerManager"),
            patch("telegram_bot.integrations.embeddings.BGEM3HybridEmbeddings"),
            patch("telegram_bot.integrations.embeddings.BGEM3SparseEmbeddings"),
            patch("telegram_bot.services.qdrant.QdrantService") as mock_qdrant,
            patch("telegram_bot.graph.config.GraphConfig.create_llm"),
        ):
            bot = PropertyBot(_make_config())

        assert mock_qdrant.call_count == 2
        primary_call = mock_qdrant.call_args_list[0].kwargs
        apartments_call = mock_qdrant.call_args_list[1].kwargs
        assert primary_call["collection_name"] == "test_collection"
        assert primary_call["timeout"] == 7
        assert apartments_call["collection_name"] == "apartments"
        assert hasattr(bot, "_qdrant")

    def test_bot_initializes_sparse_embeddings_with_bge_url(self):
        """PropertyBot should wire sparse embeddings from configured BGE-M3 URL."""
        with (
            patch("telegram_bot.bot.Bot"),
            patch("telegram_bot.bot.setup_throttling_middleware"),
            patch("telegram_bot.bot.setup_error_handler"),
            patch.object(PropertyBot, "_register_handlers"),
            patch("telegram_bot.integrations.cache.CacheLayerManager"),
            patch("telegram_bot.integrations.embeddings.BGEM3HybridEmbeddings"),
            patch("telegram_bot.integrations.embeddings.BGEM3SparseEmbeddings") as mock_sparse,
            patch("telegram_bot.services.qdrant.QdrantService"),
            patch("telegram_bot.graph.config.GraphConfig.create_llm"),
        ):
            PropertyBot(_make_config())

        mock_sparse.assert_called_once_with(base_url="http://localhost:8000", timeout=120.0)

    def test_bot_uses_hybrid_embeddings_as_primary_provider(self):
        """PropertyBot should expose hybrid embeddings as the primary provider."""
        with (
            patch("telegram_bot.bot.Bot"),
            patch("telegram_bot.bot.setup_throttling_middleware"),
            patch("telegram_bot.bot.setup_error_handler"),
            patch.object(PropertyBot, "_register_handlers"),
            patch("telegram_bot.integrations.cache.CacheLayerManager"),
            patch("telegram_bot.integrations.embeddings.BGEM3HybridEmbeddings") as mock_hybrid,
            patch("telegram_bot.integrations.embeddings.BGEM3SparseEmbeddings"),
            patch("telegram_bot.services.qdrant.QdrantService"),
            patch("telegram_bot.graph.config.GraphConfig.create_llm"),
        ):
            bot = PropertyBot(_make_config())

        assert bot._hybrid is mock_hybrid.return_value
        assert bot._embeddings is bot._hybrid

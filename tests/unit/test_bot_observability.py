"""Unit tests for bot-level Langfuse trace metadata."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from telegram_bot.bot import PropertyBot
from telegram_bot.config import BotConfig


def _create_bot(mock_config: BotConfig) -> PropertyBot:
    with (
        patch("telegram_bot.bot.Bot"),
        patch("telegram_bot.integrations.cache.CacheLayerManager"),
        patch("telegram_bot.integrations.embeddings.BGEM3HybridEmbeddings"),
        patch("telegram_bot.integrations.embeddings.BGEM3SparseEmbeddings"),
        patch("telegram_bot.services.qdrant.QdrantService"),
        patch("telegram_bot.graph.config.GraphConfig.create_llm"),
    ):
        return PropertyBot(mock_config)


@pytest.fixture
def mock_config() -> BotConfig:
    return BotConfig(
        telegram_token="test-token",
        voyage_api_key="voyage-key",
        llm_api_key="llm-key",
        llm_base_url="https://api.example.com/v1",
        llm_model="gpt-4o-mini",
        qdrant_url="http://localhost:6333",
        qdrant_api_key="qdrant-key",
        qdrant_collection="test_collection",
        redis_url="redis://localhost:6379",
        rerank_provider="none",
    )


@pytest.fixture
def mock_message() -> MagicMock:
    message = MagicMock()
    message.text = "квартиры до 100000 евро"
    message.from_user = MagicMock()
    message.from_user.id = 123456789
    message.chat = MagicMock()
    message.chat.id = 987654321
    message.bot = MagicMock()
    message.bot.send_chat_action = AsyncMock()
    return message


class TestHandleQueryObservability:
    async def test_handle_query_updates_trace(
        self, mock_config: BotConfig, mock_message: MagicMock
    ):
        bot = _create_bot(mock_config)

        mock_graph = AsyncMock()
        mock_graph.ainvoke = AsyncMock(
            return_value={"response": "ok", "query_type": "GENERAL", "latency_stages": {}}
        )
        mock_lf = MagicMock()

        with (
            patch("telegram_bot.bot.build_graph", return_value=mock_graph),
            patch("telegram_bot.bot.get_client", return_value=mock_lf),
            patch("telegram_bot.bot._write_langfuse_scores"),
            patch("telegram_bot.bot.propagate_attributes"),
            patch("telegram_bot.bot.ChatActionSender") as mock_cas,
        ):
            mock_cm = AsyncMock()
            mock_cm.__aenter__ = AsyncMock()
            mock_cm.__aexit__ = AsyncMock()
            mock_cas.typing.return_value = mock_cm

            await bot.handle_query(mock_message)

        mock_lf.update_current_trace.assert_called_once()
        kwargs = mock_lf.update_current_trace.call_args.kwargs
        assert kwargs["input"]["query"] == "квартиры до 100000 евро"
        assert kwargs["output"]["response"] == "ok"
    async def test_handle_query_includes_expected_metadata_fields(
        self,
        mock_config: BotConfig,
        mock_message: MagicMock,
    ):
        bot = _create_bot(mock_config)

        mock_graph = AsyncMock()
        mock_graph.ainvoke = AsyncMock(
            return_value={
                "response": "Найдено 2 варианта.",
                "query_type": "GENERAL",
                "cache_hit": False,
                "search_results_count": 2,
                "rerank_applied": True,
                "llm_provider_model": "cerebras/gpt-oss-120b",
                "llm_ttft_ms": 450.0,
                "latency_stages": {"generate": 1.2},
            }
        )
        mock_lf = MagicMock()

        with (
            patch("telegram_bot.bot.build_graph", return_value=mock_graph),
            patch("telegram_bot.bot.get_client", return_value=mock_lf),
            patch("telegram_bot.bot._write_langfuse_scores"),
            patch("telegram_bot.bot.propagate_attributes"),
            patch("telegram_bot.bot.ChatActionSender") as mock_cas,
        ):
            mock_cm = AsyncMock()
            mock_cm.__aenter__ = AsyncMock()
            mock_cm.__aexit__ = AsyncMock()
            mock_cas.typing.return_value = mock_cm

            await bot.handle_query(mock_message)

        metadata = mock_lf.update_current_trace.call_args.kwargs["metadata"]
        assert metadata["query_type"] == "GENERAL"
        assert metadata["cache_hit"] is False
        assert metadata["search_results_count"] == 2
        assert metadata["rerank_applied"] is True
        assert metadata["llm_provider_model"] == "cerebras/gpt-oss-120b"
        assert metadata["llm_ttft_ms"] == 450.0
        # Embedding resilience (#210)
        assert metadata["embedding_error"] is False
        assert metadata["embedding_error_type"] is None

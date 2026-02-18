"""Unit tests for bot-level Langfuse trace metadata (#310: supervisor-only)."""

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
        patch("telegram_bot.graph.config.GraphConfig.create_supervisor_llm"),
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
    message.answer = AsyncMock()
    return message


def _mock_agent_result(**overrides):
    """Create a standard SDK agent result dict (#413)."""
    base = {
        "messages": [MagicMock(content="ok")],
    }
    base.update(overrides)
    return base


class TestHandleQueryObservability:
    async def test_handle_query_updates_trace(
        self, mock_config: BotConfig, mock_message: MagicMock
    ):
        bot = _create_bot(mock_config)

        mock_agent = AsyncMock()
        mock_agent.ainvoke = AsyncMock(return_value=_mock_agent_result())
        mock_lf = MagicMock()

        with (
            patch("telegram_bot.bot.create_bot_agent", return_value=mock_agent),
            patch("telegram_bot.bot.get_client", return_value=mock_lf),
            patch("telegram_bot.bot.propagate_attributes"),
            patch("telegram_bot.bot.create_callback_handler", return_value=None),
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

        mock_agent = AsyncMock()
        mock_agent.ainvoke = AsyncMock(return_value=_mock_agent_result())
        mock_lf = MagicMock()

        with (
            patch("telegram_bot.bot.create_bot_agent", return_value=mock_agent),
            patch("telegram_bot.bot.get_client", return_value=mock_lf),
            patch("telegram_bot.bot.propagate_attributes"),
            patch("telegram_bot.bot.create_callback_handler", return_value=None),
            patch("telegram_bot.bot.ChatActionSender") as mock_cas,
        ):
            mock_cm = AsyncMock()
            mock_cm.__aenter__ = AsyncMock()
            mock_cm.__aexit__ = AsyncMock()
            mock_cas.typing.return_value = mock_cm

            await bot.handle_query(mock_message)

        metadata = mock_lf.update_current_trace.call_args.kwargs["metadata"]
        assert metadata["pipeline_mode"] == "sdk_agent"
        assert "pipeline_wall_ms" in metadata

"""Direct unit tests for bot handler trace propagation (#1253)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from telegram_bot.bot import PropertyBot
from telegram_bot.config import BotConfig


def _make_config() -> BotConfig:
    return BotConfig(
        _env_file=None,
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


def _create_bot() -> PropertyBot:
    cfg = _make_config()
    with (
        patch("telegram_bot.bot.Bot"),
        patch("telegram_bot.integrations.cache.CacheLayerManager"),
        patch("telegram_bot.integrations.embeddings.BGEM3HybridEmbeddings"),
        patch("telegram_bot.integrations.embeddings.BGEM3SparseEmbeddings"),
        patch("telegram_bot.services.qdrant.QdrantService"),
        patch("telegram_bot.graph.config.GraphConfig.create_llm"),
        patch("telegram_bot.graph.config.GraphConfig.create_supervisor_llm"),
    ):
        return PropertyBot(cfg)


def _make_typing_cm():
    cm = AsyncMock()
    cm.__aenter__ = AsyncMock()
    cm.__aexit__ = AsyncMock(return_value=False)
    return cm


@pytest.mark.asyncio
async def test_handle_query_passes_trace_context_to_callback_handler():
    """handle_query should pass current trace_id to agent CallbackHandler (#1253)."""
    bot = _create_bot()
    bot._resolve_user_role = AsyncMock(return_value="client")
    bot._ainvoke_supervisor_with_recovery = AsyncMock(
        return_value={"messages": [MagicMock(content="ok")]}
    )

    mock_lf = MagicMock()
    mock_lf.get_current_trace_id = MagicMock(return_value="trace-handler-123")

    mock_agent = AsyncMock()
    mock_agent.ainvoke = AsyncMock(return_value={"messages": [MagicMock(content="ok")]})

    with (
        patch("telegram_bot.bot.create_bot_agent", return_value=mock_agent),
        patch("telegram_bot.bot.get_client", return_value=mock_lf),
        patch("telegram_bot.bot.propagate_attributes"),
        patch("telegram_bot.bot.create_callback_handler") as mock_create_handler,
    ):
        message = MagicMock()
        message.text = "test query"
        message.chat = MagicMock(id=12345)
        message.from_user = MagicMock(id=12345)
        message.bot = MagicMock()
        message.bot.send_chat_action = AsyncMock()
        message.answer = AsyncMock()

        with patch("telegram_bot.bot.ChatActionSender") as mock_cas:
            mock_cas.typing.return_value = _make_typing_cm()
            await bot.handle_query(message)

    mock_create_handler.assert_called_once()
    assert mock_create_handler.call_args.kwargs["trace_context"] == {
        "trace_id": "trace-handler-123"
    }


@pytest.mark.asyncio
async def test_handle_query_omits_trace_context_when_no_trace_id():
    """When no trace_id is available, callback handler should not receive trace_context."""
    bot = _create_bot()
    bot._resolve_user_role = AsyncMock(return_value="client")
    bot._ainvoke_supervisor_with_recovery = AsyncMock(
        return_value={"messages": [MagicMock(content="ok")]}
    )

    mock_lf = MagicMock()
    mock_lf.get_current_trace_id = MagicMock(return_value="")

    mock_agent = AsyncMock()
    mock_agent.ainvoke = AsyncMock(return_value={"messages": [MagicMock(content="ok")]})

    with (
        patch("telegram_bot.bot.create_bot_agent", return_value=mock_agent),
        patch("telegram_bot.bot.get_client", return_value=mock_lf),
        patch("telegram_bot.bot.propagate_attributes"),
        patch("telegram_bot.bot.create_callback_handler") as mock_create_handler,
    ):
        message = MagicMock()
        message.text = "test query"
        message.chat = MagicMock(id=12345)
        message.from_user = MagicMock(id=12345)
        message.bot = MagicMock()
        message.bot.send_chat_action = AsyncMock()
        message.answer = AsyncMock()

        with patch("telegram_bot.bot.ChatActionSender") as mock_cas:
            mock_cas.typing.return_value = _make_typing_cm()
            await bot.handle_query(message)

    mock_create_handler.assert_called_once()
    assert mock_create_handler.call_args.kwargs.get("trace_context") is None

"""Tests for agent streaming via astream (#413)."""

from __future__ import annotations


async def test_streaming_config_flag():
    """Streaming is controlled by GraphConfig.streaming_enabled."""
    from telegram_bot.graph.config import GraphConfig

    gc = GraphConfig(streaming_enabled=True)
    assert gc.streaming_enabled is True

    gc2 = GraphConfig(streaming_enabled=False)
    assert gc2.streaming_enabled is False


async def test_streaming_default_is_true():
    """streaming_enabled defaults to True."""
    from telegram_bot.graph.config import GraphConfig

    gc = GraphConfig()
    assert gc.streaming_enabled is True


# --- BotContext.response_sent coordination tests (#428) ---


async def test_bot_context_has_response_sent_field():
    """BotContext has response_sent field defaulting to False (#428)."""
    from unittest.mock import MagicMock

    from telegram_bot.agents.context import BotContext

    ctx = BotContext(
        telegram_user_id=1,
        session_id="s",
        language="ru",
        kommo_client=None,
        history_service=MagicMock(),
        embeddings=MagicMock(),
        sparse_embeddings=MagicMock(),
        qdrant=MagicMock(),
        cache=MagicMock(),
        reranker=None,
        llm=MagicMock(),
    )
    assert ctx.response_sent is False


async def test_bot_context_response_sent_mutable():
    """BotContext.response_sent is mutable so streaming tools can set it (#428)."""
    from unittest.mock import MagicMock

    from telegram_bot.agents.context import BotContext

    ctx = BotContext(
        telegram_user_id=1,
        session_id="s",
        language="ru",
        kommo_client=None,
        history_service=MagicMock(),
        embeddings=MagicMock(),
        sparse_embeddings=MagicMock(),
        qdrant=MagicMock(),
        cache=MagicMock(),
        reranker=None,
        llm=MagicMock(),
    )
    ctx.response_sent = True
    assert ctx.response_sent is True

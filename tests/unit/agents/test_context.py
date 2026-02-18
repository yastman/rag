"""Tests for BotContext dataclass."""

from __future__ import annotations

from dataclasses import fields
from unittest.mock import AsyncMock, MagicMock


def test_bot_context_fields():
    """BotContext has all required fields for tool DI."""
    from telegram_bot.agents.context import BotContext

    field_names = {f.name for f in fields(BotContext)}
    expected = {
        "telegram_user_id",
        "session_id",
        "language",
        "kommo_client",
        "history_service",
        "embeddings",
        "qdrant",
        "cache",
        "sparse_embeddings",
        "reranker",
        "llm",
        "content_filter_enabled",
        "guard_mode",
    }
    assert expected.issubset(field_names), f"Missing fields: {expected - field_names}"


def test_bot_context_optional_kommo():
    """BotContext works without KommoClient (kommo_client=None)."""
    from telegram_bot.agents.context import BotContext

    ctx = BotContext(
        telegram_user_id=123,
        session_id="s-1",
        language="ru",
        kommo_client=None,
        history_service=AsyncMock(),
        embeddings=AsyncMock(),
        sparse_embeddings=AsyncMock(),
        qdrant=AsyncMock(),
        cache=AsyncMock(),
        reranker=None,
        llm=MagicMock(),
        content_filter_enabled=True,
        guard_mode="hard",
    )
    assert ctx.telegram_user_id == 123
    assert ctx.kommo_client is None


def test_bot_context_with_kommo():
    """BotContext works with KommoClient set."""
    from telegram_bot.agents.context import BotContext

    kommo = MagicMock()
    ctx = BotContext(
        telegram_user_id=456,
        session_id="s-2",
        language="en",
        kommo_client=kommo,
        history_service=AsyncMock(),
        embeddings=AsyncMock(),
        sparse_embeddings=AsyncMock(),
        qdrant=AsyncMock(),
        cache=AsyncMock(),
        reranker=None,
        llm=MagicMock(),
        content_filter_enabled=True,
        guard_mode="hard",
    )
    assert ctx.kommo_client is kommo

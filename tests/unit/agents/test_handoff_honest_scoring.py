"""Handoff honest-scoring contract (#2212, finding #4).

The real handoff action today is the manager Telegram notification (the Kommo
task was removed in #1541). So ``handoff_triggered`` must reflect that at least
one manager was actually notified — not merely that the tool ran. When every
notification fails, the tool must return a failure message instead of a false
success.
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from telegram_bot.agents.context import BotContext
from telegram_bot.agents.tooling import RunnableConfig


def _ctx(**kwargs) -> BotContext:
    defaults: dict = {
        "telegram_user_id": 42,
        "session_id": "s-test",
        "language": "ru",
        "embeddings": AsyncMock(),
        "sparse_embeddings": AsyncMock(),
        "qdrant": AsyncMock(),
        "cache": AsyncMock(),
        "reranker": None,
        "llm": AsyncMock(),
        "content_filter_enabled": True,
        "guard_mode": "hard",
    }
    defaults.update(kwargs)
    return BotContext(**defaults)


def _cfg(ctx: BotContext) -> RunnableConfig:
    return {"configurable": {"bot_context": ctx}}


@pytest.mark.asyncio
async def test_handoff_returns_success_when_delivered():
    bot = AsyncMock()
    bot.send_message = AsyncMock()
    ctx = _ctx(bot=bot, manager_ids=[100, 200])
    from telegram_bot.agents.utility_tools import handoff

    result = await handoff(reason="x", config=_cfg(ctx))

    assert "передан" in result.lower()


@pytest.mark.asyncio
async def test_handoff_all_notifications_fail_returns_error():
    bot = AsyncMock()
    bot.send_message = AsyncMock(side_effect=RuntimeError("network down"))
    ctx = _ctx(bot=bot, manager_ids=[100, 200])
    from telegram_bot.agents.utility_tools import handoff

    result = await handoff(reason="x", config=_cfg(ctx))

    assert "не удалось" in result.lower() or "позже" in result.lower()


@pytest.mark.asyncio
async def test_handoff_partial_delivery_counts_as_success():
    bot = AsyncMock()
    bot.send_message = AsyncMock(side_effect=[RuntimeError("boom"), None])
    ctx = _ctx(bot=bot, manager_ids=[100, 200])
    from telegram_bot.agents.utility_tools import handoff

    result = await handoff(reason="x", config=_cfg(ctx))

    assert "передан" in result.lower()


@pytest.mark.asyncio
async def test_handoff_does_not_crash_when_bot_missing():
    bot = None
    ctx = _ctx(bot=bot, manager_ids=[100])
    from telegram_bot.agents.utility_tools import handoff

    result = await handoff(reason="x", config=_cfg(ctx))

    assert "недоступны" in result.lower()

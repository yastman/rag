"""Handoff honest-scoring contract (#2212, finding #4).

The real handoff action today is the manager Telegram notification (the Kommo
task was removed in #1541). So ``handoff_triggered`` must reflect that at least
one manager was actually notified — not merely that the tool ran. When every
notification fails, the tool must emit ``handoff_delivery_failed`` instead of a
false success, and it must not crash when Langfuse is disabled
(``get_client()`` -> ``None``).
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from langchain_core.runnables import RunnableConfig

from telegram_bot.agents.context import BotContext


def _ctx(**kwargs) -> BotContext:
    defaults: dict = {
        "telegram_user_id": 42,
        "session_id": "s-test",
        "language": "ru",
        "kommo_client": None,
        "history_service": AsyncMock(),
        "embeddings": AsyncMock(),
        "sparse_embeddings": AsyncMock(),
        "qdrant": AsyncMock(),
        "cache": AsyncMock(),
        "reranker": None,
        "llm": MagicMock(),
        "content_filter_enabled": True,
        "guard_mode": "hard",
    }
    defaults.update(kwargs)
    return BotContext(**defaults)


def _cfg(ctx: BotContext) -> RunnableConfig:
    return RunnableConfig(configurable={"bot_context": ctx})


def _score_names(lf: MagicMock) -> list[str]:
    return [c.kwargs.get("name") for c in lf.score_current_trace.call_args_list]


@pytest.mark.asyncio
async def test_handoff_scores_triggered_when_delivered():
    bot = AsyncMock()
    bot.send_message = AsyncMock()
    ctx = _ctx(bot=bot, manager_ids=[100, 200])
    lf = MagicMock()
    from telegram_bot.agents import utility_tools

    with patch.object(utility_tools, "get_client", return_value=lf):
        result = await utility_tools.handoff.ainvoke({"reason": "x"}, config=_cfg(ctx))

    names = _score_names(lf)
    assert "handoff_triggered" in names
    assert "handoff_delivery_failed" not in names
    assert "передан" in result.lower()


@pytest.mark.asyncio
async def test_handoff_all_notifications_fail_no_false_success():
    bot = AsyncMock()
    bot.send_message = AsyncMock(side_effect=RuntimeError("network down"))
    ctx = _ctx(bot=bot, manager_ids=[100, 200])
    lf = MagicMock()
    from telegram_bot.agents import utility_tools

    with patch.object(utility_tools, "get_client", return_value=lf):
        result = await utility_tools.handoff.ainvoke({"reason": "x"}, config=_cfg(ctx))

    names = _score_names(lf)
    assert "handoff_triggered" not in names, "must not claim success when no manager was notified"
    assert "handoff_delivery_failed" in names
    assert "не удалось" in result.lower() or "позже" in result.lower()


@pytest.mark.asyncio
async def test_handoff_partial_delivery_counts_as_triggered():
    bot = AsyncMock()
    # first manager fails, second succeeds -> delivered == 1
    bot.send_message = AsyncMock(side_effect=[RuntimeError("boom"), None])
    ctx = _ctx(bot=bot, manager_ids=[100, 200])
    lf = MagicMock()
    from telegram_bot.agents import utility_tools

    with patch.object(utility_tools, "get_client", return_value=lf):
        result = await utility_tools.handoff.ainvoke({"reason": "x"}, config=_cfg(ctx))

    names = _score_names(lf)
    assert "handoff_triggered" in names
    assert "handoff_delivery_failed" not in names
    assert "передан" in result.lower()


@pytest.mark.asyncio
async def test_handoff_does_not_crash_when_langfuse_disabled():
    bot = AsyncMock()
    bot.send_message = AsyncMock()
    ctx = _ctx(bot=bot, manager_ids=[100])
    from telegram_bot.agents import utility_tools

    with patch.object(utility_tools, "get_client", return_value=None):
        result = await utility_tools.handoff.ainvoke({"reason": "x"}, config=_cfg(ctx))

    assert "передан" in result.lower()

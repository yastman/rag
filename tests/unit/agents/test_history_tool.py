"""Regression tests for history_search cache key scope (#2945).

Bug class: cache-key-missing-scope
The cache key must include deal_id so that different deals/scopes
do not return each other's cached history search results.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from telegram_bot.agents.tooling import RunnableConfig


@pytest.fixture
def bot_context():
    from telegram_bot.agents.context import BotContext

    ctx = BotContext(
        telegram_user_id=42,
        session_id="test-session",
        language="ru",
        embeddings=AsyncMock(),
        sparse_embeddings=AsyncMock(),
        qdrant=AsyncMock(),
        cache=AsyncMock(),
        reranker=None,
        llm=MagicMock(),
        content_filter_enabled=True,
        guard_mode="hard",
    )
    ctx.cache.get_embedding = AsyncMock(return_value=[0.1] * 10)
    ctx.cache.check_semantic = AsyncMock(return_value=None)
    ctx.cache.store_embedding = AsyncMock()
    ctx.cache.store_semantic = AsyncMock()
    return ctx


def _make_config(ctx) -> RunnableConfig:
    return RunnableConfig(configurable={"bot_context": ctx})


def test_history_search_is_callable():
    """history_search is importable and callable."""
    from telegram_bot.agents.history_tool import history_search

    assert callable(history_search)


# --- Regression test: different deal_id → different cache scope (#2945) ---


async def test_different_deal_ids_produce_different_cache_scopes(bot_context):
    """Cache check called with different scope when deal_id differs (#2945).

    Two history_search calls with different deal_id values must pass
    different filter/scope arguments to check_semantic so they cannot
    collide on the same cached entry.
    """
    from telegram_bot.agents.history_tool import history_search

    call_kwargs: list[dict] = []

    async def capturing_check(*args, **kwargs):
        call_kwargs.append(kwargs.copy())
        return  # always miss so both calls go through

    bot_context.cache.check_semantic = capturing_check

    config = _make_config(bot_context)
    await history_search("test query", config=config, deal_id=1)
    await history_search("test query", config=config, deal_id=2)

    assert len(call_kwargs) == 2, "check_semantic must be called for each invocation"

    # The scope or filter_signature passed for deal_id=1 must differ from deal_id=2
    scope_or_sig_0 = (
        call_kwargs[0].get("cache_scope"),
        call_kwargs[0].get("filter_signature"),
    )
    scope_or_sig_1 = (
        call_kwargs[1].get("cache_scope"),
        call_kwargs[1].get("filter_signature"),
    )
    assert scope_or_sig_0 != scope_or_sig_1, (
        f"deal_id=1 and deal_id=2 must produce different cache scope/filter_signature; "
        f"got {scope_or_sig_0!r} for both"
    )

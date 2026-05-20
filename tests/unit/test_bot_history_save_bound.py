"""Tests for ***REMOVED***1600: bounded fan-out for fire-and-forget history saves.

The bot's text path used to call ``asyncio.create_task(...)`` for every
``_bg_save_history`` invocation with no concurrency cap and no shutdown
drain. This file pins the new contract on ``PropertyBot._spawn_history_save``:

* tasks are tracked in ``_history_save_tasks`` and removed on completion
  via ``add_done_callback``;
* once the in-flight count hits ``_history_save_max_concurrency``, new
  saves are dropped (coro is closed, no leak) and a Langfuse score
  ``history_save_dropped=1`` is emitted;
* ``stop()`` drains pending saves with a bounded timeout.

Tests use a minimal ``PropertyBot`` shape via ``object.__new__`` to avoid
the full constructor (which wires aiogram, Redis, Postgres, etc.) — only
the subset relevant to the helper is initialised.
"""

from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import MagicMock, patch

import pytest


def _make_bot(*, max_concurrency: int = 32, drain_timeout: float = 0.5) -> Any:
    """Build a minimal PropertyBot with only the history-save fields."""
    from telegram_bot.bot import PropertyBot

    bot = object.__new__(PropertyBot)
    bot._history_save_tasks = set()
    bot._history_save_max_concurrency = max_concurrency
    bot._history_save_drain_timeout_s = drain_timeout
    bot._miniapp_subscriber_task = None
    bot._polling_lock_task = None
    bot._polling_lock = None
    bot._polling_lock_owner = None
    return bot


async def test_spawn_tracks_task_and_removes_on_completion():
    bot = _make_bot()

    completed = asyncio.Event()

    async def coro():
        completed.set()

    task = bot._spawn_history_save(coro(), user_id=42)
    assert task is not None
    assert task in bot._history_save_tasks

    await asyncio.wait_for(completed.wait(), timeout=1.0)
    await task

    ***REMOVED*** Done-callback runs in the loop's next pass; yield once so it fires.
    await asyncio.sleep(0)
    assert task not in bot._history_save_tasks


async def test_spawn_drops_save_at_concurrency_limit():
    bot = _make_bot(max_concurrency=2)

    blocker = asyncio.Event()

    async def slow_coro():
        await blocker.wait()

    ***REMOVED*** Saturate the limit with two pending tasks.
    t1 = bot._spawn_history_save(slow_coro(), user_id="a")
    t2 = bot._spawn_history_save(slow_coro(), user_id="b")
    assert t1 is not None and t2 is not None
    assert len(bot._history_save_tasks) == 2

    ***REMOVED*** Third save must be dropped — coro is closed, no leak.
    closed = False

    async def third_coro():
        nonlocal closed
        try:
            await asyncio.sleep(10)
        finally:
            closed = True

    third = third_coro()
    result = bot._spawn_history_save(third, user_id="c")
    assert result is None
    assert len(bot._history_save_tasks) == 2

    ***REMOVED*** The dropped coroutine must have been .close()'d so we don't leak.
    ***REMOVED*** Verify by trying to send into it: it should raise.
    with pytest.raises((StopIteration, RuntimeError)):
        third.send(None)

    blocker.set()
    await asyncio.gather(t1, t2)


async def test_drop_emits_langfuse_dropped_score():
    bot = _make_bot(max_concurrency=1)

    blocker = asyncio.Event()

    async def slow_coro():
        await blocker.wait()

    bot._spawn_history_save(slow_coro(), user_id="a")

    mock_lf = MagicMock()
    mock_lf.get_current_trace_id.return_value = "trace-xyz"

    with patch("telegram_bot.bot.get_client", return_value=mock_lf):

        async def dropped_coro():
            await asyncio.sleep(0)

        result = bot._spawn_history_save(dropped_coro(), user_id="b")
    assert result is None

    mock_lf.create_score.assert_called_once()
    call_kwargs = mock_lf.create_score.call_args.kwargs
    assert call_kwargs["name"] == "history_save_dropped"
    assert call_kwargs["value"] == 1
    assert call_kwargs["data_type"] == "BOOLEAN"
    assert call_kwargs["trace_id"] == "trace-xyz"

    blocker.set()
    await asyncio.gather(*bot._history_save_tasks)


async def test_drop_without_active_trace_does_not_raise():
    """Dropped saves must not crash when no Langfuse trace is active."""
    bot = _make_bot(max_concurrency=1)
    blocker = asyncio.Event()

    async def slow_coro():
        await blocker.wait()

    bot._spawn_history_save(slow_coro(), user_id="a")

    mock_lf = MagicMock()
    mock_lf.get_current_trace_id.return_value = ""

    with patch("telegram_bot.bot.get_client", return_value=mock_lf):

        async def coro2():
            await asyncio.sleep(0)

        result = bot._spawn_history_save(coro2(), user_id="b")

    assert result is None
    mock_lf.create_score.assert_not_called()

    blocker.set()
    await asyncio.gather(*bot._history_save_tasks)


async def test_drop_when_langfuse_disabled_is_quiet():
    """No Langfuse client → no score emission, no exception."""
    bot = _make_bot(max_concurrency=1)
    blocker = asyncio.Event()

    async def slow_coro():
        await blocker.wait()

    bot._spawn_history_save(slow_coro(), user_id="a")

    with patch("telegram_bot.bot.get_client", return_value=None):

        async def coro2():
            await asyncio.sleep(0)

        result = bot._spawn_history_save(coro2(), user_id="b")

    assert result is None

    blocker.set()
    await asyncio.gather(*bot._history_save_tasks)

"""Direct startup helper behavior, independent of PropertyBot wrappers."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from telegram_bot.lifecycle.lifecycle import polling_lock_heartbeat_tick, warmup_bge_pool


@pytest.mark.parametrize("failure", [None, RuntimeError("BGE unavailable")])
async def test_warmup_is_attempted_and_failure_is_nonfatal(failure) -> None:
    hybrid = SimpleNamespace(aembed_query=AsyncMock(side_effect=failure))
    await warmup_bge_pool(hybrid)
    hybrid.aembed_query.assert_awaited_once_with("warmup")


async def test_heartbeat_retries_recovers_and_stops_after_consecutive_failures() -> None:
    bot = SimpleNamespace(
        _polling_lock=SimpleNamespace(
            refresh=AsyncMock(side_effect=[RuntimeError(), None, RuntimeError(), RuntimeError()])
        ),
        _polling_lock_consecutive_failures=0,
        dp=SimpleNamespace(stop_polling=AsyncMock()),
    )
    for count in (1, 0, 1):
        await polling_lock_heartbeat_tick(bot, max_refresh_failures=2)
        assert bot._polling_lock_consecutive_failures == count
        bot.dp.stop_polling.assert_not_awaited()
    await polling_lock_heartbeat_tick(bot, max_refresh_failures=2)
    assert bot._polling_lock_consecutive_failures == 2
    bot.dp.stop_polling.assert_awaited_once_with()
    assert bot._polling_lock.refresh.await_count == 4


async def test_heartbeat_without_lock_is_noop() -> None:
    bot = SimpleNamespace(
        _polling_lock=None,
        _polling_lock_consecutive_failures=1,
        dp=SimpleNamespace(stop_polling=AsyncMock()),
    )
    await polling_lock_heartbeat_tick(bot)
    assert bot._polling_lock_consecutive_failures == 1
    bot.dp.stop_polling.assert_not_awaited()


async def test_heartbeat_stop_failure_is_nonfatal() -> None:
    bot = SimpleNamespace(
        _polling_lock=SimpleNamespace(refresh=AsyncMock(side_effect=RuntimeError())),
        _polling_lock_consecutive_failures=0,
        dp=SimpleNamespace(stop_polling=AsyncMock(side_effect=RuntimeError())),
    )
    await polling_lock_heartbeat_tick(bot, max_refresh_failures=1)
    bot.dp.stop_polling.assert_awaited_once_with()

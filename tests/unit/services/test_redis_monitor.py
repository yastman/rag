"""RedisHealthMonitor unit tests: checkpoint growth (#159) + asyncio-native loop (#2617).

Merged lane (#3368 A06): one file owns the monitor's scheduling, cancel, and
failure behaviour. The redis client is patched here because these tests pin
the monitor's own control flow; the live Redis contract is proven in
``tests/e2e/test_redis_modes_live.py``.
"""

import asyncio
from unittest.mock import AsyncMock, patch

from telegram_bot.services.observability.redis_monitor import RedisHealthMonitor


def _info_side_effect(**memory_extra: object) -> list[dict[str, object]]:
    return [
        {"used_memory": 1, "maxmemory": 10, **memory_extra},
        {"evicted_keys": 0, "keyspace_hits": 1, "keyspace_misses": 1},
    ]


# ---------------------------------------------------------------------------
# Checkpoint key growth (#159)
# ---------------------------------------------------------------------------


async def test_check_health_scans_all_checkpoint_keys_and_alerts_on_growth():
    """SCAN iterates cursor until 0; warns when checkpoint keys grow."""
    monitor = RedisHealthMonitor("redis://localhost:6379")
    monitor._prev_checkpoint_count = 1  # previously 1 key

    mock_redis = AsyncMock()
    mock_redis.info = AsyncMock(side_effect=_info_side_effect())
    mock_redis.dbsize = AsyncMock(return_value=5000)
    # Two SCAN iterations: cursor 1 → cursor 0 (3 keys total)
    mock_redis.scan = AsyncMock(
        side_effect=[
            (1, ["checkpoint:1", "checkpoint:2"]),
            (0, ["checkpoint:3"]),
        ]
    )
    monitor._redis = mock_redis

    with patch("telegram_bot.services.observability.redis_monitor.logger") as mock_logger:
        await monitor._check_health()

    assert mock_redis.scan.call_count == 2
    mock_logger.warning.assert_any_call(
        "Redis health: checkpoint key growth detected prev=%d current=%d delta=%d",
        1,
        3,
        2,
    )


async def test_check_health_no_warning_on_first_run():
    """No growth warning when _prev_checkpoint_count is None (first run)."""
    monitor = RedisHealthMonitor("redis://localhost:6379")
    assert monitor._prev_checkpoint_count is None

    mock_redis = AsyncMock()
    mock_redis.info = AsyncMock(side_effect=_info_side_effect())
    mock_redis.dbsize = AsyncMock(return_value=100)
    mock_redis.scan = AsyncMock(return_value=(0, ["checkpoint:1"]))
    monitor._redis = mock_redis

    with patch("telegram_bot.services.observability.redis_monitor.logger") as mock_logger:
        await monitor._check_health()

    # No growth warning on first run
    for call in mock_logger.warning.call_args_list:
        assert "checkpoint key growth" not in str(call)

    # But prev count is now set
    assert monitor._prev_checkpoint_count == 1


async def test_check_health_no_warning_when_count_stable():
    """No growth warning when checkpoint count stays the same."""
    monitor = RedisHealthMonitor("redis://localhost:6379")
    monitor._prev_checkpoint_count = 5

    mock_redis = AsyncMock()
    mock_redis.info = AsyncMock(side_effect=_info_side_effect())
    mock_redis.dbsize = AsyncMock(return_value=100)
    mock_redis.scan = AsyncMock(
        side_effect=[
            (1, ["checkpoint:1", "checkpoint:2"]),
            (0, ["checkpoint:3", "checkpoint:4", "checkpoint:5"]),
        ]
    )
    monitor._redis = mock_redis

    with patch("telegram_bot.services.observability.redis_monitor.logger") as mock_logger:
        await monitor._check_health()

    # No growth warning — count stayed at 5
    for call in mock_logger.warning.call_args_list:
        assert "checkpoint key growth" not in str(call)


async def test_check_health_checkpoint_scan_failure_is_non_fatal():
    """Checkpoint SCAN failure should not abort the whole health cycle."""
    monitor = RedisHealthMonitor("redis://localhost:6379")
    mock_redis = AsyncMock()
    mock_redis.info = AsyncMock(
        side_effect=_info_side_effect(used_memory_human="1B", maxmemory_human="10B")
    )
    mock_redis.dbsize = AsyncMock(side_effect=RuntimeError("no acl"))
    monitor._redis = mock_redis

    with patch("telegram_bot.services.observability.redis_monitor.logger") as mock_logger:
        await monitor._check_health()

    # Core INFO health log still emitted despite checkpoint metrics failure.
    mock_logger.info.assert_any_call(
        "Redis health: memory=%s/%s (%.1f%%), hit_rate=%.1f%%, evicted_keys=%d (new=%d)",
        "1B",
        "10B",
        10.0,
        50.0,
        0,
        0,
    )


# ---------------------------------------------------------------------------
# asyncio-native periodic loop (#2617): start/stop, scheduling, failure
# ---------------------------------------------------------------------------


def _patched_from_url():
    return patch("telegram_bot.services.observability.redis_monitor.aioredis.from_url")


async def test_start_sets_max_connections_for_monitor_pool():
    """RedisHealthMonitor uses max_connections=5 for its Redis pool."""
    monitor = RedisHealthMonitor("redis://localhost:6379")

    with _patched_from_url() as mock_from_url:
        mock_from_url.return_value = AsyncMock()
        await monitor.start()

    call_kwargs = mock_from_url.call_args[1]
    assert call_kwargs["max_connections"] == 5

    # Clean up
    await monitor.stop()


async def test_start_creates_asyncio_task_and_stop_cancels_it():
    """start() creates an asyncio Task; stop() cancels it and drops task + client."""
    monitor = RedisHealthMonitor("redis://localhost:6379", check_interval=60)

    with _patched_from_url() as mock_from_url:
        mock_from_url.return_value = AsyncMock()
        await monitor.start()

    assert monitor._task is not None
    assert isinstance(monitor._task, asyncio.Task)
    task = monitor._task
    assert not task.done()

    await monitor.stop()

    assert task.done()
    assert monitor._task is None
    assert monitor._redis is None


async def test_first_check_fires_promptly_not_after_full_interval():
    """First _check_health must fire well before check_interval, not after it."""
    # A long interval means a sleep-first loop would never tick during the test;
    # initial_check_delay=0 avoids the default 10s real wait in CI.
    monitor = RedisHealthMonitor(
        "redis://localhost:6379", check_interval=300, initial_check_delay=0
    )

    call_count = 0

    async def fake_check_health():
        nonlocal call_count
        call_count += 1

    with _patched_from_url() as mock_from_url:
        mock_from_url.return_value = AsyncMock()
        monitor._check_health = fake_check_health  # type: ignore[assignment]
        await monitor.start()

    await asyncio.sleep(0.2)
    await monitor.stop()

    assert call_count >= 1, (
        f"Expected first health check to fire promptly, got {call_count} calls. "
        "The loop appears to sleep the full interval before the first check."
    )


async def test_exception_in_tick_does_not_stop_loop():
    """An exception in _check_health must be caught; the periodic loop continues."""
    monitor = RedisHealthMonitor("redis://localhost:6379", check_interval=1, initial_check_delay=0)

    call_count = 0

    async def failing_check():
        nonlocal call_count
        call_count += 1
        raise RuntimeError("transient error")

    with _patched_from_url() as mock_from_url:
        mock_from_url.return_value = AsyncMock()
        monitor._check_health = failing_check  # type: ignore[assignment]
        await monitor.start()

    await asyncio.sleep(2.2)
    await monitor.stop()

    # Loop should have continued on schedule after the exception
    assert call_count >= 2, f"Expected at least 2 ticks despite exception, got {call_count}"

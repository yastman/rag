"""Tests for RedisHealthMonitor checkpoint key growth monitoring (#159)."""

from unittest.mock import AsyncMock, MagicMock, patch

from telegram_bot.services.redis_monitor import RedisHealthMonitor


async def test_check_health_scans_all_checkpoint_keys_and_alerts_on_growth():
    """SCAN iterates cursor until 0; warns when checkpoint keys grow."""
    monitor = RedisHealthMonitor("redis://localhost:6379")
    monitor._prev_checkpoint_count = 1  # previously 1 key

    mock_redis = AsyncMock()
    mock_redis.info = AsyncMock(
        side_effect=[
            {"used_memory": 1, "maxmemory": 10},
            {"evicted_keys": 0, "keyspace_hits": 1, "keyspace_misses": 1},
        ]
    )
    mock_redis.dbsize = AsyncMock(return_value=5000)
    # Two SCAN iterations: cursor 1 → cursor 0 (3 keys total)
    mock_redis.scan = AsyncMock(
        side_effect=[
            (1, ["checkpoint:1", "checkpoint:2"]),
            (0, ["checkpoint:3"]),
        ]
    )
    monitor._redis = mock_redis

    with patch("telegram_bot.services.redis_monitor.logger") as mock_logger:
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
    mock_redis.info = AsyncMock(
        side_effect=[
            {"used_memory": 1, "maxmemory": 10},
            {"evicted_keys": 0, "keyspace_hits": 1, "keyspace_misses": 1},
        ]
    )
    mock_redis.dbsize = AsyncMock(return_value=100)
    mock_redis.scan = AsyncMock(return_value=(0, ["checkpoint:1"]))
    monitor._redis = mock_redis

    with patch("telegram_bot.services.redis_monitor.logger") as mock_logger:
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
    mock_redis.info = AsyncMock(
        side_effect=[
            {"used_memory": 1, "maxmemory": 10},
            {"evicted_keys": 0, "keyspace_hits": 1, "keyspace_misses": 1},
        ]
    )
    mock_redis.dbsize = AsyncMock(return_value=100)
    mock_redis.scan = AsyncMock(
        side_effect=[
            (1, ["checkpoint:1", "checkpoint:2"]),
            (0, ["checkpoint:3", "checkpoint:4", "checkpoint:5"]),
        ]
    )
    monitor._redis = mock_redis

    with patch("telegram_bot.services.redis_monitor.logger") as mock_logger:
        await monitor._check_health()

    # No growth warning — count stayed at 5
    for call in mock_logger.warning.call_args_list:
        assert "checkpoint key growth" not in str(call)


async def test_check_health_checkpoint_scan_failure_is_non_fatal():
    """Checkpoint SCAN failure should not abort the whole health cycle."""
    monitor = RedisHealthMonitor("redis://localhost:6379")
    mock_redis = AsyncMock()
    mock_redis.info = AsyncMock(
        side_effect=[
            {
                "used_memory": 1,
                "maxmemory": 10,
                "used_memory_human": "1B",
                "maxmemory_human": "10B",
            },
            {"evicted_keys": 0, "keyspace_hits": 1, "keyspace_misses": 1},
        ]
    )
    mock_redis.dbsize = AsyncMock(side_effect=RuntimeError("no acl"))
    monitor._redis = mock_redis

    with patch("telegram_bot.services.redis_monitor.logger") as mock_logger:
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


async def test_start_sets_max_connections_for_monitor_pool():
    """RedisHealthMonitor uses max_connections=5 for its Redis pool."""
    monitor = RedisHealthMonitor("redis://localhost:6379")

    with (
        patch("telegram_bot.services.redis_monitor.aioredis.from_url") as mock_from_url,
        patch(
            "telegram_bot.services.redis_monitor.AsyncIOScheduler"
        ) as mock_scheduler_cls,
    ):
        mock_client = AsyncMock()
        mock_from_url.return_value = mock_client
        mock_scheduler = MagicMock()
        mock_scheduler_cls.return_value = mock_scheduler
        await monitor.start()

    call_kwargs = mock_from_url.call_args[1]
    assert call_kwargs["max_connections"] == 5
    mock_scheduler.start.assert_called_once()


async def test_start_registers_scheduler_job_and_stop_shuts_down():
    """start() creates a scheduler with job id='redis-health-monitor'; stop() shuts it down."""
    monitor = RedisHealthMonitor("redis://localhost:6379")

    with (
        patch("telegram_bot.services.redis_monitor.aioredis.from_url") as mock_from_url,
        patch(
            "telegram_bot.services.redis_monitor.AsyncIOScheduler"
        ) as mock_scheduler_cls,
    ):
        mock_client = AsyncMock()
        mock_from_url.return_value = mock_client
        mock_scheduler = MagicMock()
        mock_scheduler_cls.return_value = mock_scheduler
        await monitor.start()

    # Verify job was added with correct id
    mock_scheduler.add_job.assert_called_once()
    add_job_kwargs = mock_scheduler.add_job.call_args
    assert add_job_kwargs[1]["id"] == "redis-health-monitor"
    assert add_job_kwargs[1]["replace_existing"] is True
    assert add_job_kwargs[0][1] == "interval"

    # Verify stop shuts down the scheduler
    await monitor.stop()
    mock_scheduler.shutdown.assert_called_once_with(wait=False)

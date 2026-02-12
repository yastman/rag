"""Periodic Redis health monitor.

Runs every 5 minutes and checks:
- evicted_keys: WARNING if new evictions since last check
- Hit rate: WARNING if keyspace hit rate < 50%
- Memory usage: WARNING if used_memory > 80% of maxmemory

Logs are picked up by Promtail -> Loki -> Alertmanager.
"""

import asyncio
import contextlib
import logging

import redis.asyncio as aioredis
from redis.backoff import ExponentialBackoff
from redis.retry import Retry


logger = logging.getLogger(__name__)

# Thresholds
HIT_RATE_WARNING_THRESHOLD = 0.50  # Warn if hit rate < 50%
MEMORY_WARNING_THRESHOLD = 0.80  # Warn if memory usage > 80%
CHECKPOINT_GROWTH_WARN_DELTA = 1  # Warn on any growth; tune later if noisy
CHECK_INTERVAL_SECONDS = 300  # 5 minutes


class RedisHealthMonitor:
    """Monitors Redis health metrics on a periodic schedule."""

    def __init__(self, redis_url: str, check_interval: int = CHECK_INTERVAL_SECONDS):
        """Initialize the monitor.

        Args:
            redis_url: Redis connection URL
            check_interval: Seconds between health checks (default: 300)
        """
        self.redis_url = redis_url
        self.check_interval = check_interval
        self._task: asyncio.Task | None = None
        self._redis: aioredis.Redis | None = None
        self._prev_evicted_keys: int | None = None
        self._prev_checkpoint_count: int | None = None

    async def start(self):
        """Start the periodic health check loop as a background task."""
        self._redis = aioredis.from_url(
            self.redis_url,
            encoding="utf-8",
            decode_responses=True,
            socket_connect_timeout=5,
            socket_timeout=5,
            retry_on_timeout=True,
            retry=Retry(ExponentialBackoff(), 3),
            health_check_interval=30,
        )
        self._task = asyncio.create_task(self._loop(), name="redis-health-monitor")
        logger.info(
            "Redis health monitor started (interval=%ds, hit_rate_threshold=%.0f%%, "
            "memory_threshold=%.0f%%)",
            self.check_interval,
            HIT_RATE_WARNING_THRESHOLD * 100,
            MEMORY_WARNING_THRESHOLD * 100,
        )

    async def stop(self):
        """Cancel the background task and close Redis connection."""
        if self._task is not None:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
            self._task = None
        if self._redis is not None:
            await self._redis.aclose()
            self._redis = None
        logger.info("Redis health monitor stopped")

    async def _loop(self):
        """Run health checks in a loop until cancelled."""
        # Small initial delay to let the bot finish startup
        await asyncio.sleep(10)

        while True:
            try:
                await self._check_health()
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("Redis health check failed (will retry next cycle)")
            await asyncio.sleep(self.check_interval)

    async def _check_health(self):
        """Run a single health check cycle."""
        if self._redis is None:
            return

        try:
            info_memory = await self._redis.info("memory")
            info_stats = await self._redis.info("stats")
        except Exception:
            logger.warning("Redis health check: unable to connect to Redis")
            raise

        # --- Evicted keys ---
        evicted_keys = int(info_stats.get("evicted_keys", 0))
        new_evictions = 0
        if self._prev_evicted_keys is not None:
            new_evictions = evicted_keys - self._prev_evicted_keys
        self._prev_evicted_keys = evicted_keys

        if new_evictions > 0:
            logger.warning(
                "Redis health: %d keys evicted since last check (total=%d)",
                new_evictions,
                evicted_keys,
            )

        # --- Hit rate ---
        keyspace_hits = int(info_stats.get("keyspace_hits", 0))
        keyspace_misses = int(info_stats.get("keyspace_misses", 0))
        total_ops = keyspace_hits + keyspace_misses
        hit_rate = (keyspace_hits / total_ops) if total_ops > 0 else 1.0

        if total_ops > 0 and hit_rate < HIT_RATE_WARNING_THRESHOLD:
            logger.warning(
                "Redis health: low hit rate %.1f%% (hits=%d, misses=%d)",
                hit_rate * 100,
                keyspace_hits,
                keyspace_misses,
            )

        # --- Memory usage ---
        used_memory = int(info_memory.get("used_memory", 0))
        maxmemory = int(info_memory.get("maxmemory", 0))
        used_memory_human = info_memory.get("used_memory_human", "N/A")
        maxmemory_human = info_memory.get("maxmemory_human", "N/A")

        memory_pct = 0.0
        if maxmemory > 0:
            memory_pct = used_memory / maxmemory
            if memory_pct > MEMORY_WARNING_THRESHOLD:
                logger.warning(
                    "Redis health: memory usage %.1f%% (%s / %s)",
                    memory_pct * 100,
                    used_memory_human,
                    maxmemory_human,
                )

        # --- Checkpoint key metrics (#159) ---
        try:
            dbsize = await self._redis.dbsize()
            cursor: int = 0
            checkpoint_count = 0
            while True:
                cursor, keys = await self._redis.scan(
                    cursor=cursor,
                    match="checkpoint:*",
                    count=1000,
                )
                checkpoint_count += len(keys)
                if cursor == 0:
                    break

            prev_checkpoint_count = self._prev_checkpoint_count
            self._prev_checkpoint_count = checkpoint_count

            logger.info(
                "Redis health: dbsize=%d checkpoint_keys=%d",
                dbsize,
                checkpoint_count,
            )

            if (
                prev_checkpoint_count is not None
                and checkpoint_count - prev_checkpoint_count >= CHECKPOINT_GROWTH_WARN_DELTA
            ):
                logger.warning(
                    "Redis health: checkpoint key growth detected prev=%d current=%d delta=%d",
                    prev_checkpoint_count,
                    checkpoint_count,
                    checkpoint_count - prev_checkpoint_count,
                )
        except Exception as e:
            logger.warning(
                "Redis health: checkpoint metrics skipped due to %s: %s",
                type(e).__name__,
                e,
            )

        # --- INFO log every cycle ---
        logger.info(
            "Redis health: memory=%s/%s (%.1f%%), hit_rate=%.1f%%, evicted_keys=%d (new=%d)",
            used_memory_human,
            maxmemory_human if maxmemory > 0 else "unlimited",
            memory_pct * 100 if maxmemory > 0 else 0.0,
            hit_rate * 100 if total_ops > 0 else 100.0,
            evicted_keys,
            new_evictions,
        )

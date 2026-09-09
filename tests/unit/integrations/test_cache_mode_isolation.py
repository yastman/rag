"""CacheLayerManager mode behavior and import isolation (#3362, #3354).

- ``disabled``: no Redis client, no import, no DNS/socket — cache is a
  deterministic miss/no-store with no memory durability substitute.
- ``single_instance``: connects when configured; on connection loss the
  cache fails open (miss/no-store) and capability reports ``degraded``.
- ``multi_instance``: same client behavior at manager level — the
  required-connection gate is enforced upstream (preflight + polling
  lock), while reads still never fabricate values.
"""

from __future__ import annotations

import asyncio
import socket
import subprocess
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from src.runtime.integrations.cache import CacheLayerManager
from src.runtime.integrations.redis_mode import RedisCapability, RedisMode


REPO_ROOT = Path(__file__).parents[3]
_UNROUTABLE_REDIS = "redis://127.0.0.1:1"  # nothing listens on port 1


def _disabled_manager() -> CacheLayerManager:
    return CacheLayerManager(redis_url=_UNROUTABLE_REDIS, mode=RedisMode.DISABLED)


class TestDisabledMode:
    async def test_initialize_makes_no_client(self) -> None:
        manager = _disabled_manager()
        await manager.initialize()
        assert manager.redis is None
        assert manager.capability is RedisCapability.DISABLED

    async def test_initialize_attempts_no_socket_or_dns(self, monkeypatch) -> None:
        def _no_network(*_args: object, **_kwargs: object) -> None:
            raise AssertionError("disabled mode attempted a network operation")

        monkeypatch.setattr(socket, "socket", _no_network)
        monkeypatch.setattr(socket, "create_connection", _no_network)
        monkeypatch.setattr(socket, "getaddrinfo", _no_network)

        manager = _disabled_manager()
        await asyncio.wait_for(manager.initialize(), timeout=5)
        assert manager.redis is None

    async def test_reads_miss_and_writes_noop_without_memory_substitute(self) -> None:
        manager = _disabled_manager()
        await manager.initialize()

        assert await manager.get_exact("search", "k") is None
        await manager.store_exact("search", "k", {"v": 1})  # must not raise
        assert await manager.get_exact("search", "k") is None  # still a miss — no substitute

        assert await manager.check_semantic("q", [0.0], "GENERAL") is None
        assert await manager.get_embedding("q") is None
        assert await manager.get_bge_m3_query_bundle("q") is None

    async def test_close_is_safe_without_client(self) -> None:
        manager = _disabled_manager()
        await manager.initialize()
        await manager.close()


class TestSingleInstanceMode:
    async def test_default_mode_is_single_instance(self) -> None:
        # Preserves the historical single-node fail-open semantics for direct
        # constructions; production wiring always passes the mode explicitly.
        manager = CacheLayerManager(redis_url=_UNROUTABLE_REDIS)
        assert manager.mode is RedisMode.SINGLE_INSTANCE

    async def test_unreachable_redis_degrades_to_fail_open(self, caplog) -> None:
        manager = CacheLayerManager(redis_url=_UNROUTABLE_REDIS, mode=RedisMode.SINGLE_INSTANCE)
        with caplog.at_level("ERROR"):
            await manager.initialize()

        assert manager.redis is None
        assert manager.capability is RedisCapability.DEGRADED
        assert "Redis connection failed" in caplog.text

        # Fail open: reads are deterministic misses, writes are logged no-ops.
        assert await manager.get_exact("search", "k") is None
        await manager.store_exact("search", "k", {"v": 1})

    async def test_capability_enabled_after_successful_connect(self) -> None:
        manager = CacheLayerManager(
            redis_url="redis://localhost:6379", mode=RedisMode.SINGLE_INSTANCE
        )
        client = MagicMock()
        client.ping = AsyncMock(return_value=True)
        with (
            patch(
                "src.runtime.integrations.cache._create_redis_client",
                return_value=client,
            ),
            patch("src.runtime.integrations.cache._create_semantic_cache", return_value=None),
            patch("src.runtime.integrations.cache._create_embed_cache", return_value=None),
        ):
            await manager.initialize()

        assert manager.redis is client
        assert manager.capability is RedisCapability.ENABLED


class TestMultiInstanceManagerLevel:
    async def test_connection_loss_reports_degraded(self) -> None:
        # The manager itself still fails open; multi-instance "Redis required
        # at startup" is enforced by preflight (fatal) and the polling-lock
        # gate (no polling without a live backend).
        manager = CacheLayerManager(redis_url=_UNROUTABLE_REDIS, mode=RedisMode.MULTI_INSTANCE)
        await manager.initialize()
        assert manager.capability is RedisCapability.DEGRADED
        assert await manager.get_exact("search", "k") is None


class TestImportIsolation:
    def _run_blocked(self, body: str) -> subprocess.CompletedProcess[str]:
        prelude = (
            "import sys\n"
            "sys.modules['redis'] = None\n"
            "sys.modules['redis.asyncio'] = None\n"
            "sys.modules['redis.backoff'] = None\n"
            "sys.modules['redis.retry'] = None\n"
            "sys.modules['redisvl'] = None\n"
        )
        return subprocess.run(
            [sys.executable, "-c", prelude + body],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            timeout=120,
        )

    def test_disabled_mode_imports_and_runs_without_redis(self) -> None:
        result = self._run_blocked(
            "import asyncio\n"
            "from src.runtime.integrations.cache import CacheLayerManager\n"
            "from src.runtime.integrations.redis_mode import RedisMode\n"
            "mgr = CacheLayerManager(redis_url='redis://localhost:6379', mode=RedisMode.DISABLED)\n"
            "asyncio.run(mgr.initialize())\n"
            "assert mgr.redis is None\n"
            "print('OK')\n"
        )
        assert result.returncode == 0, f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
        assert "OK" in result.stdout

    def test_single_mode_without_redis_package_fails_open(self) -> None:
        result = self._run_blocked(
            "import asyncio\n"
            "from src.runtime.integrations.cache import CacheLayerManager\n"
            "from src.runtime.integrations.redis_mode import RedisMode\n"
            "mgr = CacheLayerManager(\n"
            "    redis_url='redis://127.0.0.1:1', mode=RedisMode.SINGLE_INSTANCE\n"
            ")\n"
            "asyncio.run(mgr.initialize())\n"
            "assert mgr.redis is None\n"
            "assert asyncio.run(mgr.get_exact('search', 'k')) is None\n"
            "print('OK')\n"
        )
        assert result.returncode == 0, f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
        assert "OK" in result.stdout

"""Live Redis operating-mode and polling-lock contract (#3368).

Proves the #3354 mode table (delivered by #3362) and the two-owner distributed
polling lock against a REAL authenticated Redis server. redis-py / RedisVL are
never mocked in this lane; every test starts its own disposable ``redis``
container (unique name, ephemeral host port, random password, no persistence)
and removes it on teardown, so the tests are hermetic, parallel-safe, and leave
no keys behind.

Scenarios (issue #3368):

1. ``disabled`` — Redis is neither imported nor contacted, whether the server is
   reachable or not: cache is miss/no-store, Redis-only durable features stay
   unavailable, no polling-lock claim.
2. ``single_instance`` — cache write/read/TTL/delete against real Redis; one
   lifecycle polls without a distributed lock; Redis loss (wrong password,
   unreachable, or killed mid-run) degrades the cache but never invents durable
   storage.
3. ``multi_instance`` — owner A acquires the lock through the real lifecycle
   gate; owner B, a separate OS process, is refused and told who owns it; the
   heartbeat renews the lease; forced lease loss stops A; B takes over; release
   cleans up; an un-renewed lease expires.
4. Startup with a wrong password / unavailable Redis fails only where the
   selected mode requires it (preflight + polling gate).

Strict lane: ``E2E_REDIS_STRICT=1`` (set by ``make test-e2e-redis-live``) turns
a missing Docker daemon into a failure instead of a skip.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import os
import shutil
import socket
import subprocess
import sys
import threading
import time
import uuid
from collections.abc import AsyncIterator, Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest

from src.runtime.integrations.cache import CacheLayerManager
from src.runtime.integrations.polling_lock import (
    POLLING_LOCK_KEY,
    PollingLockBusy,
    RedisPollingLock,
)
from src.runtime.integrations.redis_mode import RedisCapability, RedisMode
from telegram_bot.lifecycle.lifecycle import (
    polling_lock_heartbeat_tick,
    redis_capability_signal,
    setup_handoff_services,
    setup_polling_lock,
)
from telegram_bot.startup_status import StartupSeverity
from tests.unit._bot_config_factory import make_bot_config


pytestmark = [pytest.mark.e2e, pytest.mark.requires_services]

_REPO_ROOT = Path(__file__).resolve().parents[2]
_REDIS_IMAGE = os.getenv("E2E_REDIS_IMAGE", "redis:8.10.1")
_CONTAINER_PREFIX = "rag-e2e-3368"
# Unreachable endpoints fail instantly on every platform: connecting to
# 0.0.0.0 is an immediate address error on Windows and an immediate loopback
# refusal on Linux, whereas a refused 127.0.0.1 connect costs ~2s per attempt
# under Docker Desktop and would turn the preflight retries into minutes.
_DEAD_REDIS_URL = "redis://:nobody@0.0.0.0:1/0"
# Dead endpoints for the non-Redis preflight dependencies keep scenario 4
# independent of whatever Compose stack a developer happens to run.
_DEAD_QDRANT_URL = "http://0.0.0.0:1"
# Non-canonical local port: the BGE-M3 URL guardrail rejects it before any I/O.
_UNUSABLE_BGE_M3_URL = "http://127.0.0.1:8001"
_DEAD_POSTGRES_URL = "postgresql://postgres:postgres@0.0.0.0:1/realestate"

_TRUTHY = {"1", "true", "yes", "on"}


def _strict_lane() -> bool:
    return os.getenv("E2E_REDIS_STRICT", "").strip().lower() in _TRUTHY


def _unavailable(reason: str) -> None:
    """Fail in the strict service lane, skip otherwise (#3411 honest classification)."""
    message = f"{reason} (set E2E_REDIS_STRICT=1 to make this a failure)"
    if _strict_lane():
        pytest.fail(reason)
    pytest.skip(message)


# ---------------------------------------------------------------------------
# Disposable Redis container harness
# ---------------------------------------------------------------------------


def _docker(*args: str, timeout: float = 60.0) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["docker", *args],
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )


def _docker_daemon_available() -> bool:
    if shutil.which("docker") is None:
        return False
    return _docker("info", "--format", "{{.ServerVersion}}", timeout=30.0).returncode == 0


@dataclass(frozen=True, slots=True)
class LiveRedis:
    """One disposable, authenticated Redis server owned by a single test."""

    name: str
    password: str
    port: int

    @property
    def url(self) -> str:
        return self.url_with_password(self.password)

    def url_with_password(self, password: str) -> str:
        return f"redis://:{password}@127.0.0.1:{self.port}/0"

    def kill(self) -> None:
        """Remove the container now (mid-run Redis loss); idempotent."""
        _docker("rm", "-f", self.name)


def _start_redis_container(name: str, password: str) -> int:
    """Start the disposable server and return its ephemeral host port.

    ``-P`` lets Docker pick a free host port (parallel-safe); persistence is
    off so nothing outlives the container.
    """
    run = _docker(
        "run",
        "-d",
        "--rm",
        "--name",
        name,
        "-P",
        _REDIS_IMAGE,
        "redis-server",
        "--requirepass",
        password,
        "--save",
        "",
        "--appendonly",
        "no",
        timeout=120.0,
    )
    if run.returncode != 0:
        raise RuntimeError(f"docker run {_REDIS_IMAGE} failed: {run.stderr.strip()}")
    deadline = time.monotonic() + 30.0
    while time.monotonic() < deadline:
        published = _docker("port", name, "6379")
        for line in published.stdout.splitlines():
            host_port = line.strip().rsplit(":", 1)[-1]
            if host_port.isdigit():
                return int(host_port)
        time.sleep(0.2)
    _docker("rm", "-f", name)
    raise RuntimeError(f"docker did not publish a host port for {name}")


def _container_gone(name: str) -> bool:
    listed = _docker("ps", "-a", "--filter", f"name=^{name}$", "--format", "{{.Names}}")
    return listed.returncode == 0 and listed.stdout.strip() == ""


@contextlib.asynccontextmanager
async def _observer(live: LiveRedis) -> AsyncIterator[Any]:
    """Independent redis-py client used only to observe server-side state."""
    import redis.asyncio as aioredis

    client = aioredis.from_url(live.url, decode_responses=True, socket_connect_timeout=2)
    try:
        yield client
    finally:
        await client.aclose()


async def _wait_until_ready(live: LiveRedis, ready_deadline_s: float = 30.0) -> None:
    deadline = time.monotonic() + ready_deadline_s
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        try:
            async with _observer(live) as client:
                await client.ping()
                return
        except Exception as exc:
            last_error = exc
            await asyncio.sleep(0.25)
    raise RuntimeError(
        f"Redis container {live.name} not ready after {ready_deadline_s}s: {last_error!r}"
    )


@pytest.fixture
async def live_redis() -> AsyncIterator[LiveRedis]:
    """Disposable authenticated Redis for one test; deterministic cleanup."""
    if not _docker_daemon_available():
        _unavailable("Docker daemon unavailable — live Redis harness cannot start")
    name = f"{_CONTAINER_PREFIX}-{uuid.uuid4().hex[:10]}"
    password = f"pw-{uuid.uuid4().hex}"
    live: LiveRedis | None = None
    try:
        port = _start_redis_container(name, password)
        live = LiveRedis(name=name, password=password, port=port)
        await _wait_until_ready(live)
        yield live
    finally:
        if live is not None:
            with contextlib.suppress(Exception):
                async with _observer(live) as client:
                    await client.flushall()
        _docker("rm", "-f", name)
        assert _container_gone(name), f"disposable Redis container {name} survived cleanup"


# ---------------------------------------------------------------------------
# Minimal PropertyBot stand-in for the public lifecycle helpers
# ---------------------------------------------------------------------------


class _RecordingDispatcher:
    """aiogram Dispatcher stand-in: records ``stop_polling`` calls."""

    def __init__(self) -> None:
        self.stop_polling_calls = 0

    async def stop_polling(self) -> None:
        self.stop_polling_calls += 1


class _LifecycleBot:
    """Exactly the attributes the lifecycle helpers read/write on PropertyBot."""

    def __init__(self, config: Any, cache: CacheLayerManager) -> None:
        self.config = config
        self.bot = None
        self.dp = _RecordingDispatcher()
        self._cache = cache
        self._polling_lock: RedisPollingLock | None = None
        self._polling_lock_owner: str | None = None
        self._polling_lock_task: asyncio.Task[None] | None = None
        self._polling_lock_consecutive_failures = 0
        self._handoff_state: Any = None
        self._forum_bridge: Any = None
        self._lead_sink: Any = None

    async def _polling_lock_heartbeat_tick(self) -> None:
        await polling_lock_heartbeat_tick(self)

    async def cancel_heartbeat(self) -> None:
        if self._polling_lock_task is not None:
            self._polling_lock_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._polling_lock_task
            self._polling_lock_task = None


def _bot_config(mode: str, redis_url: str) -> Any:
    return make_bot_config(
        redis_mode=mode,
        redis_url=redis_url,
        qdrant_url=_DEAD_QDRANT_URL,
        qdrant_timeout=1,
        bge_m3_url=_UNUSABLE_BGE_M3_URL,
        realestate_database_url=_DEAD_POSTGRES_URL,
    )


class _RedisClientPackagesAbsent:
    """Make ``redis`` / ``redisvl`` un-importable for the duration of a block.

    Simulates scenario 1's "client packages absent": any import attempt raises
    ImportError, so code that honours ``disabled`` mode must not import them.
    """

    _BLOCKED = ("redis", "redisvl")

    def __init__(self) -> None:
        self._saved: dict[str, Any] = {}

    def find_spec(self, fullname: str, path: Any = None, target: Any = None) -> None:
        if fullname.split(".", 1)[0] in self._BLOCKED:
            msg = f"{fullname} is blocked: Redis client packages are absent in this block"
            raise ImportError(msg)

    def __enter__(self) -> _RedisClientPackagesAbsent:
        for name in list(sys.modules):
            if name.split(".", 1)[0] in self._BLOCKED:
                self._saved[name] = sys.modules.pop(name)
        sys.meta_path.insert(0, self)
        return self

    def __exit__(self, *exc_info: object) -> None:
        sys.meta_path.remove(self)
        for name in list(sys.modules):
            if name.split(".", 1)[0] in self._BLOCKED:
                del sys.modules[name]
        sys.modules.update(self._saved)


# ---------------------------------------------------------------------------
# Owner B: an independent OS process running the real lifecycle gate
# ---------------------------------------------------------------------------


def _emit(event: dict[str, Any]) -> None:
    sys.stdout.write(json.dumps(event) + "\n")
    sys.stdout.flush()


def _owner_b_main(redis_url: str, mode: str) -> int:
    """Second polling owner (scenario 3), executed as ``python <this file> owner-b``."""

    async def run() -> None:
        config = _bot_config(mode, redis_url)
        cache = CacheLayerManager(redis_url=redis_url, mode=config.redis_mode)
        await cache.initialize()
        bot = _LifecycleBot(config, cache)
        try:
            try:
                await setup_polling_lock(bot)
            except PollingLockBusy as exc:
                _emit({"event": "busy", "pid": os.getpid(), "message": str(exc)})
                return
            _emit({"event": "acquired", "pid": os.getpid(), "owner": bot._polling_lock_owner})
            # Hold the lease until the parent says "release" (or closes stdin).
            await asyncio.get_running_loop().run_in_executor(None, sys.stdin.readline)
            assert bot._polling_lock is not None
            await bot._polling_lock.release()
            _emit({"event": "released", "pid": os.getpid(), "owner": bot._polling_lock_owner})
        finally:
            await bot.cancel_heartbeat()
            await cache.close()

    asyncio.run(run())
    return 0


class _OwnerB:
    """Drive the owner-B subprocess: one JSON event per line on stdout."""

    def __init__(self, redis_url: str, mode: str = "multi_instance") -> None:
        env = os.environ.copy()
        env["PYTHONPATH"] = os.pathsep.join(
            p for p in (str(_REPO_ROOT), env.get("PYTHONPATH", "")) if p
        )
        env["PYTHONIOENCODING"] = "utf-8"
        self.proc = subprocess.Popen(
            [sys.executable, str(Path(__file__).resolve()), "owner-b", redis_url, mode],
            cwd=_REPO_ROOT,
            env=env,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
        )
        self._stderr: list[str] = []
        self._drain = threading.Thread(target=self._drain_stderr, daemon=True)
        self._drain.start()

    def _drain_stderr(self) -> None:
        assert self.proc.stderr is not None
        for line in self.proc.stderr:
            self._stderr.append(line)

    def next_event(self) -> dict[str, Any]:
        assert self.proc.stdout is not None
        line = self.proc.stdout.readline()
        if not line:
            rc = self.proc.wait(timeout=30)
            pytest.fail(f"owner B exited early rc={rc}; stderr:\n{''.join(self._stderr)}")
        event: dict[str, Any] = json.loads(line)
        return event

    def send(self, command: str) -> None:
        assert self.proc.stdin is not None
        self.proc.stdin.write(command + "\n")
        self.proc.stdin.flush()

    def finish(self, timeout: float = 60.0) -> int:
        with contextlib.suppress(Exception):
            if self.proc.stdin is not None:
                self.proc.stdin.close()
        try:
            rc = self.proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            self.proc.kill()
            rc = self.proc.wait(timeout=10)
        self._drain.join(timeout=5)
        return rc

    def stderr_text(self) -> str:
        return "".join(self._stderr)


@contextlib.contextmanager
def _owner_b(redis_url: str) -> Iterator[_OwnerB]:
    owner = _OwnerB(redis_url)
    try:
        yield owner
    finally:
        rc = owner.finish()
        assert rc == 0, f"owner B exited rc={rc}; stderr:\n{owner.stderr_text()}"


# ---------------------------------------------------------------------------
# Scenario 1 — disabled
# ---------------------------------------------------------------------------


@pytest.mark.timeout(120)
async def test_disabled_mode_never_imports_or_contacts_redis(live_redis: LiveRedis) -> None:
    """disabled: no client, cache miss/no-store, no durable features, no lock claim."""
    for label, url in (("reachable", live_redis.url), ("unreachable", _DEAD_REDIS_URL)):
        with _RedisClientPackagesAbsent():
            cache = CacheLayerManager(redis_url=url, mode=RedisMode.DISABLED)
            await cache.initialize()  # would raise ImportError if it touched redis-py
            assert cache.capability is RedisCapability.DISABLED, label
            assert cache.redis is None, label

            await cache.store_exact("search", f"key-{label}", {"stored": label})
            assert await cache.get_exact("search", f"key-{label}") is None, label  # no-store
            assert await cache.clear_by_tier("search") == 0, label

            # Public core: the lifecycle polling gate runs and claims nothing.
            bot = _LifecycleBot(_bot_config("disabled", url), cache)
            await setup_polling_lock(bot)
            assert bot._polling_lock is None and bot._polling_lock_task is None, label
            assert "redis" not in sys.modules and "redisvl" not in sys.modules, label
            await cache.close()

        # Redis-only durable features are unavailable and never replaced with memory.
        setup_handoff_services(bot)
        assert bot._handoff_state is None, label
        assert bot._lead_sink is None, label

        signal = redis_capability_signal(bot)
        assert signal.severity is StartupSeverity.OK, label
        assert "cache disabled (miss/no-store)" in signal.summary, label
        assert "no distributed polling lock" in signal.summary, label

    # The reachable, authenticated server saw no connection and stores nothing.
    async with _observer(live_redis) as observer:
        assert await observer.dbsize() == 0
        assert await observer.get(POLLING_LOCK_KEY) is None


# ---------------------------------------------------------------------------
# Scenario 2 — single_instance
# ---------------------------------------------------------------------------


@pytest.mark.timeout(120)
async def test_single_instance_cache_roundtrip_polls_without_lock_and_degrades_on_loss(
    live_redis: LiveRedis,
) -> None:
    """single_instance: real cache write/read/TTL/delete; one poller, no lock; loss fails open."""
    cache = CacheLayerManager(redis_url=live_redis.url, mode=RedisMode.SINGLE_INSTANCE)
    await cache.initialize()
    assert cache.capability is RedisCapability.ENABLED

    # write / read
    await cache.store_exact("search", "durable", {"answer": 42})
    assert await cache.get_exact("search", "durable") == {"answer": 42}

    # TTL: a 1s entry expires while the default-TTL entry survives
    await cache.store_exact("search", "short-lived", {"ttl": 1}, ttl=1)
    assert await cache.get_exact("search", "short-lived") == {"ttl": 1}
    await asyncio.sleep(1.5)
    assert await cache.get_exact("search", "short-lived") is None
    assert await cache.get_exact("search", "durable") == {"answer": 42}

    # delete
    assert await cache.clear_by_tier("search") >= 1
    assert await cache.get_exact("search", "durable") is None
    async with _observer(live_redis) as observer:
        assert [key async for key in observer.scan_iter(match="search:*")] == []

    # One bot lifecycle may poll — without any distributed-lock claim.
    bot = _LifecycleBot(_bot_config("single_instance", live_redis.url), cache)
    await setup_polling_lock(bot)
    assert bot._polling_lock is None and bot._polling_lock_task is None
    async with _observer(live_redis) as observer:
        assert await observer.get(POLLING_LOCK_KEY) is None
    signal = redis_capability_signal(bot)
    assert signal.severity is StartupSeverity.OK
    assert "durable Redis capabilities enabled" in signal.summary
    assert "no distributed polling lock" in signal.summary

    # Redis loss at startup (wrong password / unreachable): cache fails open,
    # durable features are unavailable, and the process may still poll.
    for label, url in (
        ("wrong-password", live_redis.url_with_password("wrong-password")),
        ("unreachable", _DEAD_REDIS_URL),
    ):
        degraded = CacheLayerManager(redis_url=url, mode=RedisMode.SINGLE_INSTANCE)
        await degraded.initialize()
        try:
            assert degraded.capability is RedisCapability.DEGRADED, label
            await degraded.store_exact("search", "lost", {"x": 1})
            assert await degraded.get_exact("search", "lost") is None, label

            lost_bot = _LifecycleBot(_bot_config("single_instance", url), degraded)
            setup_handoff_services(lost_bot)
            assert lost_bot._handoff_state is None and lost_bot._lead_sink is None, label
            await setup_polling_lock(lost_bot)
            assert lost_bot._polling_lock is None, label
            degraded_signal = redis_capability_signal(lost_bot)
            assert degraded_signal.severity is StartupSeverity.DEGRADED, label
            assert "cache miss/no-store" in degraded_signal.summary, label
        finally:
            await degraded.close()
    async with _observer(live_redis) as observer:
        assert [key async for key in observer.scan_iter(match="search:*")] == []

    # Redis loss mid-run: a value stored while connected is not served from
    # memory afterwards, writes stay silent no-ops, nothing raises.
    await cache.store_exact("search", "before-loss", {"answer": 42})
    assert await cache.get_exact("search", "before-loss") == {"answer": 42}
    live_redis.kill()
    assert await cache.get_exact("search", "before-loss") is None
    await cache.store_exact("search", "after-loss", {"answer": 43})
    assert await cache.get_exact("search", "after-loss") is None
    await cache.close()


# ---------------------------------------------------------------------------
# Scenario 3 — multi_instance two-owner polling lock
# ---------------------------------------------------------------------------


@pytest.mark.timeout(180)
async def test_multi_instance_two_owner_lock_contention_renewal_loss_and_takeover(
    live_redis: LiveRedis,
) -> None:
    """multi_instance: A holds, B (other process) is refused, renewal, loss stops A, B takes over."""
    config = _bot_config("multi_instance", live_redis.url)
    cache_a = CacheLayerManager(redis_url=live_redis.url, mode=RedisMode.MULTI_INSTANCE)
    await cache_a.initialize()
    assert cache_a.capability is RedisCapability.ENABLED
    bot_a = _LifecycleBot(config, cache_a)
    transcript: list[str] = []

    try:
        # 1. Owner A acquires through the real lifecycle gate.
        await setup_polling_lock(bot_a)
        assert bot_a._polling_lock is not None
        assert isinstance(bot_a._polling_lock_task, asyncio.Task)
        owner_a = bot_a._polling_lock_owner
        assert owner_a == f"{socket.gethostname()}:{os.getpid()}"
        async with _observer(live_redis) as observer:
            assert await observer.get(POLLING_LOCK_KEY) == owner_a
            pttl_acquired = await observer.pttl(POLLING_LOCK_KEY)
        assert 0 < pttl_acquired <= 90_000
        transcript.append(f"A acquired: owner={owner_a} pttl_ms={pttl_acquired}")

        # 2. Owner B (independent OS process) cannot poll and is told who owns it.
        with _owner_b(live_redis.url) as owner_b:
            busy = owner_b.next_event()
        assert busy["event"] == "busy", busy
        assert busy["pid"] != os.getpid()
        assert f"owner={owner_a!r}" in busy["message"], busy["message"]
        assert "pttl_ms=" in busy["message"] and "pttl_ms=None" not in busy["message"]
        assert "stop the other bot instance first" in busy["message"]
        transcript.append(f"B(pid={busy['pid']}) refused: {busy['message']}")
        async with _observer(live_redis) as observer:
            assert await observer.get(POLLING_LOCK_KEY) == owner_a  # A still owns it

        # 3. Heartbeat renews A's lease (public lifecycle tick).
        await asyncio.sleep(1.5)
        async with _observer(live_redis) as observer:
            pttl_before_renewal = await observer.pttl(POLLING_LOCK_KEY)
        assert 0 < pttl_before_renewal < pttl_acquired
        await bot_a._polling_lock_heartbeat_tick()
        assert bot_a._polling_lock_consecutive_failures == 0
        async with _observer(live_redis) as observer:
            pttl_after_renewal = await observer.pttl(POLLING_LOCK_KEY)
            assert await observer.get(POLLING_LOCK_KEY) == owner_a
        assert pttl_after_renewal > pttl_before_renewal
        assert pttl_after_renewal > 89_000
        transcript.append(
            f"A heartbeat renewed: pttl_ms {pttl_before_renewal} -> {pttl_after_renewal}"
        )

        # 4. Forced lease loss (server-side) stops A after the tolerated retries.
        async with _observer(live_redis) as observer:
            assert await observer.delete(POLLING_LOCK_KEY) == 1
        await bot_a._polling_lock_heartbeat_tick()
        assert bot_a._polling_lock_consecutive_failures == 1
        assert bot_a.dp.stop_polling_calls == 0  # first failure: retry, keep polling
        await bot_a._polling_lock_heartbeat_tick()
        assert bot_a._polling_lock_consecutive_failures == 2
        assert bot_a.dp.stop_polling_calls == 1  # second failure: polling stopped
        transcript.append("A lease lost: 2 failed heartbeats -> dp.stop_polling() called once")

        # 5. Owner B takes over now that the lease is gone, then releases cleanly.
        with _owner_b(live_redis.url) as owner_b:
            acquired = owner_b.next_event()
            assert acquired["event"] == "acquired", acquired
            owner_b_token = acquired["owner"]
            # The child reports its own pid: on Windows the venv python.exe is a
            # launcher, so Popen.pid is not the interpreter's pid.
            assert acquired["pid"] != os.getpid()
            assert owner_b_token == f"{socket.gethostname()}:{acquired['pid']}"
            assert owner_b_token != owner_a
            async with _observer(live_redis) as observer:
                assert await observer.get(POLLING_LOCK_KEY) == owner_b_token
                assert 0 < await observer.pttl(POLLING_LOCK_KEY) <= 90_000
            transcript.append(f"B(pid={acquired['pid']}) acquired: owner={owner_b_token}")

            owner_b.send("release")
            released = owner_b.next_event()
            assert released["event"] == "released", released
        async with _observer(live_redis) as observer:
            assert await observer.get(POLLING_LOCK_KEY) is None
        transcript.append("B released: lock key removed")

        # 6. An un-renewed lease expires on its own (public runtime lock API).
        async with _observer(live_redis) as observer:
            expiring = RedisPollingLock(redis=observer, key=POLLING_LOCK_KEY, ttl_sec=1)
            await expiring.acquire("expiring-owner")
            assert await observer.get(POLLING_LOCK_KEY) == "expiring-owner"
            await asyncio.sleep(1.3)
            assert await observer.get(POLLING_LOCK_KEY) is None
        transcript.append("un-renewed 1s lease expired without heartbeat")
    finally:
        await bot_a.cancel_heartbeat()
        if bot_a._polling_lock is not None:
            # Mirrors stop_bot(): releasing a lost lease must not crash teardown.
            with contextlib.suppress(Exception):
                await bot_a._polling_lock.release()
        await cache_a.close()

    async with _observer(live_redis) as observer:
        assert await observer.get(POLLING_LOCK_KEY) is None
        assert [key async for key in observer.scan_iter(match="telegram-bot:*")] == []
    print("\n".join(("polling-lock transcript:", *transcript)))


# ---------------------------------------------------------------------------
# Scenario 4 — startup fails only where the mode requires Redis
# ---------------------------------------------------------------------------


async def _preflight_failed_deps(config: Any) -> tuple[list[str], Any]:
    """Run the public preflight gate; return (fatal deps, startup report)."""
    from telegram_bot.preflight import PreflightError, check_dependencies

    try:
        result = await check_dependencies(config, log_summary=False)
    except PreflightError as exc:
        return list(exc.failed_deps), exc.report
    return [], result.report


def _redis_mode_signal(report: Any) -> Any:
    return next(signal for signal in report.signals if signal.source == "redis_mode")


@pytest.mark.timeout(120)
async def test_startup_fails_only_where_the_selected_mode_requires_redis(
    live_redis: LiveRedis, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Wrong password / unavailable Redis: fatal in multi_instance, degraded in single, ignored in disabled."""
    import telegram_bot.preflight.checks as preflight_checks

    # Keep the three real attempts; drop only the 5s pause between them.
    monkeypatch.setattr(preflight_checks, "CRITICAL_RETRY_DELAY", 0.05)
    wrong_password = live_redis.url_with_password("wrong-password")

    # multi_instance: wrong password and unavailable Redis are both fatal.
    for label, url in (("wrong-password", wrong_password), ("unreachable", _DEAD_REDIS_URL)):
        failed, report = await _preflight_failed_deps(_bot_config("multi_instance", url))
        assert "redis" in failed, (label, failed)
        assert _redis_mode_signal(report).severity is StartupSeverity.FAILED, label
        assert report.final_severity is StartupSeverity.FAILED, label

    # multi_instance with the right password: Redis passes; whatever else
    # fails, it is never Redis, and preflight's synthetic keys are cleaned up.
    failed, report = await _preflight_failed_deps(_bot_config("multi_instance", live_redis.url))
    assert not {"redis", "redis_cache"} & set(failed), failed
    assert _redis_mode_signal(report).severity is StartupSeverity.OK
    assert "Redis reachable (required)" in _redis_mode_signal(report).summary
    async with _observer(live_redis) as observer:
        assert [key async for key in observer.scan_iter(match="*__preflight_test")] == []

    # single_instance: the same broken Redis is degraded, never fatal.
    for label, url in (("wrong-password", wrong_password), ("unreachable", _DEAD_REDIS_URL)):
        failed, report = await _preflight_failed_deps(_bot_config("single_instance", url))
        assert "redis" not in failed and "redis_cache" not in failed, (label, failed)
        assert _redis_mode_signal(report).severity is StartupSeverity.DEGRADED, label
        assert "cache will fail open" in _redis_mode_signal(report).summary, label

    # disabled: Redis is never probed, even with a broken URL.
    failed, report = await _preflight_failed_deps(_bot_config("disabled", wrong_password))
    assert not any(dep.startswith("redis") for dep in failed), failed
    assert _redis_mode_signal(report).severity is StartupSeverity.OK
    assert "no connection attempted" in _redis_mode_signal(report).summary
    assert not any(signal.source in {"redis", "redis_cache"} for signal in report.signals)

    # Polling gate: multi_instance refuses to poll without a live backend.
    dead_cache = CacheLayerManager(redis_url=_DEAD_REDIS_URL, mode=RedisMode.MULTI_INSTANCE)
    await dead_cache.initialize()
    try:
        assert dead_cache.capability is RedisCapability.DEGRADED
        bot = _LifecycleBot(_bot_config("multi_instance", _DEAD_REDIS_URL), dead_cache)
        with pytest.raises(RuntimeError, match="requires a live Redis connection"):
            await setup_polling_lock(bot)
        assert bot._polling_lock is None
        signal = redis_capability_signal(bot)
        assert signal.severity is StartupSeverity.DEGRADED
        assert "distributed polling lock will be required before polling" in signal.summary
    finally:
        await dead_cache.close()

    # ...while the live backend lets the same mode poll (and clean up after itself).
    live_cache = CacheLayerManager(redis_url=live_redis.url, mode=RedisMode.MULTI_INSTANCE)
    await live_cache.initialize()
    bot = _LifecycleBot(_bot_config("multi_instance", live_redis.url), live_cache)
    try:
        await setup_polling_lock(bot)
        assert bot._polling_lock is not None
    finally:
        await bot.cancel_heartbeat()
        if bot._polling_lock is not None:
            await bot._polling_lock.release()
        await live_cache.close()
    async with _observer(live_redis) as observer:
        assert await observer.get(POLLING_LOCK_KEY) is None


if __name__ == "__main__":  # pragma: no cover - owner-B subprocess entry point
    if len(sys.argv) >= 4 and sys.argv[1] == "owner-b":
        raise SystemExit(_owner_b_main(sys.argv[2], sys.argv[3]))
    raise SystemExit("usage: python test_redis_modes_live.py owner-b <redis_url> <mode>")

"""Run-owned disposable Redis fixtures for the load lane (#3447).

The eviction load is physically incapable of touching ambient Redis:
every target comes from a run-owned disposable container with a unique
run label, a random credential, and an ephemeral loopback port backed by
tmpfs. Nothing in this module reads ``REDIS_URL``, the repository
``.env``, or any ambient endpoint; Docker absence fails the explicit
load lane instead of redirecting to ambient Redis.
"""

from __future__ import annotations

import contextlib
import secrets
import shutil
import socket
import subprocess
import time
import uuid
from collections.abc import Generator
from dataclasses import dataclass
from typing import Any

import pytest


IMAGE = "redis:8.10.1"
MAXMEMORY = "64mb"
MAXMEMORY_POLICY = "volatile-lfu"
RUN_LABEL_KEY = "rag.load.run"
OWNER_LABEL_KEY = "rag.load.owner"
OWNER_LABEL_VALUE = "pytest-load-lane"
_DEFAULT_TIMEOUT = 120


class DockerUnavailable(RuntimeError):
    """Raised when Docker is required but not usable."""


@dataclass(frozen=True)
class DisposableRedis:
    """Handle of one run-owned disposable Redis container."""

    run_id: str
    container_id: str
    container_name: str
    password: str
    port: int
    url: str
    maxmemory_bytes: int


def _docker(args: list[str], *, timeout: int = _DEFAULT_TIMEOUT) -> str:
    if shutil.which("docker") is None:
        raise DockerUnavailable("docker executable not found on PATH")
    proc = subprocess.run(["docker", *args], capture_output=True, text=True, timeout=timeout)
    if proc.returncode != 0:
        raise DockerUnavailable(f"docker {' '.join(args)} failed: {proc.stderr.strip()}")
    return proc.stdout.strip()


def docker_available() -> None:
    """Fail the explicit load lane when Docker is unusable (#3447)."""
    try:
        _docker(["info", "--format", "{{.ServerVersion}}"], timeout=60)
    except (DockerUnavailable, subprocess.TimeoutExpired) as exc:
        pytest.fail(
            f"Docker is required for the Redis eviction load lane and must not "
            f"fall back to ambient Redis: {exc}"
        )


def _free_loopback_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def assert_run_owned_target(
    url: str,
    *,
    container_id: str,
    label: str,
    run_id: str,
    password: str,
) -> None:
    """Refuse any target that is not the verified run-owned container (#3447).

    Rejects remote hosts, unlabeled or default-port endpoints, missing
    credentials, and missing/mismatched run labels before any connection
    is handed to the load tests.
    """
    from redis.asyncio.connection import parse_url

    parsed = parse_url(url)
    host = parsed.get("host")
    port = parsed.get("port")
    cred = parsed.get("password")
    if host != "127.0.0.1":
        raise ValueError(
            f"refusing non-loopback load target host {host!r}; "
            "only 127.0.0.1 run-owned containers are allowed"
        )
    if not port or port == 6379:
        raise ValueError(
            f"refusing load target on default/unset port {port!r}; "
            "targets must use an ephemeral port"
        )
    if not cred:
        raise ValueError("refusing load target without a random credential")
    if password != cred:
        raise ValueError(
            "refusing load target whose URL credential does not match the run credential"
        )
    if not container_id:
        raise ValueError("refusing load target without a container id")
    if label != run_id or not run_id:
        raise ValueError(
            f"refusing load target with missing/mismatched run label {label!r} "
            f"(expected {run_id!r})"
        )


def _wait_ready(url: str, *, timeout_sec: float = 30.0) -> None:
    import asyncio

    import redis.asyncio as redis

    async def _ping() -> bool:
        client = redis.from_url(url, decode_responses=True)
        try:
            # redis-py types ping() as Awaitable[bool] | bool; the async
            # client always returns an awaitable at runtime.
            return bool(await client.ping())  # type: ignore[misc]
        finally:
            await client.aclose()

    deadline = time.monotonic() + timeout_sec
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        try:
            if asyncio.run(_ping()):
                return
        except Exception as exc:
            last_error = exc
        time.sleep(0.25)
    raise DockerUnavailable(
        f"disposable Redis did not become ready within {timeout_sec}s: {last_error}"
    )


def _run_async(coro: Any) -> Any:
    import asyncio

    return asyncio.run(coro)


def _start_disposable(run_id: str, *, role: str) -> DisposableRedis:
    container_name = f"rag-loadtest-{role}-{run_id}"
    password = secrets.token_urlsafe(16)
    port = _free_loopback_port()
    container_id = _docker(
        [
            "run",
            "-d",
            "--rm",
            "--name",
            container_name,
            "--label",
            f"{RUN_LABEL_KEY}={run_id}",
            "--label",
            f"{OWNER_LABEL_KEY}={OWNER_LABEL_VALUE}",
            "-p",
            f"127.0.0.1:{port}:6379",
            "--tmpfs",
            "/data",
            IMAGE,
            "redis-server",
            "--requirepass",
            password,
            "--maxmemory",
            MAXMEMORY,
            "--maxmemory-policy",
            MAXMEMORY_POLICY,
            "--save",
            "",
            "--appendonly",
            "no",
        ]
    )
    handle = DisposableRedis(
        run_id=run_id,
        container_id=container_id,
        container_name=container_name,
        password=password,
        port=port,
        url=f"redis://:{password}@127.0.0.1:{port}/0",
        maxmemory_bytes=64 * 1024 * 1024,
    )
    _verify_container_label(handle)
    _wait_ready(handle.url)
    return handle


def _verify_container_label(handle: DisposableRedis) -> None:
    """Confirm the exact container id still carries this run's labels."""
    listing = _docker(
        [
            "ps",
            "--filter",
            f"id={handle.container_id}",
            "--filter",
            f"label={RUN_LABEL_KEY}={handle.run_id}",
            "--format",
            "{{.ID}}",
        ]
    )
    # `docker ps --format {{.ID}}` prints the truncated id; match by prefix.
    ids = [line.strip() for line in listing.splitlines() if line.strip()]
    if not any(handle.container_id.startswith(short) for short in ids):
        raise DockerUnavailable(
            f"container {handle.container_id} does not carry run label "
            f"{RUN_LABEL_KEY}={handle.run_id}"
        )


def _labels_match(handle: DisposableRedis) -> bool:
    try:
        out = _docker(
            [
                "inspect",
                "--format",
                f'{{{{index .Config.Labels "{RUN_LABEL_KEY}"}}}}|'
                f'{{{{index .Config.Labels "{OWNER_LABEL_KEY}"}}}}',
                handle.container_id,
            ],
            timeout=60,
        )
    except (DockerUnavailable, subprocess.TimeoutExpired):
        return False
    return out.strip() == f"{handle.run_id}|{OWNER_LABEL_VALUE}"


def _remove_disposable(handle: DisposableRedis) -> None:
    """Remove only the exact run-owned container id, after label re-check."""
    if not _labels_match(handle):
        return
    with contextlib.suppress(DockerUnavailable):
        _docker(["rm", "-f", handle.container_id], timeout=60)


@pytest.fixture(scope="session")
def load_redis_target() -> Generator[DisposableRedis, None, None]:
    """Run-owned disposable eviction target (unique label/credential/port)."""
    docker_available()
    handle = _start_disposable(uuid.uuid4().hex[:12], role="target")
    yield handle
    _remove_disposable(handle)


@pytest.fixture(scope="session")
def foreign_redis_canary() -> Generator[DisposableRedis, None, None]:
    """A separate foreign Redis used as an untouched negative control.

    Carries a persistent and an expiring sentinel key; the load tests
    assert both survive and its eviction counter is unchanged.
    """
    docker_available()
    handle = _start_disposable(uuid.uuid4().hex[:12], role="foreign")

    import redis.asyncio as redis

    async def _seed() -> None:
        client = redis.from_url(handle.url, decode_responses=True)
        try:
            await client.set("rag:foreign_sentinel_persistent", "keepforever")
            await client.setex("rag:foreign_sentinel_expiring", 3600, "hello")
        finally:
            await client.aclose()

    _run_async(_seed())
    yield handle
    _remove_disposable(handle)

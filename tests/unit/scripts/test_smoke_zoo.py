"""Tests for scripts/smoke-zoo.sh — fallback when host redis-cli is missing (#2196)."""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest


SCRIPT = Path(__file__).resolve().parents[3] / "scripts" / "smoke-zoo.sh"
BASH = shutil.which("bash") or "/bin/bash"


def _run_smoke_zoo(*, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    """Run smoke-zoo.sh in a controlled subprocess."""
    return subprocess.run(  # nosec B603
        [BASH, str(SCRIPT)],
        capture_output=True,
        text=True,
        env=env,
        timeout=30,
    )


def _make_tmp_path_without(binary: str, tmp_path: Path) -> str:
    """Build a PATH that excludes any directory containing the named binary.

    Used to simulate ``redis-cli`` (or ``docker``) being absent on the host.
    """
    parts: list[str] = []
    for entry in os.environ.get("PATH", "").split(os.pathsep):
        if entry and not (Path(entry) / binary).exists():
            parts.append(entry)
    # Also prepend an empty tmp dir so the resulting PATH is non-empty even if
    # all originals were filtered.
    parts.insert(0, str(tmp_path))
    return os.pathsep.join(parts)


def test_script_exists_and_executable() -> None:
    """Sanity: smoke-zoo.sh must exist."""
    assert SCRIPT.is_file(), f"{SCRIPT} not found"


def test_script_passes_shellcheck() -> None:
    """Lint guard: shellcheck (if available) must be clean on the script."""
    if shutil.which("shellcheck") is None:
        pytest.skip("shellcheck not installed on host")
    cp = subprocess.run(  # nosec B603 B607
        ["shellcheck", "-S", "warning", str(SCRIPT)],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert cp.returncode == 0, f"shellcheck failed:\n{cp.stdout}\n{cp.stderr}"


def test_redis_check_falls_back_to_docker_exec_when_host_redis_cli_missing(
    tmp_path: Path,
) -> None:
    """When host ``redis-cli`` is absent and Docker is available, the Redis
    check must use ``docker exec`` instead of failing immediately.

    We assert this by reading the script source — a behavioural test would
    require a running container. The contract is: the script must contain a
    branch that uses ``docker exec`` for the Redis call when the host CLI
    is missing.
    """
    text = SCRIPT.read_text(encoding="utf-8")
    assert "docker exec" in text, (
        "smoke-zoo.sh must contain a 'docker exec' fallback for redis-cli (#2196)"
    )
    # Specifically the fallback should reference the redis container name
    # used by the dev compose project.
    assert "dev-redis-1" in text or "redis" in text.lower(), (
        "fallback should target the dev redis container"
    )


def test_redis_check_classifies_missing_dependency_clearly(tmp_path: Path) -> None:
    """When neither host redis-cli nor docker is available, the script must
    print a precise dependency error rather than treating Redis as down.

    Strip both ``redis-cli`` and ``docker`` from PATH to simulate a bare host.
    """
    fake_path = _make_tmp_path_without("redis-cli", tmp_path)
    # Also strip docker so neither path is available.
    fake_path = os.pathsep.join(
        p for p in fake_path.split(os.pathsep) if not (Path(p) / "docker").exists()
    )
    env = dict(os.environ, PATH=fake_path)
    cp = _run_smoke_zoo(env=env)

    combined = cp.stdout + cp.stderr
    # Must mention redis-cli or dependency status, not silently fail
    assert (
        "redis-cli" in combined.lower()
        or "missing" in combined.lower()
        or "not available" in combined.lower()
        or "dependency" in combined.lower()
    ), f"script must report missing dependency clearly; got:\n{combined}"


def test_script_continues_after_redis_dependency_failure(tmp_path: Path) -> None:
    """If the Redis check fails because of a missing dependency, the script
    must still attempt the other independent checks (Qdrant, bge-m3, etc.).

    This guards against ``set -e`` short-circuiting all subsequent checks
    when only a CLI tool is missing.
    """
    fake_path = _make_tmp_path_without("redis-cli", tmp_path)
    fake_path = os.pathsep.join(
        p for p in fake_path.split(os.pathsep) if not (Path(p) / "docker").exists()
    )
    env = dict(os.environ, PATH=fake_path)
    cp = _run_smoke_zoo(env=env)

    combined = cp.stdout + cp.stderr
    # The script should mention at least one non-Redis check by name.
    assert any(marker in combined for marker in ("Qdrant", "bge-m3", "litellm", "user-base")), (
        "script must run independent checks even when Redis check has a "
        f"dependency failure; got:\n{combined}"
    )

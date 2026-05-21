"""Contract tests for scripts/swarm_opencode_run_unattended.sh."""

import json
import os
import subprocess
from pathlib import Path

SCRIPT = str(Path("scripts/swarm_opencode_run_unattended.sh").resolve())


def _make_stub(tmp_path: Path, exit_code: int = 0) -> str:
    """Create a stub opencode script that prints env and args to stdout."""
    stub = tmp_path / "opencode"
    stub.write_text(
        f"#!/usr/bin/env bash\n"
        f"echo \"OPENCODE_CONFIG=${{OPENCODE_CONFIG:-}}\"\n"
        f"echo \"OPENCODE_CONFIG_CONTENT=${{OPENCODE_CONFIG_CONTENT:-}}\"\n"
        f"echo \"ARGS=$*\"\n"
        f"exit {exit_code}\n",
        encoding="utf-8",
    )
    stub.chmod(0o755)
    return str(tmp_path)


def _clean_env() -> dict[str, str]:
    """Return a copy of os.environ without OPENCODE_CONFIG* variables."""
    env = os.environ.copy()
    env.pop("OPENCODE_CONFIG", None)
    env.pop("OPENCODE_CONFIG_CONTENT", None)
    return env


def test_default_injection_sets_opencode_config_content(tmp_path: Path) -> None:
    """When neither OPENCODE_CONFIG nor OPENCODE_CONFIG_CONTENT is set, the stub receives OPENCODE_CONFIG_CONTENT."""
    # Arrange
    stub_dir = _make_stub(tmp_path)
    env = _clean_env()
    env["PATH"] = stub_dir + os.pathsep + env.get("PATH", "")

    # Act
    result = subprocess.run(
        ["bash", SCRIPT],
        env=env,
        capture_output=True,
        text=True,
    )

    # Assert
    assert result.returncode == 0
    assert 'OPENCODE_CONFIG_CONTENT={"permission":"allow"}' in result.stdout


def test_respects_existing_opencode_config(tmp_path: Path) -> None:
    """When OPENCODE_CONFIG is already set, OPENCODE_CONFIG_CONTENT is NOT injected."""
    # Arrange
    stub_dir = _make_stub(tmp_path)
    env = _clean_env()
    env["PATH"] = stub_dir + os.pathsep + env.get("PATH", "")
    env["OPENCODE_CONFIG"] = "/custom/path/opencode.json"

    # Act
    result = subprocess.run(
        ["bash", SCRIPT],
        env=env,
        capture_output=True,
        text=True,
    )

    # Assert
    assert result.returncode == 0
    assert "OPENCODE_CONFIG_CONTENT=" in result.stdout
    # The value should be empty (not injected)
    for line in result.stdout.splitlines():
        if line.startswith("OPENCODE_CONFIG_CONTENT="):
            assert line == "OPENCODE_CONFIG_CONTENT="


def test_respects_existing_opencode_config_content(tmp_path: Path) -> None:
    """When OPENCODE_CONFIG_CONTENT is already set, the value is not overwritten."""
    # Arrange
    stub_dir = _make_stub(tmp_path)
    env = _clean_env()
    env["PATH"] = stub_dir + os.pathsep + env.get("PATH", "")
    env["OPENCODE_CONFIG_CONTENT"] = '{"permission":"deny"}'

    # Act
    result = subprocess.run(
        ["bash", SCRIPT],
        env=env,
        capture_output=True,
        text=True,
    )

    # Assert
    assert result.returncode == 0
    assert 'OPENCODE_CONFIG_CONTENT={"permission":"deny"}' in result.stdout


def test_passes_all_arguments_through(tmp_path: Path) -> None:
    """Arguments passed to the wrapper appear in the stub's argv."""
    # Arrange
    stub_dir = _make_stub(tmp_path)
    env = _clean_env()
    env["PATH"] = stub_dir + os.pathsep + env.get("PATH", "")

    # Act
    result = subprocess.run(
        ["bash", SCRIPT, "--model", "gpt-4", "--verbose"],
        env=env,
        capture_output=True,
        text=True,
    )

    # Assert
    assert result.returncode == 0
    assert "ARGS=--model gpt-4 --verbose" in result.stdout


def test_exit_127_when_opencode_missing(tmp_path: Path) -> None:
    """When opencode is not in PATH, script exits 127."""
    # Arrange
    env = _clean_env()
    # Use a PATH with only system dirs (no opencode) and the empty tmp dir
    env["PATH"] = str(tmp_path) + ":/usr/bin:/bin"

    # Act
    result = subprocess.run(
        ["/usr/bin/bash", SCRIPT],
        env=env,
        capture_output=True,
        text=True,
    )

    # Assert
    assert result.returncode == 127


def test_friendly_diagnostic_when_opencode_missing(tmp_path: Path) -> None:
    """When opencode is missing, stderr contains a helpful message."""
    # Arrange
    env = _clean_env()
    # Use a PATH with only system dirs (no opencode) and the empty tmp dir
    env["PATH"] = str(tmp_path) + ":/usr/bin:/bin"

    # Act
    result = subprocess.run(
        ["/usr/bin/bash", SCRIPT],
        env=env,
        capture_output=True,
        text=True,
    )

    # Assert
    assert "opencode" in result.stderr.lower()
    assert "not" in result.stderr.lower() or "ERROR" in result.stderr


def test_exits_with_opencode_success_code(tmp_path: Path) -> None:
    """When the stub exits 0, the wrapper exits 0."""
    # Arrange
    stub_dir = _make_stub(tmp_path, exit_code=0)
    env = _clean_env()
    env["PATH"] = stub_dir + os.pathsep + env.get("PATH", "")

    # Act
    result = subprocess.run(
        ["bash", SCRIPT],
        env=env,
        capture_output=True,
        text=True,
    )

    # Assert
    assert result.returncode == 0


def test_exits_with_opencode_failure_code(tmp_path: Path) -> None:
    """When the stub exits non-zero (e.g., 42), the wrapper exits with the same code."""
    # Arrange
    stub_dir = _make_stub(tmp_path, exit_code=42)
    env = _clean_env()
    env["PATH"] = stub_dir + os.pathsep + env.get("PATH", "")

    # Act
    result = subprocess.run(
        ["bash", SCRIPT],
        env=env,
        capture_output=True,
        text=True,
    )

    # Assert
    assert result.returncode == 42


def test_injected_config_is_valid_json_with_permission_allow(tmp_path: Path) -> None:
    """The injected OPENCODE_CONFIG_CONTENT is valid JSON and contains 'permission': 'allow'."""
    # Arrange
    stub_dir = _make_stub(tmp_path)
    env = _clean_env()
    env["PATH"] = stub_dir + os.pathsep + env.get("PATH", "")

    # Act
    result = subprocess.run(
        ["bash", SCRIPT],
        env=env,
        capture_output=True,
        text=True,
    )

    # Assert
    assert result.returncode == 0
    for line in result.stdout.splitlines():
        if line.startswith("OPENCODE_CONFIG_CONTENT="):
            value = line[len("OPENCODE_CONFIG_CONTENT="):]
            parsed = json.loads(value)
            assert parsed["permission"] == "allow"
            break
    else:
        raise AssertionError("OPENCODE_CONFIG_CONTENT not found in stub output")

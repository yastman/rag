"""Tests for scripts/wsl_agent_watchers.py — WSL auto-start watcher services."""

from __future__ import annotations

import importlib.util
import os
import shlex
import subprocess
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[3]
SCRIPT_PATH = REPO_ROOT / "scripts" / "wsl_agent_watchers.py"


def _load_module():
    """Import the script as a module for white-box testing."""
    spec = importlib.util.spec_from_file_location("wsl_agent_watchers_under_test", SCRIPT_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# ---------------------------------------------------------------------------
# Sanity / structural tests
# ---------------------------------------------------------------------------


def test_script_exists_and_parses() -> None:
    """Sanity: the script must exist and compile cleanly."""
    assert SCRIPT_PATH.is_file(), f"{SCRIPT_PATH} not found"
    subprocess.run(  # nosec B603
        [sys.executable, "-m", "py_compile", str(SCRIPT_PATH)],
        check=True,
        capture_output=True,
    )


# ---------------------------------------------------------------------------
# Unit content generation tests
# ---------------------------------------------------------------------------


def test_create_codeindexer_unit_defaults() -> None:
    """codeindexer unit must use the correct ExecStart command line."""
    mod = _load_module()
    unit = mod.create_codeindexer_unit(
        repo_root="/home/user/projects/rag-fresh",
        codeindexer_bin="/home/user/.local/bin/codeindexer",
    )

    assert "[Unit]" in unit
    assert "Description=CodeIndexer MCP Server" in unit
    assert "[Service]" in unit
    assert "ExecStart=" in unit
    assert "ExecStart=/home/user/.local/bin/codeindexer serve" in unit
    assert "--host 127.0.0.1" in unit
    assert "--port 8978" in unit
    assert "Restart=on-failure" in unit
    assert "[Install]" in unit
    assert "WantedBy=default.target" in unit


def test_create_codeindexer_unit_custom_port() -> None:
    """Custom port must appear in the generated unit."""
    mod = _load_module()
    unit = mod.create_codeindexer_unit(
        repo_root="/tmp/test",
        port=9999,
        codeindexer_bin="/home/user/.local/bin/codeindexer",
    )

    assert "--port 9999" in unit


def test_create_codegraph_unit_defaults() -> None:
    """codegraph unit must keep MCP stdio alive so the watcher stays active."""
    mod = _load_module()
    unit = mod.create_codegraph_unit(
        repo_root="/home/user/projects/rag-fresh",
        npx_bin="/home/user/.nvm/versions/node/v24.14.0/bin/npx",
    )

    assert "[Unit]" in unit
    assert "Description=CodeGraph RAG-Fresh Server" in unit
    assert "[Service]" in unit
    assert "Type=simple" in unit
    assert "ExecStart=" in unit
    assert "tail -f /dev/null |" in unit
    assert "/home/user/.nvm/versions/node/v24.14.0/bin/npx" in unit
    assert "-y" in unit
    assert "@colbymchenry/codegraph serve" in unit
    assert "--mcp" in unit
    assert "--path" in unit
    assert "/home/user/projects/rag-fresh" in unit
    assert "--no-watch" not in unit
    assert "CODEGRAPH_NO_DAEMON" not in unit
    assert "Restart=on-failure" in unit
    assert "[Install]" in unit
    assert "WantedBy=default.target" in unit


def test_create_codegraph_unit_quotes_repo_root() -> None:
    """Repo paths embedded in the shell command must be quoted safely."""
    mod = _load_module()
    unit = mod.create_codegraph_unit(
        repo_root="/home/user/projects/rag fresh",
        npx_bin="/usr/bin/npx",
    )

    exec_line = next(line for line in unit.splitlines() if line.startswith("ExecStart="))
    exec_args = shlex.split(exec_line.removeprefix("ExecStart="))

    assert exec_args[:3] == ["/usr/bin/env", "bash", "-lc"]
    assert "--path '/home/user/projects/rag fresh'" in exec_args[3]


def test_create_codegraph_unit_custom_repo_root() -> None:
    """Custom repo root path must appear in the generated unit."""
    mod = _load_module()
    unit = mod.create_codegraph_unit(
        repo_root="/opt/my-project",
        npx_bin="/usr/bin/npx",
    )

    assert "--path /opt/my-project" in unit


def test_units_are_idempotent() -> None:
    """Generating the same unit twice must produce identical output."""
    mod = _load_module()
    u1 = mod.create_codeindexer_unit(
        repo_root="/home/user/projects/rag-fresh",
        codeindexer_bin="/home/user/.local/bin/codeindexer",
    )
    u2 = mod.create_codeindexer_unit(
        repo_root="/home/user/projects/rag-fresh",
        codeindexer_bin="/home/user/.local/bin/codeindexer",
    )
    assert u1 == u2

    g1 = mod.create_codegraph_unit(
        repo_root="/home/user/projects/rag-fresh",
        npx_bin="/home/user/.nvm/versions/node/v24.14.0/bin/npx",
    )
    g2 = mod.create_codegraph_unit(
        repo_root="/home/user/projects/rag-fresh",
        npx_bin="/home/user/.nvm/versions/node/v24.14.0/bin/npx",
    )
    assert g1 == g2


# ---------------------------------------------------------------------------
# check_systemd_available tests
# ---------------------------------------------------------------------------


def test_check_systemd_available_returns_bool() -> None:
    """check_systemd_available must return a boolean."""
    mod = _load_module()
    result = mod.check_systemd_available()
    assert isinstance(result, bool)


def test_check_systemd_available_detects_absence(monkeypatch: pytest.MonkeyPatch) -> None:
    """When systemctl is missing from PATH, check must return False cleanly."""
    mod = _load_module()
    monkeypatch.setattr(mod.shutil, "which", lambda _name: None)
    assert mod.check_systemd_available() is False


def test_check_systemd_available_detects_offline_user_systemd(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When user systemd is offline, check must return False even if systemctl exists."""
    mod = _load_module()
    monkeypatch.setattr(mod.shutil, "which", lambda _name: "/usr/bin/systemctl")

    def fake_run(*args, **kwargs):
        return subprocess.CompletedProcess(
            args=args[0],
            returncode=1,
            stdout="offline\n",
            stderr="",
        )

    monkeypatch.setattr(mod.subprocess, "run", fake_run)
    assert mod.check_systemd_available() is False


def test_check_systemd_available_accepts_running_or_degraded(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Running and degraded user systemd states are usable for user services."""
    mod = _load_module()
    monkeypatch.setattr(mod.shutil, "which", lambda _name: "/usr/bin/systemctl")

    def fake_run(*args, **kwargs):
        return subprocess.CompletedProcess(
            args=args[0],
            returncode=0,
            stdout="degraded\n",
            stderr="",
        )

    monkeypatch.setattr(mod.subprocess, "run", fake_run)
    assert mod.check_systemd_available() is True


# ---------------------------------------------------------------------------
# write_unit_file tests
# ---------------------------------------------------------------------------


def test_write_unit_file_creates_file(tmp_path: Path) -> None:
    """write_unit_file must create the unit file at the expected path."""
    mod = _load_module()
    unit_dir = tmp_path / "systemd" / "user"
    unit_dir.mkdir(parents=True)

    content = "[Unit]\nDescription=Test\n"
    written = mod.write_unit_file("test.service", content, str(unit_dir))

    assert written.exists()
    assert written.read_text() == content


def test_write_unit_file_overwrites_idempotently(tmp_path: Path) -> None:
    """Writing the same unit twice must be safe — overwrite, no error."""
    mod = _load_module()
    unit_dir = tmp_path / "systemd" / "user"
    unit_dir.mkdir(parents=True)

    content = "[Unit]\nDescription=Test\n"
    mod.write_unit_file("test.service", content, str(unit_dir))
    # Second write should succeed without error
    written = mod.write_unit_file("test.service", content, str(unit_dir))
    assert written.exists()
    assert written.read_text() == content


def test_write_unit_file_nonexistent_dir_creates_it(tmp_path: Path) -> None:
    """write_unit_file must create parent dirs if they don't exist."""
    mod = _load_module()
    unit_dir = tmp_path / "new" / "systemd" / "user"

    content = "[Unit]\nDescription=Test\n"
    written = mod.write_unit_file("test.service", content, str(unit_dir))
    assert written.exists()
    assert written.parent == unit_dir


# ---------------------------------------------------------------------------
# CLI integration tests (subprocess)
# ---------------------------------------------------------------------------


def _run_cli(*args: str, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    """Run the CLI script with controlled arguments."""
    merged_env = os.environ.copy()
    if env:
        merged_env.update(env)
    return subprocess.run(  # nosec B603
        [sys.executable, str(SCRIPT_PATH), *args],
        capture_output=True,
        text=True,
        env=merged_env,
        timeout=10,
    )


def test_dry_run_prints_unit_contents() -> None:
    """--dry-run must print unit file contents to stdout without writing files."""
    cp = _run_cli("--dry-run", "--repo-root", "/home/user/projects/rag-fresh")

    assert cp.returncode == 0
    combined = cp.stdout + cp.stderr
    assert "codeindexer" in combined.lower()
    assert "codegraph" in combined.lower()
    assert "ExecStart=" in combined
    assert "codeindexer serve" in combined
    assert "npx" in combined


def test_dry_run_does_not_write_files(tmp_path: Path) -> None:
    """--dry-run with custom --user-systemd-dir must not create any files."""
    unit_dir = tmp_path / "systemd" / "user"
    unit_dir.mkdir(parents=True)

    cp = _run_cli(
        "--dry-run",
        "--repo-root",
        "/home/user/projects/rag-fresh",
        "--user-systemd-dir",
        str(unit_dir),
    )

    assert cp.returncode == 0
    # No .service files should be created in the target dir
    service_files = list(unit_dir.glob("*.service"))
    assert len(service_files) == 0, f"dry-run must not write files; found {service_files}"


def test_check_reports_systemd_unavailable(tmp_path: Path) -> None:
    """--check must report systemd unavailability clearly, exit non-zero."""
    # Strip systemctl from PATH
    bad_path = tmp_path
    env = {**os.environ, "PATH": str(bad_path)}

    cp = _run_cli(
        "--check",
        "--repo-root",
        "/home/user/projects/rag-fresh",
        "--user-systemd-dir",
        str(tmp_path / "systemd" / "user"),
        env=env,
    )

    combined = cp.stdout + cp.stderr
    assert (
        "systemctl" in combined.lower()
        or "systemd" in combined.lower()
        or "not available" in combined.lower()
        or "unavailable" in combined.lower()
    ), f"--check must report systemd unavailability; got:\n{combined}"


def test_check_is_nondestructive(tmp_path: Path) -> None:
    """--check must not create files or mutate state."""
    unit_dir = tmp_path / "systemd" / "user"
    unit_dir.mkdir(parents=True)

    _run_cli(
        "--check",
        "--repo-root",
        "/home/user/projects/rag-fresh",
        "--user-systemd-dir",
        str(unit_dir),
    )

    # Check should never write files regardless of systemd status
    service_files = list(unit_dir.glob("*.service"))
    assert len(service_files) == 0, f"--check must not write files; found {service_files}"


def test_install_writes_unit_files(tmp_path: Path) -> None:
    """--install must write both .service files to the user systemd dir."""
    unit_dir = tmp_path / "systemd" / "user"
    unit_dir.mkdir(parents=True)

    cp = _run_cli(
        "--install",
        "--repo-root",
        "/home/user/projects/rag-fresh",
        "--user-systemd-dir",
        str(unit_dir),
    )

    assert cp.returncode == 0, f"install failed: {cp.stderr}"
    codeindexer_file = unit_dir / "codeindexer.service"
    codegraph_file = unit_dir / "codegraph-rag-fresh.service"
    assert codeindexer_file.exists(), f"expected {codeindexer_file} to exist"
    assert codegraph_file.exists(), f"expected {codegraph_file} to exist"


def test_install_with_custom_config_root(tmp_path: Path) -> None:
    """--install with custom --config-root still writes files."""
    unit_dir = tmp_path / "systemd" / "user"
    unit_dir.mkdir(parents=True)

    cp = _run_cli(
        "--install",
        "--repo-root",
        "/home/user/projects/rag-fresh",
        "--user-systemd-dir",
        str(unit_dir),
        "--config-root",
        str(tmp_path / "config"),
    )

    assert cp.returncode == 0
    assert (unit_dir / "codeindexer.service").exists()
    assert (unit_dir / "codegraph-rag-fresh.service").exists()


def test_install_is_idempotent(tmp_path: Path) -> None:
    """Running --install twice must succeed without errors."""
    unit_dir = tmp_path / "systemd" / "user"
    unit_dir.mkdir(parents=True)

    # First install
    cp1 = _run_cli(
        "--install",
        "--repo-root",
        "/home/user/projects/rag-fresh",
        "--user-systemd-dir",
        str(unit_dir),
    )
    assert cp1.returncode == 0

    # Second install
    cp2 = _run_cli(
        "--install",
        "--repo-root",
        "/home/user/projects/rag-fresh",
        "--user-systemd-dir",
        str(unit_dir),
    )
    assert cp2.returncode == 0
    # Files should still exist
    assert (unit_dir / "codeindexer.service").exists()
    assert (unit_dir / "codegraph-rag-fresh.service").exists()


def test_wsl_agent_watchers_cli_help() -> None:
    """--help must describe available options."""
    cp = _run_cli("--help")
    assert cp.returncode == 0
    combined = cp.stdout + cp.stderr
    assert "dry-run" in combined
    assert "check" in combined
    assert "install" in combined


def test_cli_missing_repo_root_fails() -> None:
    """Missing --repo-root must produce non-zero exit code."""
    cp = _run_cli("--dry-run")
    assert cp.returncode != 0


def test_cli_invalid_mode_fails() -> None:
    """No mode (--dry-run, --check, --install) must produce non-zero exit."""
    cp = _run_cli("--repo-root", "/tmp")
    assert cp.returncode != 0


def test_installed_unit_has_correct_exec_content(tmp_path: Path) -> None:
    """Verify that the installed unit file has the correct ExecStart."""
    unit_dir = tmp_path / "systemd" / "user"
    unit_dir.mkdir(parents=True)

    _run_cli(
        "--install",
        "--repo-root",
        "/home/user/projects/rag-fresh",
        "--user-systemd-dir",
        str(unit_dir),
        "--codeindexer-bin",
        "/home/user/.local/bin/codeindexer",
        "--npx-bin",
        "/home/user/.nvm/versions/node/v24.14.0/bin/npx",
    )

    idx_content = (unit_dir / "codeindexer.service").read_text()
    assert (
        "ExecStart=/home/user/.local/bin/codeindexer serve --host 127.0.0.1 --port 8978"
        in idx_content
    )

    cg_content = (unit_dir / "codegraph-rag-fresh.service").read_text()
    assert "Type=simple" in cg_content
    assert "tail -f /dev/null |" in cg_content
    assert "--no-watch" not in cg_content
    assert "CODEGRAPH_NO_DAEMON" not in cg_content
    assert (
        "/home/user/.nvm/versions/node/v24.14.0/bin/npx -y "
        "@colbymchenry/codegraph serve --mcp --path /home/user/projects/rag-fresh" in cg_content
    )

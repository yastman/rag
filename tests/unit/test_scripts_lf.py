"""Tests for scripts/lf — Langfuse CLI quick-audit recipes.

Issue #2179: ``scripts/lf health`` must source ``.env`` before requiring
``LANGFUSE_HOST``, otherwise it fails when the variable is only in ``.env``
and not already in the shell environment.
"""

from __future__ import annotations

import os
import subprocess
import tempfile
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
LF_SCRIPT = REPO_ROOT / "scripts" / "lf"


def _run_lf_health(
    *,
    env_file: Path,
    extra_env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    """Run ``scripts/lf health`` with a controlled env file."""
    env = os.environ.copy()
    # Purge LANGFUSE_HOST so the test must rely on the env file
    env.pop("LANGFUSE_HOST", None)
    # And the other Langfuse vars to remove any ambient env
    env.pop("LANGFUSE_PUBLIC_KEY", None)
    env.pop("LANGFUSE_SECRET_KEY", None)
    env["LF_ENV_FILE"] = str(env_file)
    if extra_env:
        env.update(extra_env)
    return subprocess.run(
        ["bash", str(LF_SCRIPT), "health"],
        capture_output=True,
        text=True,
        env=env,
        timeout=15,
    )


class TestLfHealthEnvLoading:
    """scripts/lf health must source .env before checking LANGFUSE_HOST."""

    def test_health_works_when_langfuse_host_only_in_env_file(self):
        """If LANGFUSE_HOST is only in .env (not exported), health must not fail."""
        with tempfile.TemporaryDirectory() as tmpdir:
            env_path = Path(tmpdir) / ".env"
            env_path.write_text(
                "LANGFUSE_HOST=http://localhost:9999\n"
                "LANGFUSE_PUBLIC_KEY=pk-test\n"
                "LANGFUSE_SECRET_KEY=sk-test\n"
            )

            result = _run_lf_health(env_file=env_path)

            # The curl will likely fail (localhost:9999 not running), but
            # it should NOT fail with a shell-level "LANGFUSE_HOST: parameter
            # null or not set" error — that's the bug we're fixing.
            # A shell parameter-expansion failure returns exit code 1 with stderr.
            assert ": parameter null or not set" not in result.stderr, (
                "scripts/lf health failed to source .env before checking LANGFUSE_HOST;\n"
                f"stderr={result.stderr!r}"
            )
            # curl failure is expected (no real service), but not shell syntax error
            assert "LANGFUSE_HOST" not in result.stderr.split(": parameter")[0] if ": parameter" in result.stderr else True

    def test_health_sources_env_file_before_host_check(self):
        """The env file must be sourced before the host variable is expanded."""
        # Read the script to verify source order — structural check
        content = LF_SCRIPT.read_text()
        # Find the line order in the health case block
        lines = content.split("\n")
        host_check_line = -1
        source_line = -1
        for i, line in enumerate(lines):
            if "LANGFUSE_HOST" in line and ":?" in line:
                host_check_line = i
            if "source" in line and "ENV_FILE" in line:
                source_line = i

        assert source_line >= 0, "scripts/lf must have a 'source $ENV_FILE' line"
        assert host_check_line >= 0, "scripts/lf must check LANGFUSE_HOST"
        assert source_line < host_check_line, (
            f"scripts/lf must source .env (line {source_line}) "
            f"before checking LANGFUSE_HOST (line {host_check_line}); "
            f"current order is wrong — source is AFTER the variable check"
        )

# tests/unit/scripts/test_swarm_opencode_run_unattended.py
"""Unit tests for ``scripts/swarm_opencode_run_unattended.sh``.

Issue #1306 reports that swarm OpenCode workers stop and require manual
permission confirmation, which defeats the unattended-worker contract.
The repo investigation (see PR description on #1306) and Context7
documentation for ``/anomalyco/opencode`` show that the env variable used
by the existing launcher (``OPENCODE_PERMISSION``) is not recognised by
OpenCode. The canonical mechanism is the ``permission`` field in
``opencode.json``, which can be injected at runtime in three ways:

1. A project-local ``opencode.json`` (highest precedence).
2. ``OPENCODE_CONFIG=/path/to/file.json`` — load an explicit config file.
3. ``OPENCODE_CONFIG_CONTENT='{"permission":"allow"}'`` — inline JSON.

This module pins the contract for a small wrapper,
``scripts/swarm_opencode_run_unattended.sh``, that user-level launchers
(under ``~/.codex/skills/tmux-swarm-orchestration/scripts/``) can invoke
in place of bare ``opencode`` to get the correct non-interactive policy
without each launcher reinventing it.

Wrapper behaviour:

- If neither ``OPENCODE_CONFIG`` nor ``OPENCODE_CONFIG_CONTENT`` is set in
  the caller's environment, the wrapper sets
  ``OPENCODE_CONFIG_CONTENT='{"$schema": "...", "permission": "allow"}'``
  before exec'ing ``opencode``. This grants tool/edit/bash permissions
  without prompts.
- If ``OPENCODE_CONFIG_CONTENT`` is already set, leave it alone (caller
  has stronger opinions; do not override).
- If ``OPENCODE_CONFIG`` is set, leave it alone for the same reason.
- Pass through every positional argument verbatim, so callers can use
  the wrapper for ``opencode run ...``, ``opencode tui``, or any future
  OpenCode subcommand.

Refs #1306. Context7 sources:
``/anomalyco/opencode/dev/packages/web/src/content/docs/permissions.mdx``
``/anomalyco/opencode/dev/packages/web/src/content/docs/config.mdx``
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import textwrap
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[3]
SCRIPT_PATH = REPO_ROOT / "scripts" / "swarm_opencode_run_unattended.sh"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _write_opencode_stub(bin_dir: Path) -> Path:
    """Write a fake ``opencode`` executable that records env + args.

    The stub writes three lines to ``$OPENCODE_TEST_OUTFILE``:

        OPENCODE_CONFIG_CONTENT=<value or <unset>>
        OPENCODE_CONFIG=<value or <unset>>
        ARGS: <space-joined argv>

    and exits 0. Callers compare the captured file against the contract.
    """
    bin_dir.mkdir(parents=True, exist_ok=True)
    stub = bin_dir / "opencode"
    stub.write_text(
        textwrap.dedent(
            """\
            #!/usr/bin/env bash
            : "${OPENCODE_TEST_OUTFILE:?OPENCODE_TEST_OUTFILE must be set in tests}"
            {
              echo "OPENCODE_CONFIG_CONTENT=${OPENCODE_CONFIG_CONTENT-<unset>}"
              echo "OPENCODE_CONFIG=${OPENCODE_CONFIG-<unset>}"
              printf 'ARGS:'
              for a in "$@"; do printf ' %s' "$a"; done
              echo
            } > "$OPENCODE_TEST_OUTFILE"
            exit 0
            """
        )
    )
    stub.chmod(0o755)
    return stub


def _run_wrapper(
    *args: str,
    env_override: dict[str, str | None] | None = None,
    bin_dir: Path,
    outfile: Path,
) -> subprocess.CompletedProcess[str]:
    """Run the wrapper with a stubbed ``opencode`` on PATH and capture env+args."""
    env = os.environ.copy()
    env["PATH"] = f"{bin_dir}:{env['PATH']}"
    env["OPENCODE_TEST_OUTFILE"] = str(outfile)
    # Start from a clean slate for the variables we care about.
    env.pop("OPENCODE_CONFIG_CONTENT", None)
    env.pop("OPENCODE_CONFIG", None)
    if env_override:
        for key, value in env_override.items():
            if value is None:
                env.pop(key, None)
            else:
                env[key] = value
    return subprocess.run(
        ["bash", str(SCRIPT_PATH), *args],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


def _parse_outfile(outfile: Path) -> dict[str, str]:
    """Return the captured env/args from the stub's output."""
    parsed: dict[str, str] = {}
    for line in outfile.read_text(encoding="utf-8").splitlines():
        if line.startswith("OPENCODE_CONFIG_CONTENT="):
            parsed["OPENCODE_CONFIG_CONTENT"] = line.removeprefix("OPENCODE_CONFIG_CONTENT=")
        elif line.startswith("OPENCODE_CONFIG="):
            parsed["OPENCODE_CONFIG"] = line.removeprefix("OPENCODE_CONFIG=")
        elif line.startswith("ARGS:"):
            parsed["ARGS"] = line.removeprefix("ARGS:").strip()
    return parsed


# ---------------------------------------------------------------------------
# Static structural sanity
# ---------------------------------------------------------------------------


class TestScriptShape:
    def test_script_exists_and_is_executable(self) -> None:
        assert SCRIPT_PATH.is_file(), SCRIPT_PATH
        assert os.access(SCRIPT_PATH, os.X_OK), (
            f"{SCRIPT_PATH} must be executable so launchers can invoke it directly."
        )

    def test_script_starts_with_bash_shebang(self) -> None:
        first = SCRIPT_PATH.read_text(encoding="utf-8").splitlines()[0]
        assert first in (
            "#!/usr/bin/env bash",
            "#!/bin/bash",
        ), f"Unexpected shebang: {first!r}"


# ---------------------------------------------------------------------------
# Behavioural contract
# ---------------------------------------------------------------------------


class TestUnattendedWrapper:
    def test_injects_permission_allow_when_no_config_set(self, tmp_path) -> None:
        bin_dir = tmp_path / "bin"
        outfile = tmp_path / "out"
        _write_opencode_stub(bin_dir)

        result = _run_wrapper("run", "explain", "context", bin_dir=bin_dir, outfile=outfile)

        assert result.returncode == 0, (result.stdout, result.stderr)
        captured = _parse_outfile(outfile)
        assert captured["OPENCODE_CONFIG"] == "<unset>", captured
        # The injected JSON must be valid and assert a permissive policy.
        injected = captured["OPENCODE_CONFIG_CONTENT"]
        assert injected != "<unset>", captured
        parsed = json.loads(injected)
        assert parsed.get("permission") == "allow", parsed

    def test_passes_through_positional_args_verbatim(self, tmp_path) -> None:
        bin_dir = tmp_path / "bin"
        outfile = tmp_path / "out"
        _write_opencode_stub(bin_dir)

        _run_wrapper(
            "run",
            "Explain the use of context in Go",
            "--quiet",
            bin_dir=bin_dir,
            outfile=outfile,
        )

        captured = _parse_outfile(outfile)
        assert captured["ARGS"] == ("run Explain the use of context in Go --quiet"), captured

    def test_does_not_override_existing_opencode_config_content(self, tmp_path) -> None:
        bin_dir = tmp_path / "bin"
        outfile = tmp_path / "out"
        _write_opencode_stub(bin_dir)

        caller_payload = '{"permission": {"bash": "ask"}, "model": "anthropic/x"}'
        _run_wrapper(
            "run",
            "noop",
            env_override={"OPENCODE_CONFIG_CONTENT": caller_payload},
            bin_dir=bin_dir,
            outfile=outfile,
        )

        captured = _parse_outfile(outfile)
        assert captured["OPENCODE_CONFIG_CONTENT"] == caller_payload, captured

    def test_does_not_override_existing_opencode_config_path(self, tmp_path) -> None:
        bin_dir = tmp_path / "bin"
        outfile = tmp_path / "out"
        _write_opencode_stub(bin_dir)

        custom_path = "/etc/opencode/custom.json"
        _run_wrapper(
            "run",
            "noop",
            env_override={"OPENCODE_CONFIG": custom_path},
            bin_dir=bin_dir,
            outfile=outfile,
        )

        captured = _parse_outfile(outfile)
        assert captured["OPENCODE_CONFIG"] == custom_path, captured
        # The wrapper must not silently inject CONTENT alongside an existing
        # CONFIG path: that would be ambiguous to debug.
        assert captured["OPENCODE_CONFIG_CONTENT"] == "<unset>", captured

    def test_propagates_opencode_exit_code(self, tmp_path) -> None:
        # Stub that exits non-zero.
        bin_dir = tmp_path / "bin"
        outfile = tmp_path / "out"
        bin_dir.mkdir(parents=True)
        stub = bin_dir / "opencode"
        stub.write_text(
            textwrap.dedent(
                """\
                #!/usr/bin/env bash
                : "${OPENCODE_TEST_OUTFILE:?OPENCODE_TEST_OUTFILE must be set in tests}"
                echo "stubbed failure" >&2
                exit 7
                """
            )
        )
        stub.chmod(0o755)

        result = _run_wrapper("run", "fail", bin_dir=bin_dir, outfile=outfile)

        assert result.returncode == 7, (result.stdout, result.stderr)

    def test_errors_when_opencode_not_on_path(self, tmp_path) -> None:
        # No stub written, so 'opencode' is not provided by us.
        bin_dir = tmp_path / "bin"
        bin_dir.mkdir(parents=True)
        outfile = tmp_path / "out"

        # If a real opencode is already on the host PATH, this scenario is
        # impossible to construct without losing access to bash itself.
        if shutil.which("opencode"):
            pytest.skip(
                "A real opencode binary is on PATH; cannot test the "
                "missing-binary path without trimming PATH past bash too."
            )

        env = os.environ.copy()
        # Prepend our empty bin_dir so it doesn't override anything; opencode
        # remains absent system-wide.
        env["PATH"] = f"{bin_dir}:{env.get('PATH', '')}"
        env["OPENCODE_TEST_OUTFILE"] = str(outfile)
        env.pop("OPENCODE_CONFIG_CONTENT", None)
        env.pop("OPENCODE_CONFIG", None)

        result = subprocess.run(
            ["bash", str(SCRIPT_PATH), "run", "noop"],
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )

        # Wrapper must fail loudly, not silently succeed.
        assert result.returncode != 0
        # Helpful diagnostic mentions opencode somewhere.
        combined = (result.stderr or "") + (result.stdout or "")
        assert "opencode" in combined.lower(), combined


# ---------------------------------------------------------------------------
# Independence check: the test file should not assume bash exists at a
# specific path, but it does need bash to be installed.
# ---------------------------------------------------------------------------


def test_bash_is_available() -> None:
    assert shutil.which("bash") is not None, "bash must be on PATH to run the wrapper script tests."

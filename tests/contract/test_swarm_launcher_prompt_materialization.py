"""Contract test for bug L (swarm launcher prompt materialization).

`launch_kiro_worker.sh` materializes the worker prompt with:

    sed "s|{{ORCH_TARGET}}|...|g" "$PROMPT_SRC" > "$PROMPT_FILE"

where ``PROMPT_FILE=logs/prompts/<WORKER_NAME>.md``. The natural caller
workflow (write the prompt to ``logs/prompts/<name>.md`` and launch with
``WORKER_NAME=<name>``) makes ``PROMPT_SRC == PROMPT_FILE``. The shell opens the
``> "$PROMPT_FILE"`` redirection (truncating it to 0 bytes) BEFORE ``sed`` reads
it, so the worker gets an empty prompt.

This test runs the REAL launcher with a ``tmux`` PATH-shim (so nothing is
actually spawned) and asserts the prompt survives the same-path case.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
LAUNCHER = REPO_ROOT / "scripts" / "launch_kiro_worker.sh"


def _write_tmux_shim(bin_dir: Path) -> None:
    """A no-op tmux that satisfies the launcher's preflight without side effects."""
    shim = bin_dir / "tmux"
    shim.write_text(
        "#!/usr/bin/env bash\n"
        'case "$1" in\n'
        "  has-session) exit 0 ;;\n"
        "  display-message) echo faketmux ;;\n"
        "  *) exit 0 ;;\n"
        "esac\n",
        encoding="utf-8",
    )
    shim.chmod(0o755)


def test_launcher_preserves_prompt_when_src_equals_dest(tmp_path: Path) -> None:
    worker = "ttest-same-path"
    prompt_dir = REPO_ROOT / "logs" / "prompts"
    prompt_dir.mkdir(parents=True, exist_ok=True)
    dest = prompt_dir / f"{worker}.md"
    body = "x" * 200
    dest.write_text(f"WORKER_NAME={worker}\nwake {{{{ORCH_TARGET}}}}\n{body}\n", encoding="utf-8")

    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    _write_tmux_shim(bin_dir)

    env = dict(os.environ)
    env["PATH"] = f"{bin_dir}:{env['PATH']}"
    env["ORCH_TARGET"] = "faketmux:orch-test"
    env.pop("KIRO_REQUIRED_SKILLS", None)
    env.pop("WORKER_AGENT", None)
    env.pop("WORKER_MODEL", None)

    try:
        result = subprocess.run(
            ["bash", str(LAUNCHER), worker, str(dest)],
            capture_output=True,
            text=True,
            env=env,
            cwd=str(REPO_ROOT),
            timeout=30,
        )
        assert dest.stat().st_size > 0, (
            "prompt truncated to 0 bytes (bug L: redirect truncates source); "
            f"rc={result.returncode} stderr={result.stderr!r}"
        )
        materialized = dest.read_text(encoding="utf-8")
        assert "faketmux:orch-test" in materialized, "ORCH_TARGET placeholder not substituted"
        assert body in materialized, "prompt body lost during materialization"
    finally:
        dest.unlink(missing_ok=True)
        (REPO_ROOT / "logs" / f"{worker}.wrapper.sh").unlink(missing_ok=True)


def _launcher_text() -> str:
    return LAUNCHER.read_text(encoding="utf-8")


def test_launcher_has_timeout_failsafe() -> None:
    """#3 reliability: a timeout watchdog must wake the orchestrator with [FAILED]
    when the worker emits no terminal signal (kiro-cli TUI does not exit)."""
    text = _launcher_text()
    assert "WORKER_TIMEOUT" in text, "launcher must define a WORKER_TIMEOUT failsafe budget"
    assert "send_signal" in text, "launcher must funnel wake-ups through send_signal"
    assert "_watchdog" in text, "launcher must spawn a background watchdog"
    assert "[FAILED]" in text, "watchdog must emit a [FAILED] failsafe"


def test_launcher_single_fire_wakeup_no_double() -> None:
    """The wake-up must be single-fire (noclobber flag) so the agent's own wake-up
    and the failsafe can never double-send."""
    text = _launcher_text()
    assert "noclobber" in text, "single-fire wake-up must use a noclobber flag file"
    assert "SIGNAL_FLAG" in text
    # The legacy always-send STATUS_LINE block must be gone.
    assert "STATUS_LINE=" not in text, "legacy unconditional re-send must be removed"


def test_launcher_supports_worker_worktree_isolation() -> None:
    """E: the launcher must run the worker in an assigned worktree when given."""
    text = _launcher_text()
    assert "WORKER_WORKTREE" in text, "launcher must accept WORKER_WORKTREE"
    assert "WORKER_CWD" in text
    assert 'cd "$WORKER_CWD"' in text, "wrapper must cd into the assigned worktree"
    assert '-c "$WORKER_CWD"' in text, "tmux window must open in the assigned worktree"

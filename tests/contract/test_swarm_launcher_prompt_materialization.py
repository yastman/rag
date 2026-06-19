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


# --- #2820: wake-up reliability regressions ---------------------------------

SET_ORCH = REPO_ROOT / "scripts" / "set_orchestrator_window.sh"


def test_launcher_normalizes_worker_cwd_to_absolute() -> None:
    """Bug 1 (#2820): the wrapper's `cd` failed for a relative WORKER_WORKTREE.
    The launcher must normalize WORKER_CWD to an absolute path before writing it
    into the wrapper."""
    text = _launcher_text()
    assert 'WORKER_CWD="$(cd "$WORKER_CWD" && pwd)"' in text, (
        "launcher must canonicalize WORKER_CWD to an absolute path so the "
        "wrapper's cd works regardless of the caller's CWD"
    )


def test_launcher_wakeup_not_keyed_on_log_grep() -> None:
    """Bug 3 (#2820): the old wrapper reconciled by grepping the worker LOG for
    '[DONE]'. A printed-but-not-executed wake-up line landed in the log and
    tripped a false positive, suppressing the failsafe. The wake-up must key on
    a status/report FILE, never on log content."""
    text = _launcher_text()
    assert "grep -qE '\\[(DONE|FAILED|BLOCKED)\\]' \"$WORKER_LOG\"" not in text, (
        "wrapper must not grep the worker LOG to decide the terminal signal "
        "(printed text forges a false positive)"
    )
    assert "STATUS_FILE" in text, "wrapper must read a status file for the terminal status"
    assert "resolve_status" in text, "wrapper must resolve status from file, not log"
    assert "REPORT_FILE_ABS" in text, "wrapper must check report-file existence as fallback"


def test_launcher_substitutes_report_and_status_placeholders() -> None:
    """The launcher must substitute {{REPORT_FILE}} and {{STATUS_FILE}} into the
    prompt so the agent writes to the canonical absolute paths the wrapper reads."""
    text = _launcher_text()
    assert "{{REPORT_FILE}}" in text, "launcher must substitute the report-file placeholder"
    assert "{{STATUS_FILE}}" in text, "launcher must substitute the status-file placeholder"


def test_launcher_canonical_report_path() -> None:
    """Report path must follow the done-signal protocol convention."""
    text = _launcher_text()
    assert 'REPORT_FILE="logs/REPORT.${WORKER_NAME}.md"' in text


def test_set_orchestrator_window_anchors_on_tmux_pane() -> None:
    """Bug 2 (#2820): the script resolved the window via the session's *active*
    window, not the calling process's pane. It must anchor on $TMUX_PANE."""
    text = SET_ORCH.read_text(encoding="utf-8")
    assert "TMUX_PANE" in text, "set_orchestrator_window.sh must anchor on $TMUX_PANE"
    assert 'tmux display-message -p -t "$TMUX_PANE"' in text, (
        "window-id/name must be resolved from the calling process's pane"
    )


def test_launcher_generates_absolute_cd_in_wrapper(tmp_path: Path) -> None:
    """Functional: a RELATIVE WORKER_WORKTREE must yield an ABSOLUTE cd in the
    generated wrapper (Bug 1 end-to-end)."""
    worker = "ttest-abs-cwd"
    # A real relative subdir under the repo root to act as the worktree.
    rel_wt = f"logs/.ttest-wt-{worker}"
    abs_wt = REPO_ROOT / rel_wt
    abs_wt.mkdir(parents=True, exist_ok=True)

    prompt_dir = REPO_ROOT / "logs" / "prompts"
    prompt_dir.mkdir(parents=True, exist_ok=True)
    dest = prompt_dir / f"{worker}.md"
    dest.write_text("body\n", encoding="utf-8")

    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    _write_tmux_shim(bin_dir)

    env = dict(os.environ)
    env["PATH"] = f"{bin_dir}:{env['PATH']}"
    env["ORCH_TARGET"] = "faketmux:orch-test"
    env["WORKER_WORKTREE"] = rel_wt  # relative on purpose
    env.pop("KIRO_REQUIRED_SKILLS", None)
    env.pop("WORKER_AGENT", None)
    env.pop("WORKER_MODEL", None)

    wrapper = REPO_ROOT / "logs" / f"{worker}.wrapper.sh"
    try:
        subprocess.run(
            ["bash", str(LAUNCHER), worker, str(dest)],
            capture_output=True,
            text=True,
            env=env,
            cwd=str(REPO_ROOT),
            timeout=30,
        )
        wtext = wrapper.read_text(encoding="utf-8")
        assert f'cd "{abs_wt}"' in wtext, (
            f"wrapper cd must be absolute; got wrapper:\n{wtext[:400]}"
        )
        assert f'cd "{rel_wt}"' not in wtext, "wrapper must not cd into a relative path"
    finally:
        dest.unlink(missing_ok=True)
        wrapper.unlink(missing_ok=True)
        import shutil

        shutil.rmtree(abs_wt, ignore_errors=True)

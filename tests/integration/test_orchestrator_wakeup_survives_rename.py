"""Regression test: orchestrator wake-up must survive a window rename.

Root cause being pinned: ``set_orchestrator_window.sh`` historically routed
wake-ups by the tmux *window name* (``session:window_name``). tmux window names
are mutable — ``automatic-rename`` (on by default), an ``allow-rename`` escape
sequence from the shell, or a per-task re-rename can change them. Once the name
drifts, the worker's ``tmux send-keys -t "$ORCH_TARGET"`` fails with
``can't find window`` and the orchestrator never receives ``[DONE]`` (the
"secretary notified itself / orchestrator idle" symptom).

The fix routes wake-ups by the immutable tmux window-id (``@N``) and names the
orchestrator window exactly once per session (idempotent on subsequent tasks).

These tests drive a REAL tmux server (skipped when tmux is unavailable). The
script is copied into an isolated ``REPO_ROOT`` so the marker lands under
``tmp_path/.signals`` and never touches the real repo state.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import time
import uuid
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
SET_ORCH = REPO_ROOT / "scripts" / "set_orchestrator_window.sh"

pytestmark = pytest.mark.skipif(shutil.which("tmux") is None, reason="tmux not available on PATH")


def _tmux(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["tmux", *args], capture_output=True, text=True)


def _send(target: str, *keys: str) -> None:
    _tmux("send-keys", "-t", target, *keys)


def _wait(predicate, timeout: float = 10.0, interval: float = 0.2) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            if predicate():
                return True
        except Exception:
            pass
        time.sleep(interval)
    return False


def _isolated_script(tmp_path: Path) -> tuple[Path, Path]:
    """Copy set_orchestrator_window.sh into an isolated REPO_ROOT under tmp_path.

    The tracked script derives REPO_ROOT as ``dirname/..`` so the marker lands at
    ``<scripts_parent>/.signals/orchestrator-window.json``.
    """
    scripts_dir = tmp_path / "scripts"
    scripts_dir.mkdir()
    script = scripts_dir / "set_orchestrator_window.sh"
    script.write_bytes(SET_ORCH.read_bytes())
    script.chmod(0o755)
    marker = tmp_path / ".signals" / "orchestrator-window.json"
    return script, marker


def _new_session() -> tuple[str, str]:
    """Create a detached session and return (session_name, window_id).

    Targets the window by its immutable id rather than ``session:0`` because the
    server may run with ``base-index 1``.
    """
    session = f"orchwake_{uuid.uuid4().hex[:8]}"
    _tmux("kill-session", "-t", session)  # best-effort cleanup of a stale name
    res = _tmux(
        "new-session",
        "-d",
        "-s",
        session,
        "-n",
        "init",
        "bash",
        "--norc",
        "--noprofile",
    )
    assert res.returncode == 0, f"could not create tmux session: {res.stderr}"
    win_id = (
        _tmux("list-windows", "-t", session, "-F", "#{window_id}").stdout.strip().splitlines()[0]
    )
    assert win_id, "could not resolve the session's window id"
    return session, win_id


def test_wakeup_survives_window_rename(tmp_path: Path) -> None:
    """A wake-up sent to the marker's orchestrator_target must reach the
    orchestrator window even after that window has been renamed."""
    script, marker = _isolated_script(tmp_path)
    capture = tmp_path / "capture.txt"
    session, win = _new_session()
    try:
        # 1. Claim the orchestrator window from inside the window itself.
        _send(win, f"bash {script} mytask", "C-m")
        assert _wait(marker.exists), "set_orchestrator_window.sh did not write a marker"
        time.sleep(0.5)
        data = json.loads(marker.read_text())
        orch_target = data["orchestrator_target"]

        # 2. Simulate name drift (automatic-rename / manual re-rename for a new task).
        win_id = _tmux("display-message", "-p", "-t", win, "#{window_id}").stdout.strip()
        _tmux("rename-window", "-t", win_id, "orch-rag-audit-OLD-reverted")

        # 3. Start a capture sink in the orchestrator window.
        _send(win_id, f"cat >> {capture}", "C-m")
        time.sleep(0.5)

        # 4. Worker wake-up, exactly as launch_kiro_worker.sh's wrapper sends it.
        _send(orch_target, "-l", "[DONE] worker report.md")
        time.sleep(0.25)
        _send(orch_target, "C-m")

        # 5. The renamed orchestrator window must have received the signal.
        got = _wait(
            lambda: capture.exists() and "[DONE]" in capture.read_text(),
            timeout=8,
        )
        snap = capture.read_text() if capture.exists() else "<no capture file>"
        assert got, (
            "wake-up did not reach the orchestrator window after rename; "
            f"orch_target={orch_target!r} capture={snap!r}"
        )
    finally:
        _tmux("kill-session", "-t", session)


def test_set_once_keeps_window_name_across_tasks(tmp_path: Path) -> None:
    """The orchestrator window is named once per session; a second call for a
    different task must NOT rename it (idempotent), and the window-id is stable."""
    script, marker = _isolated_script(tmp_path)
    session, win = _new_session()
    try:
        # First claim for task A.
        _send(win, f"bash {script} task-a", "C-m")
        assert _wait(marker.exists), "marker not written on first claim"
        time.sleep(0.5)
        first = json.loads(marker.read_text())
        name_a = _tmux("display-message", "-p", "-t", win, "#{window_name}").stdout.strip()
        id_a = _tmux("display-message", "-p", "-t", win, "#{window_id}").stdout.strip()

        # Second call for a DIFFERENT task B from the same window.
        _send(win, f"bash {script} task-b", "C-m")
        # Wait until the marker's task metadata flips to task-b.
        assert _wait(
            lambda: json.loads(marker.read_text()).get("task") == "task-b",
            timeout=8,
        ), "second call did not refresh marker task metadata"
        time.sleep(0.3)
        second = json.loads(marker.read_text())
        name_b = _tmux("display-message", "-p", "-t", win, "#{window_name}").stdout.strip()
        id_b = _tmux("display-message", "-p", "-t", win, "#{window_id}").stdout.strip()

        assert name_b == name_a, (
            "orchestrator window was renamed on a new task (should be set-once): "
            f"{name_a!r} -> {name_b!r}"
        )
        assert id_b == id_a, "window-id changed unexpectedly"
        # The delivery target must stay stable and id-based across tasks.
        assert second["orchestrator_target"] == first["orchestrator_target"], (
            "orchestrator_target drifted across tasks: "
            f"{first['orchestrator_target']!r} -> {second['orchestrator_target']!r}"
        )
    finally:
        _tmux("kill-session", "-t", session)

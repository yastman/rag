"""Contract: ``scripts/launch_kiro_worker.sh`` must validate that the
``ORCH_TARGET`` *window* is live before launching — not just that the tmux
*session* exists.

Root cause it guards (gotcha ``card_f5600223ad55``): a stale orchestrator
marker left over from a prior session points ``ORCH_TARGET`` at a dead/foreign
window (e.g. ``claude:@1``). The session still exists, so the old
``tmux has-session`` check passed, and the worker wake-up ``[DONE]`` was
send-keys'd into a dead pane — the orchestrator was never woken.

The launcher must therefore:

1. keep the session-existence check (``tmux has-session``);
2. additionally confirm the target window (``@id`` or name) is currently live
   via ``tmux list-windows`` for that session;
3. fail loud (non-zero exit) on a stale window, pointing the operator at
   ``set_orchestrator_window.sh`` to re-claim the current window.

The check is a substring scan against the rendered script (same style as the
other tmux/skills contract tests) — it pins the guard, it does not execute tmux.
"""

from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
LAUNCHER = REPO_ROOT / "scripts" / "launch_kiro_worker.sh"


def test_launcher_script_exists() -> None:
    assert LAUNCHER.exists(), f"Expected launcher at {LAUNCHER.relative_to(REPO_ROOT)}."


def test_launcher_still_checks_session() -> None:
    text = LAUNCHER.read_text(encoding="utf-8")
    assert "has-session" in text, (
        "launch_kiro_worker.sh must still verify the tmux session exists "
        "(tmux has-session) — the window check is additive, not a replacement."
    )


def test_launcher_validates_orch_target_window_liveness() -> None:
    text = LAUNCHER.read_text(encoding="utf-8")
    # The window-liveness guard must enumerate the session's windows ...
    assert "list-windows" in text, (
        "launch_kiro_worker.sh must validate the ORCH_TARGET *window* is live "
        "via `tmux list-windows`, not only that the session exists. A stale "
        "marker from a prior session points at a dead window and the worker "
        "wake-up is sent into the void (gotcha card_f5600223ad55)."
    )
    # ... and steer a stale marker back to re-claiming the current window.
    assert "set_orchestrator_window.sh" in text, (
        "On a stale/dead ORCH_TARGET window the launcher must fail loud and "
        "tell the operator to re-claim the current window with "
        "set_orchestrator_window.sh."
    )
    assert "stale" in text.lower(), (
        "The stale-window error message must name the failure mode ('stale') "
        "so the operator recognises the prior-session marker problem."
    )

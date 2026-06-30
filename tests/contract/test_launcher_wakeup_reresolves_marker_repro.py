"""Repro (red) for card_8dfe242c7fc7 — wake-up uses launch-baked ORCH_TARGET.

Problem being proven real (NOT fixed here):
``scripts/launch_kiro_worker.sh`` resolves + liveness-checks ``ORCH_TARGET`` at
LAUNCH time, then bakes that literal value into the worker wrapper via an
unquoted heredoc. The wrapper's ``send_signal`` (the sole wake-up channel) fires
30+ minutes later against that baked literal. If the orchestrator window was
killed and a NEW orchestrator claimed a DIFFERENT window in the meantime, the
launch-time liveness check (card_f5600223ad55) and the window-id rename survival
(test_orchestrator_wakeup_survives_rename) do NOT help — a new window is a new
``@id`` the baked target never learns about, so ``[DONE]`` is send-keys'd into a
dead/foreign pane and the orchestrator never wakes.

The fix the card wants: ``send_signal`` must RE-RESOLVE the orchestrator target
from ``.signals/orchestrator-window.json`` (+ re-check window liveness) at
wake-up time, not trust the launch-baked literal.

This test drives the REAL launcher (tmux PATH-shim) and inspects the generated
wrapper: it asserts the wake-up path re-reads the marker. RED today (the wrapper
contains only the baked literal and never references the marker); GREEN once
send_signal re-resolves at wake-up.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
LAUNCHER = REPO_ROOT / "scripts" / "launch_kiro_worker.sh"
MARKER_BASENAME = "orchestrator-window.json"


def _write_tmux_shim(bin_dir: Path) -> None:
    shim = bin_dir / "tmux"
    shim.write_text(
        "#!/usr/bin/env bash\n"
        'case "$1" in\n'
        "  has-session) exit 0 ;;\n"
        "  display-message) echo faketmux ;;\n"
        "  list-windows) printf '@0\\torch-test\\n' ;;\n"
        "  *) exit 0 ;;\n"
        "esac\n",
        encoding="utf-8",
    )
    shim.chmod(0o755)


def test_wrapper_reresolves_orch_target_at_wakeup(tmp_path: Path) -> None:
    worker = "ttest-wakeup-reresolve"
    baked_target = "faketmux:orch-test"

    prompt_dir = REPO_ROOT / "logs" / "prompts"
    prompt_dir.mkdir(parents=True, exist_ok=True)
    dest = prompt_dir / f"{worker}.md"
    dest.write_text("body {{ORCH_TARGET}}\n", encoding="utf-8")

    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    _write_tmux_shim(bin_dir)

    env = dict(os.environ)
    env["PATH"] = f"{bin_dir}:{env['PATH']}"
    env["ORCH_TARGET"] = baked_target
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

        # Characterization: the launch-time target IS baked into the wrapper.
        assert baked_target in wtext, (
            "sanity: expected the launch-time ORCH_TARGET to be present in the "
            f"generated wrapper; got:\n{wtext[:400]}"
        )

        # RED: the wake-up must re-resolve the orchestrator target from the marker
        # at send time, not rely on the baked literal.
        assert MARKER_BASENAME in wtext, (
            "launch_kiro_worker.sh bakes ORCH_TARGET into the wrapper and never "
            "re-resolves it at wake-up (card_8dfe242c7fc7). The wrapper must "
            f"re-read {MARKER_BASENAME} (+ re-check window liveness) inside "
            "send_signal so a [DONE] still reaches the orchestrator after the "
            "window it was launched against is gone and a new one was claimed."
        )
    finally:
        dest.unlink(missing_ok=True)
        wrapper.unlink(missing_ok=True)

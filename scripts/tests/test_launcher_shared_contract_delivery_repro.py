"""Repro/contract for card_7b9b6a8eac50 — shared/* contracts delivered to workers.

Problem the card pins:
``scripts/launch_kiro_worker.sh`` resolved each name in ``KIRO_REQUIRED_SKILLS``
ONLY as ``<repo|home>/.kiro/skills/<name>/SKILL.md``. A ``shared/<name>.md``
contract (``done-signal-protocol``, ``forbidden-files``, ...) is a plain markdown
FILE, not a skill directory — so it never resolved and was never handed to a
worker. "Dedup by replacing an inlined contract with a path reference" silently
dropped worker-critical contracts.

Fix: the launcher also resolves ``<name>.md``, so ``shared/<name>`` in
``KIRO_REQUIRED_SKILLS`` is delivered under "REQUIRED SKILL SOURCES".

This drives the REAL launcher (tmux PATH-shim) with a freshly-created shared
contract requested via ``KIRO_REQUIRED_SKILLS`` and asserts it is delivered.
The sentinel lives under the real ``~/.kiro/skills/shared/`` (the launcher's home
resolution root) so the test never creates a repo-local ``.kiro/skills/`` tree
(which would un-skip the sibling skill-content contract tests). Skipped when that
home dir is absent (fresh clone / CI).
"""

from __future__ import annotations

import os
import subprocess
import uuid
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
LAUNCHER = REPO_ROOT / "scripts" / "launch_kiro_worker.sh"
HOME_SHARED = Path.home() / ".kiro" / "skills" / "shared"

pytestmark = pytest.mark.skipif(
    not HOME_SHARED.is_dir(),
    reason="~/.kiro/skills/shared not present (skills home untracked, #2820)",
)


def _write_tmux_shim(bin_dir: Path) -> None:
    """A no-op tmux that satisfies the launcher's preflight without side effects."""
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


def test_launcher_delivers_requested_shared_contract(tmp_path: Path) -> None:
    worker = "ttest-shared-delivery"
    token = f"SHARED-SENTINEL-{uuid.uuid4().hex[:8]}"
    shared_name = f"ttest-contract-{uuid.uuid4().hex[:8]}"

    # A shared contract is a *.md FILE under .kiro/skills/shared/ (NOT a SKILL.md
    # dir). Placed in the real home shared/ (an existing dir) so no repo-local
    # .kiro/skills/ tree is created.
    shared_file = HOME_SHARED / f"{shared_name}.md"
    shared_file.write_text(f"# worker-critical contract\n{token}\n", encoding="utf-8")

    prompt_dir = REPO_ROOT / "logs" / "prompts"
    prompt_dir.mkdir(parents=True, exist_ok=True)
    dest = prompt_dir / f"{worker}.md"
    dest.write_text("body {{ORCH_TARGET}}\n", encoding="utf-8")

    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    _write_tmux_shim(bin_dir)

    env = dict(os.environ)
    env["PATH"] = f"{bin_dir}:{env['PATH']}"
    env["ORCH_TARGET"] = "faketmux:orch-test"
    env["KIRO_REQUIRED_SKILLS"] = f"shared/{shared_name}"
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
        materialized = dest.read_text(encoding="utf-8")
        delivered = token in materialized or f"shared/{shared_name}" in materialized
        assert delivered, (
            "launch_kiro_worker.sh did not deliver the requested shared contract "
            f"'shared/{shared_name}' to the worker prompt (card_7b9b6a8eac50). "
            "It must resolve shared/*.md contracts (done-signal-protocol, "
            "forbidden-files, ...), not only <skill>/SKILL.md. "
            f"launcher stderr={result.stderr!r}"
        )
    finally:
        dest.unlink(missing_ok=True)
        shared_file.unlink(missing_ok=True)
        (REPO_ROOT / "logs" / f"{worker}.wrapper.sh").unlink(missing_ok=True)

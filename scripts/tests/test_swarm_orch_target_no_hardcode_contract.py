"""Contract test: no hardcoded ORCH_TARGET in skill wake-up blocks.

Pins the fix for the wake-up dead-window bug (2026-06-17):
- Worker wake-up blocks in skill files must use dynamic ORCH_TARGET resolution
  (read from .signals/orchestrator-window.json or via {{ORCH_TARGET}} placeholder),
  NOT hardcoded tmux window names like 'claude:orch-issues-intake-2026...'.
- Hardcoded window names cause dead-window failures when the orchestrator
  marker is refreshed mid-session.

What is allowed in skill files:
  ORCH_TARGET="$(cat .signals/orchestrator-window.json | jq -r .orchestrator_target)"
  ORCH_TARGET="{{ORCH_TARGET}}"   # launcher substitutes this

What is forbidden in skill files:
  ORCH_TARGET="claude:orch-<anything>-<timestamp>-<hex>"  # hardcoded

Pinned by: scripts/tests/test_swarm_orch_target_no_hardcode_contract.py
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
SKILLS_DIR = REPO_ROOT / ".kiro" / "skills"

# .kiro/ is gitignored and untracked (#2820): skip on fresh clones with no
# local .kiro/skills/ tree.
pytestmark = pytest.mark.skipif(
    not SKILLS_DIR.exists(),
    reason=".kiro/skills/ is untracked (gitignored, #2820)",
)

# Pattern that matches a hardcoded tmux orchestrator window name:
# e.g. claude:orch-issues-intake-20260617T054509-bfb2ec78
# or   claude:orch-main-orch-20260617T062932-cc41b8cf
_HARDCODED_ORCH_TARGET = re.compile(
    r'ORCH_TARGET\s*=\s*["\']'  # ORCH_TARGET="  or  ORCH_TARGET='
    r"[a-zA-Z0-9_-]+:"  # session name e.g. claude:
    r"orch-[a-zA-Z0-9_-]+"  # window prefix orch-*
    r"T\d{6,}"  # timestamp fragment e.g. T054509
    r"[a-f0-9-]*"  # hex suffix
    r'["\']',  # closing quote
    re.IGNORECASE,
)


def _collect_skill_mds() -> list[Path]:
    return sorted(SKILLS_DIR.rglob("*.md")) if SKILLS_DIR.exists() else []


def test_no_hardcoded_orch_target_in_skill_files() -> None:
    """No skill .md file may hardcode a timestamped ORCH_TARGET window name."""
    violations: list[tuple[Path, int, str]] = []
    for path in _collect_skill_mds():
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if _HARDCODED_ORCH_TARGET.search(line):
                violations.append((path, lineno, line.strip()))

    if violations:
        lines = "\n".join(
            f"  {p.relative_to(REPO_ROOT)}:{n}  {snippet}" for p, n, snippet in violations
        )
        raise AssertionError(
            "Hardcoded ORCH_TARGET found in skill files.\n"
            "Use dynamic resolution instead:\n"
            '  ORCH_TARGET="$(cat .signals/orchestrator-window.json'
            ' | jq -r .orchestrator_target)"\n'
            f"Violations:\n{lines}"
        )


def test_swarm_launch_skill_uses_dynamic_orch_target() -> None:
    """swarm-launch/SKILL.md must use the wrapper-owned finish contract (#2820).

    The launcher wrapper is the sole wake-up channel: the worker writes its
    report to {{REPORT_FILE}} and a one-word status to {{STATUS_FILE}}, then
    stops. The skill must NOT instruct the agent to self-send tmux keys (a
    printed-but-not-executed wake-up used to forge a false rail signal).
    """
    launch_skill = SKILLS_DIR / "swarm-launch" / "SKILL.md"
    assert launch_skill.exists(), f"Missing: {launch_skill}"
    content = launch_skill.read_text(encoding="utf-8")

    assert "{{STATUS_FILE}}" in content and "{{REPORT_FILE}}" in content, (
        "swarm-launch/SKILL.md must show the {{REPORT_FILE}} / {{STATUS_FILE}} "
        "placeholders (substituted by the launcher) for the wrapper-owned wake-up."
    )
    assert 'tmux send-keys -t "$ORCH_TARGET"' not in content, (
        "swarm-launch/SKILL.md must NOT tell the agent to self-send the wake-up "
        "via tmux (#2820): the wrapper owns delivery."
    )


def test_swarm_intake_skill_uses_dynamic_orch_target() -> None:
    """swarm-intake/SKILL.md must use the wrapper-owned finish contract (#2820)."""
    intake_skill = SKILLS_DIR / "swarm-intake" / "SKILL.md"
    assert intake_skill.exists(), f"Missing: {intake_skill}"
    content = intake_skill.read_text(encoding="utf-8")

    assert "{{STATUS_FILE}}" in content and "{{REPORT_FILE}}" in content, (
        "swarm-intake/SKILL.md must show the {{REPORT_FILE}} / {{STATUS_FILE}} "
        "placeholders for the wrapper-owned wake-up."
    )
    assert 'tmux send-keys -t "$ORCH_TARGET"' not in content, (
        "swarm-intake/SKILL.md must NOT tell the secretary to self-send the "
        "wake-up via tmux (#2820): the wrapper owns delivery."
    )

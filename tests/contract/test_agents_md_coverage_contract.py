"""Contract test: directories must carry agent guidance.

Each path in `REQUIRED_DIRS` must contain either an `AGENTS.md` (gateway file)
or an `AGENTS.override.md` (scoped override extending the root AGENTS.md).

Refs #1530.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parent.parent.parent

# Directories that must expose AGENTS guidance to coding agents.
# Each entry is repo-root-relative.
REQUIRED_DIRS: list[str] = [
    "telegram_bot",
    "src/ingestion/unified",
    "scripts",
    "services",
    "services/bge-m3-api",
]


@pytest.mark.parametrize("rel_dir", REQUIRED_DIRS)
def test_directory_has_agents_guidance(rel_dir: str) -> None:
    """Every required directory must ship AGENTS.md or AGENTS.override.md."""
    directory = REPO_ROOT / rel_dir
    assert directory.is_dir(), f"Required directory missing: {rel_dir}"

    candidates = [directory / "AGENTS.md", directory / "AGENTS.override.md"]
    found = [c for c in candidates if c.is_file()]

    assert found, (
        f"{rel_dir} lacks AGENTS guidance — expected one of: "
        f"AGENTS.md or AGENTS.override.md (see #1530)."
    )


@pytest.mark.parametrize(
    "path",
    [
        "AGENTS.md",
        "CLAUDE.md",
        "PROJECT.md",
        "CONTEXT.md",
        "services/new-module/AGENTS.md",
        "services/new-module/CLAUDE.md",
        *(f"{rel_dir}/AGENTS.override.md" for rel_dir in REQUIRED_DIRS),
    ],
)
def test_shared_project_docs_are_not_ignored(path: str) -> None:
    """Existing and new project guidance must be addable on either workstation."""
    result = subprocess.run(
        ["git", "check-ignore", "--no-index", "-q", "--", path],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 1, f"{path} is ignored or Git failed: {result.stderr}"


@pytest.mark.parametrize(
    "path",
    [
        ".env",
        ".env.local",
        ".mcp.json",
        "CLAUDE.local.md",
        "services/new-module/AGENTS.override.md",
        ".claude/rules/project.md",
        ".claude/rules/ingestion/contracts.md",
        ".claude/settings.json",
        ".claude/cache/context.md",
        ".claude/prompts/session.md",
        ".codex/config.toml",
        ".worktrees/task/AGENTS.md",
        ".venv/package/AGENTS.md",
        "logs/session.md",
        "docs/reports/generated.md",
        "docs/artifacts/worker.md",
        "docs/audits/old-review.md",
        "docs/superpowers/specs/old-design.md",
        ".swarm/plans/old-worker-plan.md",
    ],
)
def test_local_agent_state_stays_ignored(path: str) -> None:
    """Sharing guidance must not expose private settings or generated state."""
    result = subprocess.run(
        ["git", "check-ignore", "--no-index", "-q", "--", path],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, f"{path} is not ignored or Git failed: {result.stderr}"


@pytest.mark.parametrize("rel_dir", REQUIRED_DIRS)
def test_root_agents_lists_local_override(rel_dir: str) -> None:
    """Root AGENTS.md must advertise every scoped override for discoverability."""
    override_path = f"{rel_dir}/AGENTS.override.md"
    root_agents = (REPO_ROOT / "AGENTS.md").read_text(encoding="utf-8")
    assert override_path in root_agents, (
        f"AGENTS.md must list {override_path} under Local Overrides."
    )

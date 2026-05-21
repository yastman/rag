"""Contract test: directories must carry agent guidance.

Each path in `REQUIRED_DIRS` must contain either an `AGENTS.md` (gateway file)
or an `AGENTS.override.md` (scoped override extending the root AGENTS.md).

Refs #1530.
"""

from __future__ import annotations

from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parent.parent.parent

# Directories that must expose AGENTS guidance to coding agents.
# Each entry is repo-root-relative.
REQUIRED_DIRS: list[str] = [
    "scripts",
    "services",
    "services/bge-m3-api",
    "services/user-base",
    "services/docling",
    "mini_app/frontend/src",
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


@pytest.mark.parametrize("rel_dir", REQUIRED_DIRS)
def test_override_is_gitignore_allowlisted(rel_dir: str) -> None:
    """Scoped override files are ignored by default and must be explicitly allowlisted."""
    override_path = f"{rel_dir}/AGENTS.override.md"
    gitignore = (REPO_ROOT / ".gitignore").read_text(encoding="utf-8")
    assert f"!{override_path}" in gitignore, (
        f"{override_path} must be allowlisted in .gitignore; otherwise future "
        "edits in this scoped guidance file can be silently ignored."
    )


@pytest.mark.parametrize("rel_dir", REQUIRED_DIRS)
def test_root_agents_lists_local_override(rel_dir: str) -> None:
    """Root AGENTS.md must advertise every scoped override for discoverability."""
    override_path = f"{rel_dir}/AGENTS.override.md"
    root_agents = (REPO_ROOT / "AGENTS.md").read_text(encoding="utf-8")
    assert override_path in root_agents, (
        f"AGENTS.md must list {override_path} under Local Overrides."
    )

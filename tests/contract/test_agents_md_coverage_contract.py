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

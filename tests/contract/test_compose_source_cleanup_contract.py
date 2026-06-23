"""Contract test for compose source hygiene (#2195).

The dev Compose project must only reference canonical files inside the
main checkout. Stray temp compose files (``/tmp/compose.*.yml``) and
worktree-checkout compose files mixed into the same project are a
known source of container drift, port-binding overrides, and stale
env files (#2185, #2195).

Behaviour:

- When Docker is unavailable or the ``dev`` project is not running,
  the test is skipped (developer-machine context).
- When the ``dev`` project IS running, its declared ConfigFiles must
  not include any path under ``/tmp`` and must not span more than one
  checkout root.

Operator runbook: ``docs/runbooks/COMPOSE_SOURCE_CLEANUP.md``.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
RUNBOOK = REPO_ROOT / "docs" / "runbooks" / "COMPOSE_SOURCE_CLEANUP.md"


def _docker_available() -> bool:
    return shutil.which("docker") is not None


def _list_dev_compose_sources() -> list[str] | None:
    """Return ConfigFiles for the local 'dev' Compose project, or None when
    Docker / the project is not present.
    """
    if not _docker_available():
        return None
    try:
        cp = subprocess.run(  # nosec B603 B607
            ["docker", "compose", "ls", "--all", "--format", "json"],
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (subprocess.TimeoutExpired, OSError):
        return None
    if cp.returncode != 0:
        return None
    try:
        projects = json.loads(cp.stdout or "[]")
    except json.JSONDecodeError:
        return None
    for project in projects:
        if project.get("Name") == "dev":
            raw = project.get("ConfigFiles") or ""
            return [p for p in raw.split(",") if p]
    return None


def test_compose_source_cleanup_runbook_exists() -> None:
    """The runbook documenting the canonical cleanup must exist."""
    assert RUNBOOK.is_file(), f"missing runbook: {RUNBOOK}"
    text = RUNBOOK.read_text(encoding="utf-8")
    # Must contain key terms operators search for.
    for term in ("compose.yml", "compose.dev.yml", "/tmp/compose", "docker compose ls"):
        assert term in text, f"runbook must mention {term!r}"


def test_runbook_referenced_from_runbooks_index() -> None:
    """The new runbook must be linked from docs/runbooks/README.md."""
    index = REPO_ROOT / "docs" / "runbooks" / "README.md"
    text = index.read_text(encoding="utf-8")
    assert "COMPOSE_SOURCE_CLEANUP.md" in text, (
        "runbook must be linked from docs/runbooks/README.md"
    )


def test_dev_compose_project_has_no_stray_tmp_sources() -> None:
    """When the dev Compose project is running, ConfigFiles must not include
    ``/tmp/compose.*.yml`` overrides (#2195)."""
    sources = _list_dev_compose_sources()
    if sources is None:
        pytest.skip("Docker not available or 'dev' Compose project not running")
    stray = [s for s in sources if s.startswith("/tmp/")]
    assert not stray, (
        f"stray /tmp compose sources active in dev project: {stray}; "
        f"see docs/runbooks/COMPOSE_SOURCE_CLEANUP.md to recreate the project"
    )


def test_dev_compose_project_uses_single_checkout_root() -> None:
    """When the dev Compose project is running, its compose files must come
    from a single checkout root — not be a mix of multiple worktrees (#2195)."""
    sources = _list_dev_compose_sources()
    if sources is None:
        pytest.skip("Docker not available or 'dev' Compose project not running")
    roots: set[str] = set()
    for raw in sources:
        path = Path(raw)
        # Pick a stable parent — the directory containing compose*.yml
        # is the checkout root for our purposes.
        roots.add(str(path.parent))
    # Allow a single canonical root + at most one /tmp override caught by the
    # other test; the meaningful failure is mixing 2+ real checkouts.
    real_roots = {r for r in roots if not r.startswith("/tmp")}
    assert len(real_roots) <= 1, (
        f"dev project mixes compose files from multiple checkouts: {sorted(real_roots)}; "
        f"see docs/runbooks/COMPOSE_SOURCE_CLEANUP.md"
    )

"""Contract test for issue #2285 — read-only candidate-validation gate.

`make check` (and its `lint` / `type-check` deps) invoked plain `uv run`, which
syncs the project environment before running. In shared/reused `.venv`
candidate worktrees this silently uninstalls/installs packages during what is
supposed to be a *validation* step, mutating the environment and potentially
switching versions between candidates.

This contract pins the fix:

* a dedicated ``check-frozen`` (candidate-validation) target exists;
* it preflights with a read-only lock check (``uv sync --frozen --check``) so a
  stale env fails with guidance instead of being auto-synced;
* its lint/type-check commands run via the no-sync runner (``uv run --no-sync``
  / ``$(UV_RUN_NO_SYNC)``), never a plain auto-syncing ``uv run``;
* developer-friendly ``make check`` is left intact (still allowed to auto-sync).
"""

from __future__ import annotations

import re
from pathlib import Path


REPO = Path(__file__).resolve().parents[2]
MAKEFILE = REPO / "Makefile"


def _makefile_text() -> str:
    return MAKEFILE.read_text(encoding="utf-8")


def _target_block(text: str, target: str) -> str:
    pattern = rf"^{re.escape(target)}:.*?(?=^[A-Za-z0-9_.-]+:|\Z)"
    match = re.search(pattern, text, re.MULTILINE | re.DOTALL)
    assert match, f"Makefile must define a {target!r} target (#2285)"
    return match.group(0)


def test_check_frozen_target_exists() -> None:
    text = _makefile_text()
    assert re.search(r"^check-frozen:", text, re.MULTILINE), (
        "Makefile must define a read-only candidate-validation target "
        "'check-frozen' (#2285)."
    )


def test_check_frozen_preflights_with_readonly_lock_check() -> None:
    block = _target_block(_makefile_text(), "check-frozen")
    # Read-only env verification: uv sync --frozen --check (no mutation).
    assert "uv sync --frozen --check" in block, (
        "check-frozen must preflight the environment read-only with "
        "'uv sync --frozen --check' so a stale .venv fails with guidance "
        "instead of being auto-synced (#2285)."
    )


def test_check_frozen_runs_tools_without_autosync() -> None:
    block = _target_block(_makefile_text(), "check-frozen")
    # ruff + mypy must run, and must not use a bare auto-syncing `uv run`.
    assert "ruff check" in block and "mypy" in block, (
        "check-frozen must run both ruff and mypy (#2285)."
    )
    no_sync = "$(UV_RUN_NO_SYNC)" in block or "uv run --no-sync" in block
    assert no_sync, (
        "check-frozen must execute lint/type-check via the no-sync runner "
        "($(UV_RUN_NO_SYNC) / 'uv run --no-sync'), never a plain auto-syncing "
        "'uv run' (#2285)."
    )
    # Guard against an accidental bare `uv run ` (auto-sync) in the recipe.
    bare_uv_run = re.findall(r"(?<!\S)uv run (?!--no-sync)", block)
    assert not bare_uv_run, (
        "check-frozen must not use a bare auto-syncing 'uv run' "
        f"(found {len(bare_uv_run)}); use $(UV_RUN_NO_SYNC) (#2285)."
    )


def test_check_frozen_is_documented_in_help() -> None:
    block = _target_block(_makefile_text(), "check-frozen")
    assert "##" in block, (
        "check-frozen must carry a '## ' help annotation so it appears in "
        "`make help` (#2285)."
    )

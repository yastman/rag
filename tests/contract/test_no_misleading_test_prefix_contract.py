"""Contract test for issue #1950 — no `test_*` files outside `tests/`.

Files named `test_*.py` or `test_*.sh` are expected by every reader to be
pytest collection or test scripts. Putting non-test scripts (A/B
benchmarks, health probes, etc.) under `scripts/test_*` creates real
hazards:

* `pytest <path>` collects them on demand even though `testpaths = ["tests"]`
  keeps them out of default collection.
* `find . -name "test_*.py"` in CI helper scripts pulls them in.
* New contributors expect "everything named test_* is a test".

This contract test enforces the rule. Tests themselves live under `tests/`
(this file included). Any other file beginning with `test_` is rejected.
"""

from __future__ import annotations

from pathlib import Path

REPO = Path(__file__).resolve().parents[2]

# Directories that we never traverse for the purposes of this check.
SKIP_DIRS = {
    ".git",
    ".venv",
    "venv",
    "node_modules",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    "site",
    "dist",
    "build",
    "tests",  # pytest tests live here — that is the allowed home
    ".kiro",
    ".agents",
    ".worktrees",
}


def _is_skipped(path: Path) -> bool:
    return any(part in SKIP_DIRS for part in path.parts)


def test_no_misleading_test_prefix_outside_tests_dir() -> None:
    offenders = []
    for ext in ("py", "sh"):
        for path in REPO.rglob(f"test_*.{ext}"):
            rel = path.relative_to(REPO)
            if _is_skipped(rel):
                continue
            offenders.append(str(rel))
    assert offenders == [], (
        "Files matching `test_*.{py,sh}` outside `tests/` are misleading: "
        "pytest collection on a path or a `find . -name 'test_*'` sweep will "
        "treat them as tests even though they are not. Move them under "
        "`scripts/benchmark/`, `scripts/probe/`, or rename to drop the "
        f"`test_` prefix. Offenders: {offenders}"
    )

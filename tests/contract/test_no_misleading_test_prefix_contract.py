"""Contract: no misleading test_* files outside the tests/ directory (#1950).

Scripts named ``test_*.py`` or ``test_*.sh`` that live outside ``tests/``
confuse developers (they look like pytest tests) and can be accidentally
collected by ``pytest --rootdir=.``.  All test files belong under
``tests/``; operational scripts should use descriptive non-test prefixes
(e.g. ``benchmark_``, ``probe_``, ``check_``).

Exclusions:
- ``tests/`` — the canonical home for test files.
- ``scripts/e2e/`` — end-to-end test scenario helpers invoked by CI,
  not standalone pytest tests.
- ``.venv/``, ``.git/``, ``node_modules/``, ``__pycache__/`` — generated
  or third-party directories.

Refs #1950.
"""

from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]

_EXCLUDED_SEGMENTS = {
    "/tests/",
    "/.venv/",
    "/.git/",
    "/node_modules/",
    "/__pycache__/",
    "/scripts/e2e/",
}


def _is_excluded(path: Path) -> bool:
    """Return True if the path contains any excluded directory segment."""
    s = f"/{path.relative_to(REPO_ROOT).as_posix()}/"
    return any(seg in s for seg in _EXCLUDED_SEGMENTS)


def _find_offending_files() -> list[Path]:
    """Glob the repo for test_*.py and test_*.sh outside allowed directories."""
    offenders: list[Path] = []
    for pattern in ("**/test_*.py", "**/test_*.sh"):
        for path in REPO_ROOT.glob(pattern):
            if not _is_excluded(path):
                offenders.append(path)
    offenders.sort()
    return offenders


def test_no_test_prefix_outside_tests_dir() -> None:
    """No test_* files may exist outside tests/ (and other excluded dirs).

    Scripts with a ``test_`` prefix belong under ``tests/``.  Operational
    scripts should be renamed to use a descriptive prefix that does not
    collide with pytest collection (e.g. ``benchmark_``, ``probe_``).

    If this test fails, either:
    1. Move the file into the appropriate ``tests/`` subdirectory, or
    2. Rename the script to drop the ``test_`` prefix (#1950).
    """
    offenders = _find_offending_files()
    if offenders:
        paths_str = "\n  ".join(
            str(p.relative_to(REPO_ROOT)) for p in offenders
        )
        raise AssertionError(
            f"Found {len(offenders)} file(s) with a test_* prefix outside "
            f"tests/ (and other excluded directories):\n  {paths_str}\n"
            "Rename or relocate these files to avoid confusion with pytest "
            "test modules (#1950)."
        )

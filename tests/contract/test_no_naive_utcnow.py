"""Contract test: production code must not use naive `datetime.utcnow()`.

`datetime.utcnow()` returns a naive datetime (no tzinfo). It is deprecated
in Python 3.12+ and silently mixes with timezone-aware datetimes returned
by SDKs such as Langfuse, leading to drift or `TypeError` at compare time.

Replacement is `datetime.now(UTC)` (or `datetime.now(timezone.utc)`).

This test scans production code paths via AST and reports every offending
call site. Test code (`tests/`) is intentionally excluded — historical
fixtures may still construct naive datetimes for compatibility checks.

Refs #1640.
"""

from __future__ import annotations

import ast
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent.parent

# Production code paths that must not contain naive UTC constructors.
SCAN_DIRS = [
    REPO_ROOT / "scripts",
    REPO_ROOT / "src",
    REPO_ROOT / "telegram_bot",
    REPO_ROOT / "mini_app",
    REPO_ROOT / "services",
]

# Forbidden datetime constructors (all return naive datetimes).
FORBIDDEN_ATTRS = {"utcnow", "utcfromtimestamp"}


def _iter_python_files(directories: list[Path]) -> list[Path]:
    files: list[Path] = []
    for d in directories:
        if not d.exists():
            continue
        files.extend(p for p in d.rglob("*.py") if "/.venv/" not in str(p))
    return files


def _find_naive_utc_calls(source: str, file_path: Path) -> list[tuple[Path, int, str]]:
    """Return [(file, lineno, full-call-name)] for every forbidden call in source."""
    try:
        tree = ast.parse(source, filename=str(file_path))
    except SyntaxError:
        return []

    offenders: list[tuple[Path, int, str]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        # Match `datetime.utcnow(...)` and `datetime.utcfromtimestamp(...)`
        # whether `datetime` is the class or the module is irrelevant —
        # both yield naive datetimes and are forbidden.
        if isinstance(func, ast.Attribute) and func.attr in FORBIDDEN_ATTRS:
            target = ast.unparse(func)
            offenders.append((file_path, node.lineno, target))
    return offenders


def test_no_naive_utcnow_in_production_code() -> None:
    """No production module may call datetime.utcnow() / utcfromtimestamp()."""
    offenders: list[tuple[Path, int, str]] = []
    for py_file in _iter_python_files(SCAN_DIRS):
        offenders.extend(_find_naive_utc_calls(py_file.read_text(), py_file))

    if offenders:
        rel = [
            f"  {p.relative_to(REPO_ROOT)}:{lineno} -> {name}()"
            for p, lineno, name in offenders
        ]
        msg = (
            "Naive UTC datetime constructors found in production code "
            "(see #1640). Replace with `datetime.now(UTC)`:\n"
            + "\n".join(rel)
        )
        raise AssertionError(msg)

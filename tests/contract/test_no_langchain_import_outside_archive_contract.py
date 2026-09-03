"""Contract: no langchain / langchain_core imports in kept tests outside archive/.

Guards against test-debt regression introduced in #2619: after the migration
off LangChain the kept tests must not import langchain or langchain_core
directly.  Only archive/ is an allowed exception zone.

Bug class: test-debt/langchain-core-import
Canonical issue: #2619
"""

from __future__ import annotations

import ast
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]

# Directories that are allowed to contain langchain imports.
ALLOWLIST_PREFIXES = (REPO_ROOT / "archive",)

# Top-level package names that must not appear in kept-test imports.
FORBIDDEN_TOPS = {"langchain", "langchain_core"}


def _collect_python_files(root: Path) -> list[Path]:
    return [
        p
        for p in root.rglob("*.py")
        if not any(p.is_relative_to(prefix) for prefix in ALLOWLIST_PREFIXES)
    ]


def _langchain_imports_in_file(path: Path) -> list[str]:
    """Return list of offending import strings found in *path*."""
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except SyntaxError:
        return []

    offenders: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                top = alias.name.split(".", 1)[0]
                if top in FORBIDDEN_TOPS:
                    offenders.append(alias.name)
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            top = module.split(".", 1)[0]
            if top in FORBIDDEN_TOPS:
                offenders.append(module)
    return offenders


def test_no_langchain_import_in_tests_outside_archive() -> None:
    """tests/ must not contain langchain / langchain_core imports outside archive/."""
    tests_root = REPO_ROOT / "tests"
    files = _collect_python_files(tests_root)

    violations: dict[str, list[str]] = {}
    for path in sorted(files):
        found = _langchain_imports_in_file(path)
        if found:
            violations[str(path.relative_to(REPO_ROOT))] = found

    assert not violations, (
        "langchain / langchain_core imports found outside archive/ in tests/:\n"
        + "\n".join(f"  {f}: {imps}" for f, imps in violations.items())
        + "\nReplace with local stubs (dataclasses, unittest.mock, etc.) or move to archive/."
    )


def test_no_langchain_import_in_scripts_outside_archive() -> None:
    """scripts/ must not contain langchain / langchain_core imports outside archive/."""
    scripts_root = REPO_ROOT / "scripts"
    if not scripts_root.exists():
        return
    files = _collect_python_files(scripts_root)

    violations: dict[str, list[str]] = {}
    for path in sorted(files):
        found = _langchain_imports_in_file(path)
        if found:
            violations[str(path.relative_to(REPO_ROOT))] = found

    assert not violations, (
        "langchain / langchain_core imports found outside archive/ in scripts/:\n"
        + "\n".join(f"  {f}: {imps}" for f, imps in violations.items())
        + "\nReplace with local tooling equivalents."
    )

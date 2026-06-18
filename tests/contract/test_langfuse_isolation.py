"""Contract: no file outside src/observability/ may import directly from langfuse.

All langfuse access must go through src.observability re-exports.

Exclusions:
- src/observability/ itself (the kernel)
- archive/ directory (archived code, not in active runtime)
- tests/ directory (test fixtures may use langfuse for assertions)
- services/bge-m3-api/ (standalone service with its own dependency footprint)
"""

from __future__ import annotations

import ast
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]

# Directories excluded from the isolation check
_EXCLUDED_PREFIXES = (
    "src/observability/",
    "archive/",
    "tests/",
    "services/bge-m3-api/",
    "scripts/archive/",
    ".venv/",
)

# Production directories scanned for archive/ import violations
_PRODUCTION_DIRS = (
    "src/",
    "telegram_bot/",
    "scripts/",
    "services/",
)

# Ratchet: maximum number of files allowed to import langfuse directly outside
# the exclusion list above.  Current count is 0; must never grow.
_MAX_DIRECT_LANGFUSE_FILES = 0


def _has_direct_langfuse_import(path: Path) -> list[str]:
    """Return list of violation strings (file:line: description) for direct langfuse imports."""
    try:
        source = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return []

    try:
        tree = ast.parse(source, filename=str(path))
    except SyntaxError:
        return []

    violations: list[str] = []
    rel = path.relative_to(REPO_ROOT)

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == "langfuse" or alias.name.startswith("langfuse."):
                    violations.append(f"{rel}:{node.lineno}: import {alias.name}")
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            if module == "langfuse" or module.startswith("langfuse."):
                violations.append(f"{rel}:{node.lineno}: from {module} import ...")

    return violations


def _is_excluded(path: Path) -> bool:
    rel = path.relative_to(REPO_ROOT).as_posix()
    return any(rel.startswith(prefix) for prefix in _EXCLUDED_PREFIXES)


def test_no_direct_langfuse_imports_outside_observability() -> None:
    """All langfuse access must go through src.observability re-exports."""
    violations: list[str] = []

    for py_file in sorted(REPO_ROOT.rglob("*.py")):
        if _is_excluded(py_file):
            continue
        violations.extend(_has_direct_langfuse_import(py_file))

    assert violations == [], (
        "Files outside src/observability/ must not import langfuse directly.\n"
        "Route through: from src.observability import <symbol>\n"
        "Violations:\n" + "\n".join(f"  {v}" for v in violations)
    )


def test_direct_langfuse_files_count_ratchet() -> None:
    """Ratchet: number of direct-langfuse files must not exceed the pinned max.

    Current allowed max is 0.  To intentionally add a new allowed file, update
    _MAX_DIRECT_LANGFUSE_FILES and add a justification comment.
    """
    offending: list[str] = []

    for py_file in sorted(REPO_ROOT.rglob("*.py")):
        if _is_excluded(py_file):
            continue
        if _has_direct_langfuse_import(py_file):
            offending.append(py_file.relative_to(REPO_ROOT).as_posix())

    assert len(offending) <= _MAX_DIRECT_LANGFUSE_FILES, (
        f"Direct-langfuse file count ({len(offending)}) exceeds ratchet "
        f"({_MAX_DIRECT_LANGFUSE_FILES}).\n"
        "To raise the limit, update _MAX_DIRECT_LANGFUSE_FILES with a justification.\n"
        "Files: " + ", ".join(offending)
    )


def test_no_archive_imports_in_production() -> None:
    """Production code must not import from the archive/ namespace.

    archive/ is removed from the active runtime (PR #2804).  Any surviving
    reference in src/, telegram_bot/, scripts/, or services/ is a dangling
    import that would fail at runtime.
    """
    violations: list[str] = []

    for prod_dir in _PRODUCTION_DIRS:
        scan_root = REPO_ROOT / prod_dir
        if not scan_root.exists():
            continue
        for py_file in sorted(scan_root.rglob("*.py")):
            try:
                source = py_file.read_text(encoding="utf-8")
                tree = ast.parse(source, filename=str(py_file))
            except (OSError, UnicodeDecodeError, SyntaxError):
                continue
            rel = py_file.relative_to(REPO_ROOT)
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        if alias.name == "archive" or alias.name.startswith("archive."):
                            violations.append(f"{rel}:{node.lineno}: import {alias.name}")
                elif isinstance(node, ast.ImportFrom):
                    module = node.module or ""
                    if module == "archive" or module.startswith("archive."):
                        violations.append(f"{rel}:{node.lineno}: from {module} import ...")

    assert violations == [], (
        "Production code must not import from archive/.\n"
        "archive/ was removed in PR #2804; these are dangling references:\n"
        + "\n".join(f"  {v}" for v in violations)
    )


def test_observability_init_exports_all_imported_symbols() -> None:
    """src/observability/__init__.py must declare __all__ covering every imported name.

    Callers that do ``from src.observability import *`` must get the full public
    surface without needing to know individual submodules.  This test enforces
    that every name brought in via an ``import`` or ``from … import`` statement
    is also listed in ``__all__``.
    """
    init_path = REPO_ROOT / "src" / "observability" / "__init__.py"
    source = init_path.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(init_path))

    imported_names: set[str] = set()
    all_names: set[str] = set()

    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            for alias in node.names:
                imported_names.add(alias.asname or alias.name)
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "__all__":
                    for elt in node.value.elts:  # type: ignore[attr-defined]
                        if isinstance(elt, ast.Constant):
                            all_names.add(elt.value)

    assert all_names, "src/observability/__init__.py must define __all__"

    missing = imported_names - all_names
    assert not missing, (
        "These names are imported in src/observability/__init__.py but missing from __all__:\n"
        + "\n".join(f"  {n}" for n in sorted(missing))
        + "\nAdd them to __all__ so callers can discover the full public surface."
    )

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

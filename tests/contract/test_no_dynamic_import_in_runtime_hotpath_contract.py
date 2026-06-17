"""Contract: no filesystem dynamic import (spec_from_file_location / exec_module)
in the src/runtime hot-path (#2620).

Dynamic filesystem imports bypass normal import caching, type identity checks,
and layering guardrails. The fix moves topic-hint helpers into a stable module
imported normally. This contract prevents regression.
"""

from __future__ import annotations

import ast
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
# Guard the runtime hot-path modules only (not tests or ingestion)
GUARDED_ROOTS = (REPO_ROOT / "src" / "runtime",)

# AST attribute names that indicate filesystem dynamic import
_FORBIDDEN_CALLS = frozenset(
    {
        "spec_from_file_location",
        "exec_module",
    }
)


def _find_dynamic_import_calls(path: Path) -> list[str]:
    """Return list of forbidden call names found in the file."""
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except SyntaxError:
        return []
    hits: list[str] = []
    for node in ast.walk(tree):
        # func.attr style: importlib.util.spec_from_file_location(...)
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr in _FORBIDDEN_CALLS
        ):
            hits.append(node.func.attr)
    return hits


def test_no_filesystem_dynamic_import_in_src_runtime() -> None:
    """src/runtime must not use spec_from_file_location or exec_module (#2620)."""
    violations: dict[str, list[str]] = {}
    for root in GUARDED_ROOTS:
        if not root.exists():
            continue
        for path in sorted(root.rglob("*.py")):
            calls = _find_dynamic_import_calls(path)
            if calls:
                violations[path.relative_to(REPO_ROOT).as_posix()] = calls

    assert not violations, (
        "#2620: filesystem dynamic import detected in src/runtime. "
        "Import topic-hint helpers (or any module) via normal static imports "
        "so the module cache is used and layering is respected. "
        f"Violations: {violations}"
    )

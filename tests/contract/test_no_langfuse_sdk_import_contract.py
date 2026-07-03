"""Contract: no real Langfuse SDK imports remain in src/, telegram_bot/, scripts/, or services/ (#2951).

Bug class: incomplete-removal — half-done feature removal leaves dead shim.
The shim in src/observability/ is intentional; direct `from langfuse import …`
or `import langfuse` in production code is forbidden.
"""

from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
_SCAN_DIRS = ["src", "telegram_bot", "scripts", "services"]


def _is_real_langfuse_import(node: ast.stmt) -> bool:
    """Return True if the node is a direct langfuse SDK import."""
    if isinstance(node, ast.Import):
        return any(
            alias.name == "langfuse" or alias.name.startswith("langfuse.") for alias in node.names
        )
    if isinstance(node, ast.ImportFrom):
        return node.module is not None and (
            node.module == "langfuse" or node.module.startswith("langfuse.")
        )
    return False


def test_no_langfuse_sdk_imports_in_src_and_telegram_bot() -> None:
    """No file in src/, telegram_bot/, scripts/, or services/ may import the real Langfuse SDK directly."""
    violations: list[str] = []
    for dir_name in _SCAN_DIRS:
        scan_dir = ROOT / dir_name
        if not scan_dir.exists():
            continue
        for py_file in sorted(scan_dir.rglob("*.py")):
            try:
                tree = ast.parse(py_file.read_text(encoding="utf-8"), filename=str(py_file))
            except SyntaxError:
                continue
            for node in ast.walk(tree):
                if _is_real_langfuse_import(node):
                    rel = py_file.relative_to(ROOT)
                    violations.append(f"{rel}:{node.lineno}")
    assert not violations, (
        "Direct Langfuse SDK imports found (bug class: incomplete-removal, #2951):\n"
        + "\n".join(f"  {v}" for v in violations)
        + "\n\nUse src.observability no-op stubs instead of importing langfuse directly."
    )

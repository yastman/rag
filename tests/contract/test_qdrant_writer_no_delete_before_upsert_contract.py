# tests/contract/test_qdrant_writer_no_delete_before_upsert_contract.py
"""AST contract: no delete call before upsert call in upsert_chunks_sync (#1602).

Walks the AST of upsert_chunks_sync and asserts that any call that looks like
a 'delete' / 'delete_file_sync' appears only AFTER the first call that looks
like 'upsert' / '_upsert_points_in_batches'.

This is a static structural guard — it catches regressions even if mocks
change or new callers are added.
"""

from __future__ import annotations

import ast
import textwrap
from pathlib import Path


SOURCE_FILE = (
    Path(__file__).parent.parent.parent
    / "src"
    / "ingestion"
    / "unified"
    / "qdrant_writer.py"
)

# Names that constitute an "upsert" operation
UPSERT_NAMES = {"upsert", "_upsert_points_in_batches", "upsert_chunks_sync"}

# Names that constitute a "delete" operation
DELETE_NAMES = {"delete", "delete_file_sync", "delete_file"}


def _extract_call_names_in_order(func_node: ast.FunctionDef) -> list[str]:
    """Walk the function body and return call names in source order.

    Captures both:
    - ``foo(...)``           → "foo"
    - ``self.foo(...)``      → "foo"
    - ``obj.attr.foo(...)``  → "foo"
    """
    call_names: list[str] = []

    class _CallCollector(ast.NodeVisitor):
        def visit_Call(self, node: ast.Call) -> None:  # noqa: N802
            func = node.func
            if isinstance(func, ast.Attribute):
                call_names.append(func.attr)
            elif isinstance(func, ast.Name):
                call_names.append(func.id)
            self.generic_visit(node)

    _CallCollector().visit(func_node)
    return call_names


def _find_function(tree: ast.Module, name: str) -> ast.FunctionDef | None:
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return node
    return None


def test_no_delete_before_upsert_in_upsert_chunks_sync() -> None:
    """upsert_chunks_sync must not call delete before upsert."""
    source = SOURCE_FILE.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(SOURCE_FILE))

    func = _find_function(tree, "upsert_chunks_sync")
    assert func is not None, (
        f"Could not find 'upsert_chunks_sync' in {SOURCE_FILE}. "
        "Was it renamed or removed?"
    )

    call_names = _extract_call_names_in_order(func)

    upsert_positions = [i for i, name in enumerate(call_names) if name in UPSERT_NAMES]
    delete_positions = [i for i, name in enumerate(call_names) if name in DELETE_NAMES]

    # If there's no upsert call something is very wrong
    assert upsert_positions, (
        f"No upsert-family call found in upsert_chunks_sync. Calls seen: {call_names}"
    )

    if not delete_positions:
        # No delete at all is also fine (all-new content, nothing stale to remove)
        return

    first_upsert = min(upsert_positions)
    first_delete = min(delete_positions)

    assert first_upsert < first_delete, (
        f"CONTRACT VIOLATION (#1602): delete-family call ('{call_names[first_delete]}', "
        f"call-index {first_delete}) appears before "
        f"upsert-family call ('{call_names[first_upsert]}', call-index {first_upsert}) "
        f"in upsert_chunks_sync.\n"
        f"Full call sequence: {call_names}\n"
        "Fix: move delete to AFTER successful upsert."
    )


def test_upsert_chunks_sync_has_no_delete_file_sync_early_call() -> None:
    """Explicit check: delete_file_sync must not appear before _upsert_points_in_batches."""
    source = SOURCE_FILE.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(SOURCE_FILE))

    func = _find_function(tree, "upsert_chunks_sync")
    assert func is not None

    call_names = _extract_call_names_in_order(func)

    try:
        upsert_idx = call_names.index("_upsert_points_in_batches")
    except ValueError:
        pytest.fail(
            f"'_upsert_points_in_batches' not found in upsert_chunks_sync calls: {call_names}"
        )

    delete_file_positions = [
        i for i, name in enumerate(call_names) if name == "delete_file_sync"
    ]

    early_deletes = [pos for pos in delete_file_positions if pos < upsert_idx]
    assert not early_deletes, (
        f"CONTRACT VIOLATION (#1602): delete_file_sync called at position(s) {early_deletes} "
        f"which is before _upsert_points_in_batches at position {upsert_idx}.\n"
        f"Full call sequence: {call_names}"
    )

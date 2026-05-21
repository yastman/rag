# tests/contract/test_qdrant_writer_atomic_replace_contract.py
"""Static guardrail for #1602 — qdrant_writer must not delete-before-upsert.

The bug: ``upsert_chunks_sync`` previously called ``delete_file_sync`` at the
top of the function, before any embedding work or upsert. If embedding or
upsert failed afterwards, the document was wiped from search until the next
successful retry.

The fix: build replacement points first, upsert with deterministic IDs, and
then sweep stale orphan IDs via ``_delete_stale_points_sync``.

This contract enforces the structural shape of the fix so a refactor can't
silently regress to the destructive delete-first pattern.
"""

from __future__ import annotations

import ast
import textwrap
from pathlib import Path

import pytest


_WRITER_PATH = (
    Path(__file__).resolve().parents[2] / "src" / "ingestion" / "unified" / "qdrant_writer.py"
)


def _load_function(name: str) -> ast.FunctionDef | ast.AsyncFunctionDef:
    """Return the AST node for ``QdrantHybridWriter.<name>``."""
    tree = ast.parse(_WRITER_PATH.read_text(encoding="utf-8"))
    for cls in ast.walk(tree):
        if not isinstance(cls, ast.ClassDef) or cls.name != "QdrantHybridWriter":
            continue
        for node in cls.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
                return node
    pytest.fail(f"QdrantHybridWriter.{name} not found in {_WRITER_PATH}")


def _self_method_calls(func: ast.AST) -> list[str]:
    """Return the list of ``self.<method>`` call targets in ``func``."""
    calls: list[str] = []
    for node in ast.walk(func):
        if not isinstance(node, ast.Call):
            continue
        target = node.func
        if (
            isinstance(target, ast.Attribute)
            and isinstance(target.value, ast.Name)
            and target.value.id == "self"
        ):
            calls.append(target.attr)
    return calls


@pytest.mark.parametrize("func_name", ["upsert_chunks", "upsert_chunks_sync"])
def test_upsert_does_not_call_destructive_delete_helpers(func_name: str) -> None:
    """``upsert_chunks*`` must not call ``delete_file`` / ``delete_file_sync``."""
    func = _load_function(func_name)
    calls = _self_method_calls(func)
    forbidden = {"delete_file", "delete_file_sync"}
    found = forbidden.intersection(calls)
    assert not found, textwrap.dedent(
        f"""
        QdrantHybridWriter.{func_name} must not invoke {sorted(found)}; they
        delete by metadata.file_id Filter and run BEFORE the upsert, which is
        the data-loss pattern called out in #1602. Use
        ``self._delete_stale_points_sync`` AFTER a successful upsert instead.
        """
    ).strip()


@pytest.mark.parametrize("func_name", ["upsert_chunks", "upsert_chunks_sync"])
def test_upsert_calls_post_upsert_stale_sweep(func_name: str) -> None:
    """``upsert_chunks*`` must perform the stale-id sweep after the upsert."""
    func = _load_function(func_name)
    calls = _self_method_calls(func)
    assert "_delete_stale_points_sync" in calls, textwrap.dedent(
        f"""
        QdrantHybridWriter.{func_name} must call
        ``self._delete_stale_points_sync`` after the replacement upsert
        completes successfully. This is the safe orphan-sweep half of the
        atomic-replace pattern from #1602.
        """
    ).strip()


@pytest.mark.parametrize("func_name", ["upsert_chunks", "upsert_chunks_sync"])
def test_stale_sweep_runs_after_upsert(func_name: str) -> None:
    """Inside the function body, ``_upsert_points_in_batches`` must precede
    ``_delete_stale_points_sync``."""
    func = _load_function(func_name)
    calls = _self_method_calls(func)
    if "_upsert_points_in_batches" not in calls or "_delete_stale_points_sync" not in calls:
        pytest.fail(
            f"{func_name} must call both _upsert_points_in_batches and "
            f"_delete_stale_points_sync; got {calls}"
        )
    assert calls.index("_upsert_points_in_batches") < calls.index("_delete_stale_points_sync"), (
        textwrap.dedent(
            f"""
        In QdrantHybridWriter.{func_name}, the call to
        ``self._upsert_points_in_batches`` must precede the call to
        ``self._delete_stale_points_sync``. If the order is inverted the
        function falls back to the destructive delete-first pattern from
        #1602.
        """
        ).strip()
    )

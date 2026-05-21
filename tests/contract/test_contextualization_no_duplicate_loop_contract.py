"""Contract: provider.contextualize must not duplicate the per-chunk loop (#1533).

The base class ``ContextualizeProvider.contextualize_batch`` already implements
concurrent per-chunk dispatch with a TaskGroup, semaphore, and fallback
``ContextualizedChunk(context_method="none")``. Each provider used to ship its
own sequential ``for i, chunk in enumerate(chunks): try/except`` copy of that
logic. This contract pins the deduplication: each provider's
``contextualize`` must be a thin delegate that calls
``self.contextualize_batch(...)``.

Failure modes blocked:
  - re-introducing a ``for`` loop over ``chunks`` inside a provider override
  - re-introducing a ``try/except`` per-chunk fallback inside a provider override
  - dropping the ``contextualize_batch`` delegation
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest


PROVIDER_FILES = (
    "src/contextualization/claude.py",
    "src/contextualization/groq.py",
    "src/contextualization/openai.py",
)


def _find_contextualize_method(tree: ast.Module) -> ast.AsyncFunctionDef:
    """Return the AsyncFunctionDef node for the ``contextualize`` method.

    Searches inside the (single) class definition in the module.
    """
    for class_node in ast.walk(tree):
        if not isinstance(class_node, ast.ClassDef):
            continue
        for item in class_node.body:
            if isinstance(item, ast.AsyncFunctionDef) and item.name == "contextualize":
                return item
    raise AssertionError("No async contextualize method found in module")


def _calls_contextualize_batch(method: ast.AsyncFunctionDef) -> bool:
    """Return True if the method body invokes self.contextualize_batch."""
    for node in ast.walk(method):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if isinstance(func, ast.Attribute) and func.attr == "contextualize_batch":
            return True
    return False


def _has_chunk_loop(method: ast.AsyncFunctionDef) -> bool:
    """Return True if the method body contains a (Async)For loop."""
    for node in ast.walk(method):
        if isinstance(node, (ast.For, ast.AsyncFor)):
            return True
    return False


def _has_try_except(method: ast.AsyncFunctionDef) -> bool:
    """Return True if the method body contains a try/except block."""
    for node in ast.walk(method):
        if isinstance(node, ast.Try):
            return True
    return False


@pytest.mark.parametrize("relpath", PROVIDER_FILES)
def test_provider_contextualize_delegates_to_base(relpath: str) -> None:
    """Each provider.contextualize must delegate to base.contextualize_batch (#1533)."""
    repo_root = Path(__file__).resolve().parents[2]
    src = (repo_root / relpath).read_text(encoding="utf-8")
    tree = ast.parse(src)
    method = _find_contextualize_method(tree)

    assert not _has_chunk_loop(method), (
        f"{relpath}::contextualize must not iterate over chunks itself; "
        "delegate to self.contextualize_batch(chunks, query) instead (#1533)."
    )
    assert not _has_try_except(method), (
        f"{relpath}::contextualize must not implement its own per-chunk "
        "try/except fallback; the base contextualize_batch already does (#1533)."
    )
    assert _calls_contextualize_batch(method), (
        f"{relpath}::contextualize must call self.contextualize_batch(chunks, query) "
        "to share the concurrent per-chunk dispatch with the base class (#1533)."
    )

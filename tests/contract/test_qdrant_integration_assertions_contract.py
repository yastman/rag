"""Contract: Qdrant integration tests must not pass with empty data (#1631).

Two read-path integration tests previously reported success without proving
that anything was actually read:

- ``tests/integration/test_qdrant_read.py`` — ``_run_qdrant_read_checks``
  returned ``True`` when the Qdrant instance had zero collections, and the
  wrapper test only port-checked Qdrant before asserting the helper. So a
  brand-new empty Qdrant gave a green test.

- ``tests/integration/test_hybrid_search_sparse.py`` — the test executed
  search queries and printed result counts but never asserted that any
  query returned at least one result. Sparse search returning zero hits
  for every probe query was reported as success.

This contract uses AST inspection to keep both files honest:

1. The wrapper ``test_qdrant_read`` must skip when collections are empty
   or the candidate collection has zero points, instead of returning
   success.
2. ``test_hybrid_search_with_sparse`` must contain an assertion that
   checks query results were non-empty (e.g. ``assert ... > 0``).
"""

from __future__ import annotations

import ast
from contextlib import suppress
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
QDRANT_READ = REPO_ROOT / "tests" / "integration" / "test_qdrant_read.py"
HYBRID_SPARSE = REPO_ROOT / "tests" / "integration" / "test_hybrid_search_sparse.py"


def _function(tree: ast.AST, name: str) -> ast.FunctionDef:
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            return node  # type: ignore[return-value]
    raise AssertionError(f"function '{name}' not found")


def _calls(tree: ast.AST, dotted: str) -> list[ast.Call]:
    """Return every Call node whose target is the given dotted name."""
    parts = dotted.split(".")
    out: list[ast.Call] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        target = node.func
        chain: list[str] = []
        while isinstance(target, ast.Attribute):
            chain.append(target.attr)
            target = target.value
        if isinstance(target, ast.Name):
            chain.append(target.id)
        if list(reversed(chain)) == parts:
            out.append(node)
    return out


def test_qdrant_read_skips_on_empty_collections() -> None:
    """``test_qdrant_read`` must call ``pytest.skip`` when no collections exist (#1631)."""
    assert QDRANT_READ.exists(), f"missing: {QDRANT_READ}"
    tree = ast.parse(QDRANT_READ.read_text(encoding="utf-8"))
    test_func = _function(tree, "test_qdrant_read")

    # Need at least two pytest.skip() calls (one for port-down, one for empty data).
    skip_calls = _calls(test_func, "pytest.skip")
    assert len(skip_calls) >= 2, (
        "test_qdrant_read must skip on BOTH 'Qdrant unreachable' AND 'no data "
        "in Qdrant' before asserting the read helper. Found "
        f"{len(skip_calls)} pytest.skip(...) call(s)."
    )

    # The skip messages must signal the empty-data path explicitly.
    skip_messages = []
    for call in skip_calls:
        if call.args and isinstance(call.args[0], (ast.Constant, ast.JoinedStr)):
            with suppress(Exception):
                skip_messages.append(ast.unparse(call.args[0]).lower())
    has_empty_data_skip = any(
        any(token in msg for token in ("collection", "data", "point", "empty"))
        for msg in skip_messages
    )
    assert has_empty_data_skip, (
        "At least one pytest.skip(...) message in test_qdrant_read must "
        "reference the missing-collection / empty-data condition. "
        f"Found messages: {skip_messages!r}"
    )


def test_qdrant_read_helper_does_not_return_true_on_empty_collections() -> None:
    """The helper must not silently succeed when ``collections.collections`` is empty (#1631)."""
    tree = ast.parse(QDRANT_READ.read_text(encoding="utf-8"))
    helper = _function(tree, "_run_qdrant_read_checks")

    # Walk every `if not collections.collections:` branch and ensure the
    # body does not unconditionally return True.
    for node in ast.walk(helper):
        if not isinstance(node, ast.If):
            continue
        try:
            test_src = ast.unparse(node.test)
        except Exception:  # pragma: no cover - defensive
            continue
        if "collections.collections" not in test_src or "not " not in test_src:
            continue
        for sub in ast.walk(node):
            if (
                isinstance(sub, ast.Return)
                and isinstance(sub.value, ast.Constant)
                and sub.value.value is True
            ):
                raise AssertionError(
                    "_run_qdrant_read_checks must not 'return True' inside the "
                    "'if not collections.collections:' branch. Either skip in "
                    "the test wrapper before calling the helper, or fail the "
                    "assertion when no collections are present."
                )


def test_hybrid_search_with_sparse_asserts_nonempty_results() -> None:
    """``test_hybrid_search_with_sparse`` must assert at least one query returned hits (#1631)."""
    assert HYBRID_SPARSE.exists(), f"missing: {HYBRID_SPARSE}"
    tree = ast.parse(HYBRID_SPARSE.read_text(encoding="utf-8"))
    test_func = _function(tree, "test_hybrid_search_with_sparse")

    # Pull every Assert in the function body and inspect their condition source.
    assert_sources: list[str] = []
    for node in ast.walk(test_func):
        if isinstance(node, ast.Assert):
            try:
                assert_sources.append(ast.unparse(node.test))
            except Exception:  # pragma: no cover - defensive
                continue

    has_nonempty_results_assertion = any(
        ("> 0" in src or ">= 1" in src or "any(" in src or " is True" in src)
        and any(tok in src.lower() for tok in ("result", "hit", "total", "found", "len(", "count"))
        for src in assert_sources
    )
    assert has_nonempty_results_assertion, (
        "test_hybrid_search_with_sparse must assert that the search path "
        "actually returned data (e.g. `assert total_results > 0`). "
        f"Found assertions: {assert_sources!r}"
    )


@pytest.mark.parametrize(
    "src,target,expected",
    [
        ("import x\nx.foo()\n", "x.foo", 1),
        ("import x\ny.foo()\nx.foo(1)\n", "x.foo", 1),
        ("import a.b\na.b.c.d()\n", "a.b.c.d", 1),
    ],
)
def test_calls_helper_walks_dotted_chain(src: str, target: str, expected: int) -> None:
    tree = ast.parse(src)
    assert len(_calls(tree, target)) == expected

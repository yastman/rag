"""Contract: live E2E cache test must FAIL on missing transitions, not skip (***REMOVED***1630).

Once ``_require_live_stack()`` confirms the RAG API and Redis responded, the
remainder of the test owns post-query assertions. Skipping when no
miss→hit transition is observed conflates "stack not available" (legitimate
skip) with "cache regression" (must fail). This contract uses AST analysis
to keep the cache test honest:

1. Inside ``test_cache_miss_then_hit_on_repeated_query``, a ``pytest.skip(...)``
   call may only appear BEFORE the live-stack preflight returns successfully
   (or as the preflight itself via ``_require_live_stack``). After the
   queries have run, the missing transition must be expressed as an
   ``assert``.

2. The test must contain an ``assert`` that requires both
   ``hits >= 1`` (or ``> 0``) and ``misses >= 1`` (or ``> 0``).
"""

from __future__ import annotations

import ast
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
TARGET = REPO_ROOT / "tests" / "e2e" / "test_core_flows_live.py"


def _function(tree: ast.AST, name: str) -> ast.AST:
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            return node
    raise AssertionError(f"function '{name}' not found in {TARGET}")


def _is_pytest_skip(call: ast.Call) -> bool:
    target = call.func
    chain: list[str] = []
    while isinstance(target, ast.Attribute):
        chain.append(target.attr)
        target = target.value
    if isinstance(target, ast.Name):
        chain.append(target.id)
    return list(reversed(chain)) == ["pytest", "skip"]


def test_target_file_exists() -> None:
    assert TARGET.exists(), f"missing target: {TARGET}"


def test_cache_test_does_not_skip_after_queries_ran() -> None:
    """No ``pytest.skip()`` is allowed after the cache queries have executed (***REMOVED***1630)."""
    tree = ast.parse(TARGET.read_text(encoding="utf-8"))
    func = _function(tree, "test_cache_miss_then_hit_on_repeated_query")
    skip_calls = [
        node
        for node in ast.walk(func)
        if isinstance(node, ast.Call) and _is_pytest_skip(node)
    ]
    assert not skip_calls, (
        "test_cache_miss_then_hit_on_repeated_query must not call "
        "pytest.skip() after the live-stack preflight. Live-stack readiness "
        "is owned by _require_live_stack(); a missing miss/hit transition "
        f"must be an assert. Found {len(skip_calls)} skip call(s) inline."
    )


def test_cache_test_asserts_miss_and_hit_observed() -> None:
    """Test must assert both ``hits`` and ``misses`` are positive (***REMOVED***1630)."""
    tree = ast.parse(TARGET.read_text(encoding="utf-8"))
    func = _function(tree, "test_cache_miss_then_hit_on_repeated_query")

    assert_sources = [
        ast.unparse(node.test)
        for node in ast.walk(func)
        if isinstance(node, ast.Assert)
    ]
    has_hits = any(
        "hits" in src and (">= 1" in src or "> 0" in src) for src in assert_sources
    )
    has_misses = any(
        "misses" in src and (">= 1" in src or "> 0" in src) for src in assert_sources
    )
    assert has_hits and has_misses, (
        "test_cache_miss_then_hit_on_repeated_query must assert both "
        "hits >= 1 and misses >= 1 (or > 0) once the live stack has "
        f"responded. Found assertions: {assert_sources!r}"
    )

"""#2802 keeps _hybrid_retrieve a thin retrieval orchestrator.

Mirrors tests/contract/test_generate_response_complexity_contract.py.
"""

from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
TARGET = ROOT / "src" / "runtime" / "pipeline" / "rag.py"
MAX_HYBRID_RETRIEVE_COMPLEXITY = 15
MAX_HELPER_COMPLEXITY = 20

_COMPLEXITY_NODES = (
    ast.If,
    ast.For,
    ast.AsyncFor,
    ast.While,
    ast.ExceptHandler,
    ast.IfExp,
    ast.BoolOp,
    ast.comprehension,
)


def _function_complexity(function: ast.AsyncFunctionDef | ast.FunctionDef) -> int:
    return 1 + sum(isinstance(node, _COMPLEXITY_NODES) for node in ast.walk(function))


def _module_functions() -> dict[str, ast.AsyncFunctionDef | ast.FunctionDef]:
    module = ast.parse(TARGET.read_text())
    return {
        node.name: node
        for node in ast.walk(module)
        if isinstance(node, (ast.AsyncFunctionDef, ast.FunctionDef))
    }


def test_hybrid_retrieve_is_thin_orchestrator() -> None:
    functions = _module_functions()
    assert "_hybrid_retrieve" in functions
    assert _function_complexity(functions["_hybrid_retrieve"]) < MAX_HYBRID_RETRIEVE_COMPLEXITY


def test_extracted_retrieval_helpers_stay_simple() -> None:
    functions = _module_functions()
    expected_helpers = [
        "_resolve_query_vectors",
        "_load_cached_query_bundle",
        "_embed_and_cache_query_vectors",
        "_compute_retrieval_filters",
        "_lookup_search_cache",
        "_ensure_sparse_vector",
        "_retrieve_with_relaxation",
        "_store_search_results",
    ]
    missing = [name for name in expected_helpers if name not in functions]
    assert not missing, f"missing extracted helpers: {missing}"
    for name in expected_helpers:
        cc = _function_complexity(functions[name])
        assert cc < MAX_HELPER_COMPLEXITY, f"{name} CC={cc} >= {MAX_HELPER_COMPLEXITY}"

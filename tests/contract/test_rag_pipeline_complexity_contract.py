"""#3030 keeps rag_pipeline below CC D(20) by extracting stage helpers."""

from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
TARGET = ROOT / "src" / "runtime" / "pipeline" / "rag.py"
MAX_RAG_PIPELINE_COMPLEXITY = 20
MAX_STAGE_HELPER_COMPLEXITY = 20

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


def _function_complexity(fn: ast.AsyncFunctionDef | ast.FunctionDef) -> int:
    return 1 + sum(isinstance(node, _COMPLEXITY_NODES) for node in ast.walk(fn))


def _file_functions(path: Path) -> dict[str, ast.AsyncFunctionDef | ast.FunctionDef]:
    module = ast.parse(path.read_text())
    return {
        node.name: node
        for node in ast.walk(module)
        if isinstance(node, (ast.AsyncFunctionDef, ast.FunctionDef))
    }


def test_rag_pipeline_complexity_below_d() -> None:
    """rag_pipeline CC must be below D(20) after #3030 stage extraction."""
    functions = _file_functions(TARGET)
    assert "rag_pipeline" in functions, "rag_pipeline not found in rag.py"
    cc = _function_complexity(functions["rag_pipeline"])
    assert cc < MAX_RAG_PIPELINE_COMPLEXITY, (
        f"rag_pipeline CC={cc} >= {MAX_RAG_PIPELINE_COMPLEXITY}. "
        f"Extract stage helpers to reduce complexity (#3030)."
    )


def test_extracted_stage_helpers_present_and_simple() -> None:
    """Stage helpers extracted in #3030 must exist and stay under CC 20."""
    functions = _file_functions(TARGET)
    expected = [
        "_run_rerank_and_trim",
        "_try_build_result",
    ]
    missing = [name for name in expected if name not in functions]
    assert not missing, f"Missing extracted stage helpers: {missing}"
    for name in expected:
        cc = _function_complexity(functions[name])
        assert cc < MAX_STAGE_HELPER_COMPLEXITY, f"{name} CC={cc} >= {MAX_STAGE_HELPER_COMPLEXITY}"

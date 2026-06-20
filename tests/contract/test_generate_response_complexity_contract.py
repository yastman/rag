"""CORE-011 keeps Telegram generate_response as a thin wrapper."""

from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
TARGET = ROOT / "telegram_bot" / "services" / "generate_response.py"
MAX_GENERATE_RESPONSE_COMPLEXITY = 20
MAX_STREAMING_STAGE_COMPLEXITY = 25  # #2926: _generate_streaming_response decomposed

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


def test_generate_response_is_thin_wrapper() -> None:
    module = ast.parse(TARGET.read_text())
    functions = [
        node
        for node in module.body
        if isinstance(node, ast.AsyncFunctionDef) and node.name == "generate_response"
    ]
    assert len(functions) == 1
    assert _function_complexity(functions[0]) < MAX_GENERATE_RESPONSE_COMPLEXITY


def test_streaming_stages_within_complexity_budget() -> None:
    """#2926: each stage helper extracted from _generate_streaming_response stays under CC 25."""
    module = ast.parse(TARGET.read_text())
    stage_names = {
        "_generate_streaming_response",
        "_prepare_streaming_context",
        "_run_stream_with_recovery",
        "_emit_generation_span",
        "_compute_latency_metrics",
        "_build_generation_signal",
    }
    found = {
        node.name: _function_complexity(node)
        for node in ast.walk(module)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name in stage_names
    }
    missing = stage_names - found.keys()
    assert not missing, f"Stage functions not found: {missing}"
    over_budget = {name: cc for name, cc in found.items() if cc >= MAX_STREAMING_STAGE_COMPLEXITY}
    assert not over_budget, (
        f"Stage functions over CC {MAX_STREAMING_STAGE_COMPLEXITY}: {over_budget}"
    )

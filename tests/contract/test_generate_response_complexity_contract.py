"""CORE-011 keeps Telegram generate_response as a thin wrapper."""

from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
TARGET = ROOT / "telegram_bot" / "services" / "generate_response.py"
# #3034: stage helpers live in split modules after generate_response.py decomposition
_STREAMING_CONTEXT = ROOT / "telegram_bot" / "services" / "_streaming_context.py"
_STREAM_EXECUTION = ROOT / "telegram_bot" / "services" / "_stream_execution.py"
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


def _collect_functions(path: Path) -> dict[str, int]:
    return {
        node.name: _function_complexity(node)
        for node in ast.walk(ast.parse(path.read_text()))
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }


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
    """#2926/#3034: stage helpers stay under CC 25 across split modules.

    After #3034 decomposition:
    - _generate_streaming_response, _compute_latency_metrics, _build_generation_signal
      remain in generate_response.py
    - prepare_streaming_context lives in _streaming_context.py
    - run_stream_with_recovery lives in _stream_execution.py
    - _emit_generation_span was dropped when Langfuse was removed
    """
    all_funcs: dict[str, int] = {}
    all_funcs.update(_collect_functions(TARGET))
    all_funcs.update(_collect_functions(_STREAMING_CONTEXT))
    all_funcs.update(_collect_functions(_STREAM_EXECUTION))

    stage_names = {
        "_generate_streaming_response",
        "prepare_streaming_context",
        "run_stream_with_recovery",
        "_compute_latency_metrics",
        "_build_generation_signal",
    }
    found = {name: all_funcs[name] for name in stage_names if name in all_funcs}
    missing = stage_names - found.keys()
    assert not missing, f"Stage functions not found: {missing}"
    over_budget = {name: cc for name, cc in found.items() if cc >= MAX_STREAMING_STAGE_COMPLEXITY}
    assert not over_budget, (
        f"Stage functions over CC {MAX_STREAMING_STAGE_COMPLEXITY}: {over_budget}"
    )

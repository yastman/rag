"""CORE-011 keeps Telegram generate_response as a thin wrapper."""

from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
TARGET = ROOT / "telegram_bot" / "services" / "generate_response.py"
MAX_GENERATE_RESPONSE_COMPLEXITY = 20


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

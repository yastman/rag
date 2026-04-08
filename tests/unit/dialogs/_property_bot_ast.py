"""Lightweight AST helpers for PropertyBot contract tests."""

from __future__ import annotations

import ast
from functools import lru_cache
from pathlib import Path


@lru_cache(maxsize=1)
def _property_bot_class() -> ast.ClassDef:
    tree = ast.parse(Path("telegram_bot/bot.py").read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name == "PropertyBot":
            return node
    raise AssertionError("PropertyBot class not found in telegram_bot/bot.py")


def get_property_bot_method(name: str) -> ast.AsyncFunctionDef:
    for node in _property_bot_class().body:
        if isinstance(node, ast.AsyncFunctionDef) and node.name == name:
            return node
    raise AssertionError(f"PropertyBot.{name} not found")


def get_parameter_names(method: ast.AsyncFunctionDef) -> list[str]:
    return [arg.arg for arg in method.args.args]


def get_default_map(method: ast.AsyncFunctionDef) -> dict[str, object]:
    positional_args = method.args.args
    defaults = method.args.defaults
    start = len(positional_args) - len(defaults)
    default_map = {
        positional_args[start + index].arg: ast.literal_eval(default)
        for index, default in enumerate(defaults)
    }
    for arg, default in zip(method.args.kwonlyargs, method.args.kw_defaults, strict=False):
        if default is not None:
            default_map[arg.arg] = ast.literal_eval(default)
    return default_map

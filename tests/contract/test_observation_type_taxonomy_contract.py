"""Observation-type taxonomy contract (#2216 / Epic F).

Langfuse was removed in #3008 / #3049. The ``@observe(as_type=...)``
taxonomy that this file previously enforced is no longer applicable.

This contract now guards the **inverse**: no Langfuse ``@observe``
decorators must re-appear in agent tools or guard nodes (#3085).
If Langfuse is ever re-introduced, re-add the as_type taxonomy checks
from the original contract (see git history for the full spec).
"""

from __future__ import annotations

import ast
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]

_SCAN_DIRS = (
    REPO_ROOT / "telegram_bot" / "agents",
    REPO_ROOT / "src" / "runtime" / "graph" / "nodes",
)


def _collect_observe_decorators() -> list[str]:
    """Return list of files that still contain @observe decorators."""
    hits: list[str] = []
    for root in _SCAN_DIRS:
        if not root.exists():
            continue
        for py_file in root.rglob("*.py"):
            if "/tests/" in str(py_file) or "/__pycache__/" in str(py_file):
                continue
            try:
                tree = ast.parse(py_file.read_text(encoding="utf-8"))
            except SyntaxError:
                continue
            for node in ast.walk(tree):
                if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                    continue
                for dec in node.decorator_list:
                    if not isinstance(dec, ast.Call):
                        continue
                    func = dec.func
                    name = (
                        func.id
                        if isinstance(func, ast.Name)
                        else func.attr
                        if isinstance(func, ast.Attribute)
                        else None
                    )
                    if name == "observe":
                        hits.append(str(py_file.relative_to(REPO_ROOT)))
    return hits


def test_no_langfuse_observe_decorators_in_agents_or_nodes() -> None:
    """Langfuse @observe was removed in #3008/#3049 (#3085).

    Guard against accidental re-introduction in agent tools or guard nodes.
    """
    hits = _collect_observe_decorators()
    assert not hits, (
        "Langfuse @observe decorators were removed in #3008/#3049 but were found again "
        f"in: {hits}. Either re-add the full Langfuse as_type taxonomy contract "
        "or remove the decorator."
    )


def _collect_bot_py_observe_decorators() -> list[str]:
    """Return observe decorator names still present in bot.py."""
    bot_py = REPO_ROOT / "telegram_bot" / "bot.py"
    hits: list[str] = []
    tree = ast.parse(bot_py.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            continue
        for dec in node.decorator_list:
            if not isinstance(dec, ast.Call):
                continue
            func = dec.func
            name = (
                func.id
                if isinstance(func, ast.Name)
                else func.attr
                if isinstance(func, ast.Attribute)
                else None
            )
            if name == "observe":
                hits.append(getattr(node, "name", "<unknown>"))
    return hits


def test_no_langfuse_observe_decorators_in_bot_py() -> None:
    """Langfuse @observe was removed in #3008/#3049 (#3085).

    Guard against accidental re-introduction in bot.py agent entry points.
    """
    hits = _collect_bot_py_observe_decorators()
    assert not hits, (
        "Langfuse @observe decorators were removed in #3008/#3049 but were found again "
        f"in bot.py on: {hits}. Either re-add the full Langfuse as_type taxonomy "
        "contract or remove the decorator."
    )

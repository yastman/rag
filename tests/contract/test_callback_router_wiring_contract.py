"""Contract test: every create_*_router() factory in handlers/ must be wired into bot.py.

TDD RED:  fails while service_callbacks.py / results_callbacks.py / favorites_callbacks.py exist
          and their factories are NOT passed to dp.include_router() in bot.py.
TDD GREEN: passes after orphaned modules are deleted (Path A) or wired (Path B).

Approach:
  - Walk telegram_bot/handlers/*.py AST → collect every ``def create_*_router(`` name + source file.
  - Walk telegram_bot/bot.py AST → collect every ``include_router(`` argument expression that
    matches a call to one of those factories.
  - For each factory whose call is absent from bot.py: FAIL with a descriptive message.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path


# ---------------------------------------------------------------------------
# Repository root detection
# ---------------------------------------------------------------------------
_REPO_ROOT = Path(__file__).parent.parent.parent  # tests/contract/ -> repo root


def _handlers_dir() -> Path:
    return _REPO_ROOT / "telegram_bot" / "handlers"


def _bot_py() -> Path:
    return _REPO_ROOT / "telegram_bot" / "bot.py"


# ---------------------------------------------------------------------------
# AST helpers
# ---------------------------------------------------------------------------


def _collect_router_factories(handlers_dir: Path) -> dict[str, Path]:
    """Return {factory_name: source_file} for every ``def create_*_router(`` in handlers/."""
    factories: dict[str, Path] = {}
    for py_file in sorted(handlers_dir.glob("*.py")):
        if py_file.name.startswith("_"):
            continue  # skip __init__ etc.
        try:
            tree = ast.parse(py_file.read_text(encoding="utf-8"))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and re.match(r"create_.+_router$", node.name):
                factories[node.name] = py_file
    return factories


def _collect_included_router_calls(bot_py: Path) -> set[str]:
    """Return the set of factory function names called inside dp.include_router(…) in bot.py."""
    tree = ast.parse(bot_py.read_text(encoding="utf-8"))
    included: set[str] = set()
    for node in ast.walk(tree):
        # Match: something.include_router(create_xyz_router())
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "include_router"
        ):
            for arg in node.args:
                # Positional call expression: include_router(create_phone_router())
                if isinstance(arg, ast.Call):
                    func = arg.func
                    if isinstance(func, ast.Name):
                        included.add(func.id)
                    elif isinstance(func, ast.Attribute):
                        included.add(func.attr)
    return included


# ---------------------------------------------------------------------------
# Contract test
# ---------------------------------------------------------------------------


def test_all_router_factories_are_wired_into_startup() -> None:
    """Every create_*_router() defined in handlers/ must be included in bot.py startup."""
    handlers_dir = _handlers_dir()
    bot_py = _bot_py()

    assert handlers_dir.is_dir(), f"handlers dir not found: {handlers_dir}"
    assert bot_py.is_file(), f"bot.py not found: {bot_py}"

    factories = _collect_router_factories(handlers_dir)
    included = _collect_included_router_calls(bot_py)

    orphans: list[str] = []
    for name, src in sorted(factories.items()):
        if name not in included:
            orphans.append(f"  {name}()  →  {src.relative_to(_REPO_ROOT)}")

    assert not orphans, (
        "The following router factories are defined in handlers/ but never passed to "
        "dp.include_router() in bot.py — either wire them or remove the dead modules:\n"
        + "\n".join(orphans)
    )

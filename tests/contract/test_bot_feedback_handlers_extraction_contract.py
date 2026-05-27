"""Contract: feedback handlers live in ``telegram_bot/_bot_feedback_handlers.py``.

PR-9a of the Slice 2 decomposition plan
(``docs/engineering/bot-decomposition-plan-2026-05-27.md``, parent
#1265 / child #2048). Feedback callbacks are the first vertical of
PropertyBot's callback layer to move off the god-object — keeping the
class methods as thin wrappers preserves the aiogram dispatcher
registration sites and the existing ``tests/unit/test_bot_handlers.py``
suite.

The contract pins:

1. ``telegram_bot._bot_feedback_handlers`` exposes the three module-level
   helpers ``handle_feedback`` / ``handle_feedback_reason`` /
   ``clear_feedback_confirmation_later`` (all async).
2. The module's top-level imports stay narrow — no aiogram /
   langgraph / qdrant_client / fastapi at module scope.
3. ``PropertyBot.handle_feedback`` / ``handle_feedback_reason`` /
   ``_clear_feedback_confirmation_later`` delegate to the module-level
   helpers (verified statically via AST).
"""

from __future__ import annotations

import ast
import importlib
import inspect
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
MODULE_NAME = "telegram_bot._bot_feedback_handlers"
MODULE_PATH = REPO_ROOT / "telegram_bot" / "_bot_feedback_handlers.py"
BOT_PATH = REPO_ROOT / "telegram_bot" / "bot.py"

FORBIDDEN_TOP_IMPORTS = {
    "aiogram",
    "langgraph",
    "langchain",
    "qdrant_client",
    "fastapi",
}

REQUIRED_HELPERS = (
    "handle_feedback",
    "handle_feedback_reason",
    "clear_feedback_confirmation_later",
)


def _parse(path: Path) -> ast.Module:
    return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def test_module_exists_and_exports_required_helpers() -> None:
    assert MODULE_PATH.is_file(), f"{MODULE_PATH.relative_to(REPO_ROOT)} must exist (#2048 PR-9a)."
    module = importlib.import_module(MODULE_NAME)
    for name in REQUIRED_HELPERS:
        assert hasattr(module, name), f"{MODULE_NAME} must export {name}."
        assert inspect.iscoroutinefunction(getattr(module, name)), (
            f"{MODULE_NAME}.{name} must be async (`async def`)."
        )


def test_module_has_no_heavy_top_imports() -> None:
    """Feedback helpers must stay cheap to import — no aiogram /
    langchain / langgraph / qdrant_client / fastapi at module scope.
    Lazy-import inside function bodies if needed."""
    tree = _parse(MODULE_PATH)
    offenders: list[str] = []
    for node in ast.iter_child_nodes(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                top = alias.name.split(".", 1)[0]
                if top in FORBIDDEN_TOP_IMPORTS:
                    offenders.append(alias.name)
        elif isinstance(node, ast.ImportFrom):
            module = (node.module or "").split(".", 1)[0]
            if module in FORBIDDEN_TOP_IMPORTS:
                offenders.append(node.module or "")
    assert not offenders, (
        f"{MODULE_PATH.relative_to(REPO_ROOT)} forbidden module-scope imports: {offenders}."
    )


def _find_class_method(tree: ast.Module, class_name: str, method_name: str) -> ast.AsyncFunctionDef:
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == class_name:
            for item in node.body:
                if isinstance(item, ast.AsyncFunctionDef) and item.name == method_name:
                    return item
    raise AssertionError(f"PropertyBot.{method_name} not found in bot.py")


def _method_awaits_helper(method: ast.AsyncFunctionDef, helper_name: str) -> bool:
    """True iff the method body awaits a call to ``helper_name``.

    Accepted shapes:
      * ``await _bot_feedback_handlers.HELPER(...)``
      * ``await HELPER(...)`` (when imported by name)
    """
    for node in ast.walk(method):
        if not isinstance(node, ast.Await):
            continue
        call = node.value
        if not isinstance(call, ast.Call):
            continue
        func = call.func
        if isinstance(func, ast.Name) and func.id == helper_name:
            return True
        if isinstance(func, ast.Attribute) and func.attr == helper_name:
            return True
    return False


def test_handle_feedback_method_delegates() -> None:
    tree = _parse(BOT_PATH)
    method = _find_class_method(tree, "PropertyBot", "handle_feedback")
    assert _method_awaits_helper(method, "handle_feedback"), (
        "PropertyBot.handle_feedback must delegate to "
        "telegram_bot._bot_feedback_handlers.handle_feedback."
    )


def test_handle_feedback_reason_method_delegates() -> None:
    tree = _parse(BOT_PATH)
    method = _find_class_method(tree, "PropertyBot", "handle_feedback_reason")
    assert _method_awaits_helper(method, "handle_feedback_reason"), (
        "PropertyBot.handle_feedback_reason must delegate to "
        "telegram_bot._bot_feedback_handlers.handle_feedback_reason."
    )


def test_clear_feedback_confirmation_method_delegates() -> None:
    tree = _parse(BOT_PATH)
    method = _find_class_method(tree, "PropertyBot", "_clear_feedback_confirmation_later")
    assert _method_awaits_helper(method, "clear_feedback_confirmation_later"), (
        "PropertyBot._clear_feedback_confirmation_later must delegate to "
        "telegram_bot._bot_feedback_handlers.clear_feedback_confirmation_later."
    )

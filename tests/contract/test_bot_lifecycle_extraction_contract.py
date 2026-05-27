"""Contract: lifecycle helpers live in ``telegram_bot/_bot_lifecycle.py`` (#2048).

PR-8 of the Slice 2 decomposition plan
(``docs/engineering/bot-decomposition-plan-2026-05-27.md``) extracts the
``_warmup_bge`` and ``_polling_lock_heartbeat_tick`` helpers out of
``PropertyBot`` so that:

* their bodies can be imported and unit-tested without instantiating the
  full bot (no aiogram / langgraph / qdrant_client cost),
* ``telegram_bot/bot.py`` shrinks toward a thin facade,
* the import-graph invariants from Slice 1 (no aiogram / langgraph /
  qdrant_client / fastapi at module scope of an ``_bot_*.py`` file) are
  preserved.

The contract pins three things:

1. ``telegram_bot._bot_lifecycle`` exposes the module-level helpers
   ``warmup_bge_pool`` and ``polling_lock_heartbeat_tick``.
2. ``PropertyBot._warmup_bge`` and ``PropertyBot._polling_lock_heartbeat_tick``
   delegate to those helpers (verified statically — the method body must
   ``await`` the module-level helper).
3. ``telegram_bot/_bot_lifecycle.py`` does not import aiogram, langgraph,
   langchain, qdrant_client or fastapi at module scope.

Re-introducing inline lifecycle code on ``PropertyBot`` (or pulling a
heavy import into ``_bot_lifecycle.py``) trips this contract at CI time.
"""

from __future__ import annotations

import ast
import importlib
import inspect
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
LIFECYCLE_MODULE = "telegram_bot._bot_lifecycle"
LIFECYCLE_PATH = REPO_ROOT / "telegram_bot" / "_bot_lifecycle.py"
BOT_PATH = REPO_ROOT / "telegram_bot" / "bot.py"

# Forbidden module-scope imports — these belong to the heavy bot stack and
# must not creep into a pure helper module.
FORBIDDEN_TOP_IMPORTS = {
    "aiogram",
    "langgraph",
    "langchain",
    "qdrant_client",
    "fastapi",
}

# Public surface the module must export.
REQUIRED_HELPERS = ("warmup_bge_pool", "polling_lock_heartbeat_tick")


def _parse(path: Path) -> ast.Module:
    return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def test_lifecycle_module_exists_and_exports_helpers() -> None:
    assert LIFECYCLE_PATH.is_file(), (
        f"{LIFECYCLE_PATH.relative_to(REPO_ROOT)} must exist (#2048 PR-8)."
    )
    module = importlib.import_module(LIFECYCLE_MODULE)
    missing = [name for name in REQUIRED_HELPERS if not hasattr(module, name)]
    assert not missing, (
        f"{LIFECYCLE_MODULE} must export {REQUIRED_HELPERS}; "
        f"missing: {missing}"
    )
    for name in REQUIRED_HELPERS:
        assert inspect.iscoroutinefunction(getattr(module, name)), (
            f"{LIFECYCLE_MODULE}.{name} must be async (`async def`)."
        )


def test_lifecycle_module_has_no_heavy_imports() -> None:
    tree = _parse(LIFECYCLE_PATH)
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
        f"{LIFECYCLE_PATH.relative_to(REPO_ROOT)} has forbidden module-scope "
        f"imports: {offenders}. Move them into function bodies (lazy import) "
        f"or keep the helpers stdlib-only."
    )


def _find_class_method(tree: ast.Module, class_name: str, method_name: str) -> ast.AsyncFunctionDef:
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == class_name:
            for item in node.body:
                if isinstance(item, ast.AsyncFunctionDef) and item.name == method_name:
                    return item
    raise AssertionError(f"PropertyBot.{method_name} not found in bot.py")


def _method_awaits_lifecycle_helper(method: ast.AsyncFunctionDef, helper_name: str) -> bool:
    """Return True iff the method body awaits a call to the named helper.

    Accepted shapes:
      * ``await _bot_lifecycle.HELPER(...)`` — preferred form.
      * ``await HELPER(...)`` — when the helper was imported by name.
    """
    for node in ast.walk(method):
        if not isinstance(node, ast.Await):
            continue
        call = node.value
        if not isinstance(call, ast.Call):
            continue
        func = call.func
        # Bare-name import: ``await polling_lock_heartbeat_tick(...)``.
        if isinstance(func, ast.Name) and func.id == helper_name:
            return True
        # Attribute access: ``await _bot_lifecycle.polling_lock_heartbeat_tick(...)``.
        if isinstance(func, ast.Attribute) and func.attr == helper_name:
            return True
    return False


def test_warmup_bge_method_delegates_to_helper() -> None:
    tree = _parse(BOT_PATH)
    method = _find_class_method(tree, "PropertyBot", "_warmup_bge")
    assert _method_awaits_lifecycle_helper(method, "warmup_bge_pool"), (
        "PropertyBot._warmup_bge must delegate to "
        "telegram_bot._bot_lifecycle.warmup_bge_pool. Move the body into the "
        "module-level helper and have the method await it."
    )


def test_polling_lock_heartbeat_method_delegates_to_helper() -> None:
    tree = _parse(BOT_PATH)
    method = _find_class_method(tree, "PropertyBot", "_polling_lock_heartbeat_tick")
    assert _method_awaits_lifecycle_helper(method, "polling_lock_heartbeat_tick"), (
        "PropertyBot._polling_lock_heartbeat_tick must delegate to "
        "telegram_bot._bot_lifecycle.polling_lock_heartbeat_tick. Move the "
        "body into the module-level helper and have the method await it."
    )

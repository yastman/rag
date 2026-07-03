"""Contract: clearcache handler lives in ``telegram_bot/handlers/bot_crm_callbacks.py``.

Slice #2980: decompose PropertyBot god-object into per-feature handlers.
Pins:

1. ``telegram_bot.handlers.bot_crm_callbacks`` exports ``handle_clearcache_callback``
   (async).
2. The module has no heavy top-level imports (aiogram / langgraph /
   qdrant_client / fastapi).
3. ``PropertyBot.handle_clearcache_callback`` delegates to the module-level
   helper (verified statically via AST).
"""

from __future__ import annotations

import ast
import importlib
import inspect
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
MODULE_NAME = "telegram_bot.handlers.bot_crm_callbacks"
MODULE_PATH = REPO_ROOT / "telegram_bot" / "handlers" / "bot_crm_callbacks.py"
BOT_PATH = REPO_ROOT / "telegram_bot" / "bot.py"

FORBIDDEN_TOP_IMPORTS = {
    "aiogram",
    "langgraph",
    "langchain",
    "qdrant_client",
    "fastapi",
}

REQUIRED_HELPERS = ("handle_clearcache_callback",)


def _parse(path: Path) -> ast.Module:
    return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def test_module_exists_and_exports_required_helpers() -> None:
    assert MODULE_PATH.is_file(), f"{MODULE_PATH.relative_to(REPO_ROOT)} must exist (#2980)."
    module = importlib.import_module(MODULE_NAME)
    for name in REQUIRED_HELPERS:
        assert hasattr(module, name), f"{MODULE_NAME} must export {name}."
        assert inspect.iscoroutinefunction(getattr(module, name)), (
            f"{MODULE_NAME}.{name} must be async (`async def`)."
        )


def test_module_has_no_heavy_top_imports() -> None:
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


def test_handle_clearcache_method_delegates() -> None:
    tree = _parse(BOT_PATH)
    method = _find_class_method(tree, "PropertyBot", "handle_clearcache_callback")
    assert _method_awaits_helper(method, "handle_clearcache_callback"), (
        "PropertyBot.handle_clearcache_callback must delegate to "
        "telegram_bot.handlers.bot_crm_callbacks.handle_clearcache_callback."
    )


def test_per_feature_routers_exist() -> None:
    """All per-feature handler router modules named in handlers/README.md must exist."""
    expected = [
        "crm_callbacks",
        "favorites_callbacks",
        "results_callbacks",
        "service_callbacks",
    ]
    handlers_dir = REPO_ROOT / "telegram_bot" / "handlers"
    for name in expected:
        path = handlers_dir / f"{name}.py"
        assert path.is_file(), f"telegram_bot/handlers/{name}.py must exist (#2980)."


def test_per_feature_routers_export_factory() -> None:
    """Each per-feature router module must define a ``create_*_router`` function."""
    factories = {
        "crm_callbacks": "create_crm_router",
        "favorites_callbacks": "create_favorites_router",
        "results_callbacks": "create_results_router",
        "service_callbacks": "create_service_router",
    }
    handlers_dir = REPO_ROOT / "telegram_bot" / "handlers"
    for mod_file, fn_name in factories.items():
        source = (handlers_dir / f"{mod_file}.py").read_text(encoding="utf-8")
        assert f"def {fn_name}" in source, (
            f"telegram_bot/handlers/{mod_file}.py must define {fn_name} (#2980)."
        )


def test_register_handlers_uses_per_feature_routers() -> None:
    """``_register_handlers`` in bot.py must include the per-feature routers."""
    source = BOT_PATH.read_text(encoding="utf-8")
    for name in (
        "create_crm_router",
        "create_service_router",
        "create_favorites_router",
        "create_results_router",
    ):
        assert name in source, f"bot.py _register_handlers must import and use {name} (#2980)."

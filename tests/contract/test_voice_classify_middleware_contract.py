"""Contract: ClassifyMiddleware lives in ``telegram_bot/graph/middleware/classify.py``.

Slice 2.5 of the voice-path migration to ``create_agent`` (ADR-0010,
parent #1535 / #2051). The middleware is the SDK-native counterpart of
:func:`telegram_bot.graph.nodes.classify.classify_node`. It runs once
at the start of the agent invocation, classifies the user query and
short-circuits the agent loop for ``CHITCHAT`` / ``OFF_TOPIC`` types
with a canned response — exactly as the legacy ``classify_node``
routes those types past ``cache_check`` straight to ``respond``.
"""

from __future__ import annotations

import ast
import importlib
import inspect
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
MODULE_NAME = "telegram_bot.graph.middleware.classify"
MODULE_PATH = REPO_ROOT / "telegram_bot" / "graph" / "middleware" / "classify.py"
PKG_INIT_PATH = REPO_ROOT / "telegram_bot" / "graph" / "middleware" / "__init__.py"

FORBIDDEN_TOP_IMPORTS = {
    "aiogram",
    "qdrant_client",
    "fastapi",
}
ALLOWED_LANGGRAPH_SUBPACKAGES = {"langgraph.runtime"}


def _parse(path: Path) -> ast.Module:
    return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def test_module_exists_and_exports_required_symbols() -> None:
    assert MODULE_PATH.is_file(), (
        f"{MODULE_PATH.relative_to(REPO_ROOT)} must exist (#2051 Slice 2.5)."
    )
    module = importlib.import_module(MODULE_NAME)
    for name in ("ClassifyMiddleware", "_ClassifyAwareState"):
        assert hasattr(module, name), f"{MODULE_NAME} must export {name}."


def test_middleware_subclasses_AgentMiddleware() -> None:
    from langchain.agents.middleware import AgentMiddleware

    module = importlib.import_module(MODULE_NAME)
    cls = module.ClassifyMiddleware
    assert inspect.isclass(cls)
    assert issubclass(cls, AgentMiddleware)


def test_middleware_declares_before_agent_hook() -> None:
    module = importlib.import_module(MODULE_NAME)
    cls = module.ClassifyMiddleware
    member = inspect.getattr_static(cls, "before_agent", None)
    assert member is not None, (
        "ClassifyMiddleware must define before_agent (Slice 2.5 single-shot classify)."
    )


def test_before_agent_is_hook_config_with_jump_to_end() -> None:
    """`@hook_config(can_jump_to=['end'])` is required so the SDK
    permits the canned-response short-circuit."""
    tree = _parse(MODULE_PATH)
    found = False
    for node in ast.walk(tree):
        if not (
            isinstance(node, (ast.AsyncFunctionDef, ast.FunctionDef))
            and node.name == "before_agent"
        ):
            continue
        for deco in node.decorator_list:
            if not (isinstance(deco, ast.Call) and isinstance(deco.func, ast.Name)):
                continue
            if deco.func.id != "hook_config":
                continue
            for kw in deco.keywords:
                if kw.arg != "can_jump_to":
                    continue
                if isinstance(kw.value, ast.List) and any(
                    isinstance(elt, ast.Constant) and elt.value == "end" for elt in kw.value.elts
                ):
                    found = True
    assert found, (
        "ClassifyMiddleware.before_agent must be decorated with "
        "@hook_config(can_jump_to=['end']) — the canned-response path needs jump_to='end'."
    )


def test_module_has_no_forbidden_top_imports() -> None:
    tree = _parse(MODULE_PATH)
    offenders: list[str] = []
    for node in ast.iter_child_nodes(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                top = alias.name.split(".", 1)[0]
                if top in FORBIDDEN_TOP_IMPORTS:
                    offenders.append(alias.name)
                if top == "langgraph" and alias.name not in ALLOWED_LANGGRAPH_SUBPACKAGES:
                    offenders.append(alias.name)
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            top = module.split(".", 1)[0]
            if top in FORBIDDEN_TOP_IMPORTS:
                offenders.append(module)
            if top == "langgraph" and module not in ALLOWED_LANGGRAPH_SUBPACKAGES:
                offenders.append(module)
    assert not offenders, (
        f"{MODULE_PATH.relative_to(REPO_ROOT)} forbidden module-scope imports: {offenders}."
    )


def test_package_init_re_exports_middleware() -> None:
    init_text = PKG_INIT_PATH.read_text(encoding="utf-8")
    assert "ClassifyMiddleware" in init_text, (
        "telegram_bot/graph/middleware/__init__.py must re-export ClassifyMiddleware."
    )


def test_state_schema_has_query_type_field() -> None:
    module = importlib.import_module(MODULE_NAME)
    schema = module._ClassifyAwareState
    assert "query_type" in getattr(schema, "__annotations__", {})

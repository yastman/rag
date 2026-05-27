"""Contract: SemanticCacheMiddleware lives in ``telegram_bot/graph/middleware/cache.py``.

Slice 2 of the voice-path migration to ``create_agent`` (ADR-0010, parent
#1535 / #2051). The middleware is the SDK-native counterpart of
:func:`telegram_bot.graph.nodes.cache.cache_check_node` and
:func:`telegram_bot.graph.nodes.cache.cache_store_node`.

The contract pins:

1. ``telegram_bot.graph.middleware.cache`` exposes
   ``SemanticCacheMiddleware`` and the local state schema
   ``_CacheAwareState`` it ships with.
2. ``SemanticCacheMiddleware`` is a subclass of
   :class:`langchain.agents.middleware.AgentMiddleware`.
3. The class declares the two SDK-native hooks required for the
   cache-hit short-circuit: ``abefore_agent`` (runs once at the start;
   may ``jump_to=end`` on cache HIT) and ``aafter_agent`` (runs once at
   the end; persists the agent's final response).
4. ``abefore_agent`` is decorated with ``@hook_config(can_jump_to=["end"])``
   so the SDK knows the hook may short-circuit.
5. The constructor takes ``cache`` and ``embeddings`` keyword-only — no
   reading from ``runtime.context`` for these heavy collaborators, so
   the middleware stays unit-testable in isolation.
6. The module does not import aiogram / langgraph (beyond
   ``langgraph.runtime``) / qdrant_client / fastapi at module scope.
   Heavy imports must stay inside function bodies if needed.
7. ``__init__.py`` re-exports ``SemanticCacheMiddleware`` so callers
   can ``from telegram_bot.graph.middleware import SemanticCacheMiddleware``.
"""

from __future__ import annotations

import ast
import importlib
import inspect
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
MODULE_NAME = "telegram_bot.graph.middleware.cache"
MODULE_PATH = REPO_ROOT / "telegram_bot" / "graph" / "middleware" / "cache.py"
PKG_INIT_PATH = REPO_ROOT / "telegram_bot" / "graph" / "middleware" / "__init__.py"

FORBIDDEN_TOP_IMPORTS = {
    "aiogram",
    "qdrant_client",
    "fastapi",
}
# ``langgraph.runtime`` is allowed (Runtime is the SDK type-hint), but other
# langgraph subpackages should stay out of module scope.
ALLOWED_LANGGRAPH_SUBPACKAGES = {"langgraph.runtime"}


def _parse(path: Path) -> ast.Module:
    return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def test_cache_middleware_module_exists_and_exports_required_symbols() -> None:
    assert MODULE_PATH.is_file(), (
        f"{MODULE_PATH.relative_to(REPO_ROOT)} must exist (#2051 Slice 2)."
    )
    module = importlib.import_module(MODULE_NAME)
    for name in ("SemanticCacheMiddleware", "_CacheAwareState"):
        assert hasattr(module, name), f"{MODULE_NAME} must export {name}."


def test_cache_middleware_subclasses_AgentMiddleware() -> None:
    from langchain.agents.middleware import AgentMiddleware

    module = importlib.import_module(MODULE_NAME)
    cls = module.SemanticCacheMiddleware
    assert inspect.isclass(cls)
    assert issubclass(cls, AgentMiddleware), (
        "SemanticCacheMiddleware must subclass langchain.agents.middleware.AgentMiddleware"
    )


def test_middleware_declares_required_hooks() -> None:
    module = importlib.import_module(MODULE_NAME)
    cls = module.SemanticCacheMiddleware
    for hook in ("abefore_agent", "aafter_agent"):
        member = inspect.getattr_static(cls, hook, None)
        assert member is not None, (
            f"SemanticCacheMiddleware must define {hook} (Slice 2 cache lifecycle)."
        )


def test_abefore_agent_is_hook_config_with_jump_to_end() -> None:
    """``@hook_config(can_jump_to=['end'])`` is required so the SDK
    permits the cache-hit short-circuit. Detect via AST so the test
    does not depend on runtime decorator metadata."""
    tree = _parse(MODULE_PATH)
    found = False
    for node in ast.walk(tree):
        if not (
            isinstance(node, (ast.AsyncFunctionDef, ast.FunctionDef))
            and node.name == "abefore_agent"
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
                    isinstance(elt, ast.Constant) and elt.value == "end"
                    for elt in kw.value.elts
                ):
                    found = True
    assert found, (
        "SemanticCacheMiddleware.abefore_agent must be decorated with "
        "@hook_config(can_jump_to=['end']) so the SDK allows jump_to='end' on cache HIT."
    )


def test_constructor_takes_cache_and_embeddings_keyword_only() -> None:
    module = importlib.import_module(MODULE_NAME)
    cls = module.SemanticCacheMiddleware
    sig = inspect.signature(cls.__init__)
    params = sig.parameters
    for name in ("cache", "embeddings"):
        assert name in params, (
            f"SemanticCacheMiddleware.__init__ must accept '{name}' (keyword-only)"
        )
        assert params[name].kind == inspect.Parameter.KEYWORD_ONLY, (
            f"'{name}' must be KEYWORD_ONLY for explicit dependency injection"
        )


def test_cache_module_has_no_forbidden_top_imports() -> None:
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
        f"{MODULE_PATH.relative_to(REPO_ROOT)} has forbidden module-scope imports: "
        f"{offenders}. Lazy-import inside function bodies if needed."
    )


def test_package_init_re_exports_cache_middleware() -> None:
    init_text = PKG_INIT_PATH.read_text(encoding="utf-8")
    assert "SemanticCacheMiddleware" in init_text, (
        "telegram_bot/graph/middleware/__init__.py must re-export "
        "SemanticCacheMiddleware so callers can do "
        "`from telegram_bot.graph.middleware import SemanticCacheMiddleware`."
    )


def test_state_schema_has_required_fields() -> None:
    """``_CacheAwareState`` must declare the cache fields the hooks
    write so the SDK's state-merge layer accepts them. NotRequired
    keeps backward-compatibility with checkpoints lacking these fields.
    """
    module = importlib.import_module(MODULE_NAME)
    schema = module._CacheAwareState
    annotations = getattr(schema, "__annotations__", {})
    for field in ("query_type", "cache_hit", "cached_response", "query_embedding"):
        assert field in annotations, (
            f"_CacheAwareState must annotate field '{field}' "
            f"(declared annotations: {sorted(annotations)})"
        )

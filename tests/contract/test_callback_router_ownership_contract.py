# tests/contract/test_callback_router_ownership_contract.py
"""Single-owner contract for Telegram callback routing (#1598, #2980).

#1598 audit (2026-05-19) identified orphan ``create_*_router`` factories
under ``telegram_bot/handlers/`` that were never wired into bot startup
while ``PropertyBot._register_handlers`` registered the same callback
prefixes directly on ``self.dp``.

#2980 (P17 bot decomposition) resolved this by creating proper per-feature
router modules (service_callbacks.py, results_callbacks.py,
favorites_callbacks.py) that ARE properly wired into ``_register_handlers``
via ``self.dp.include_router(create_*_router(self))``. These are no longer
orphans — they are the canonical location for their callback prefixes.

This contract pins the P17 architecture so a future refactor cannot:

1. Remove the per-feature router modules (breaking the decomposition), AND
2. Drop the ``include_router(create_*_router(self))`` calls from
   ``_register_handlers`` (orphaning the callback prefixes).

The contract also pins that the orphan test files (which imported the old
unfactored ``create_*_router`` factories) remain deleted.

The contract is purely AST-static and runs in <0.1s.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]


# ---------------------------------------------------------------------------
# 1. Per-feature callback router modules must exist (P17 decomposition).
# ---------------------------------------------------------------------------


_CALLBACK_ROUTER_MODULES = pytest.mark.parametrize(
    "rel_path",
    [
        "telegram_bot/handlers/service_callbacks.py",
        "telegram_bot/handlers/results_callbacks.py",
        "telegram_bot/handlers/favorites_callbacks.py",
    ],
)


@_CALLBACK_ROUTER_MODULES
def test_callback_router_module_exists(rel_path: str) -> None:
    """Per-feature callback router modules must exist (#2980 P17 decomposition).

    These modules were created in P17 to decompose PropertyBot._register_handlers.
    They are properly wired into bot startup via include_router(); they are NOT orphans.
    """
    src_path = REPO_ROOT / rel_path
    assert src_path.is_file(), (
        f"{rel_path} must exist — it was created in #2980 (P17) to hold the "
        "per-feature callback router factory, properly wired into "
        "PropertyBot._register_handlers via include_router()."
    )


# ---------------------------------------------------------------------------
# 2. Orphan-only test modules must remain deleted — they imported the old
#    unfactored create_*_router factories from a time when those factories
#    were never wired into bot startup.
# ---------------------------------------------------------------------------


_ORPHAN_TEST_MODULES = pytest.mark.parametrize(
    "rel_path",
    [
        "tests/unit/test_service_callbacks.py",
        "tests/unit/test_results_callbacks.py",
        "tests/unit/test_favorites_callbacks.py",
    ],
)


@_ORPHAN_TEST_MODULES
def test_orphan_callback_test_module_is_gone(rel_path: str) -> None:
    """Stale test files for old unfactored callback factories must remain deleted."""
    src_path = REPO_ROOT / rel_path
    assert not src_path.is_file(), (
        f"{rel_path} imported the old unfactored create_*_router factories. "
        "It must remain deleted; callback behaviour is now covered by the "
        "per-feature router modules and PropertyBot method tests."
    )


# ---------------------------------------------------------------------------
# 3. PropertyBot._register_handlers must include all per-feature routers.
#    This is the positive lock that pins the "router-per-feature" decision.
# ---------------------------------------------------------------------------


# Each entry: (factory_call_fragment, router_module_fragment)
# We verify that _register_handlers imports and calls each factory.
_REQUIRED_ROUTER_INCLUSIONS: dict[str, str] = {
    "create_service_router": "service_callbacks",
    "create_results_router": "results_callbacks",
    "create_favorites_router": "favorites_callbacks",
    "create_crm_router": "crm_callbacks",
}


def _propertybot_register_handlers_source() -> str:
    """Return the source text of ``PropertyBot._register_handlers``."""
    bot_path = REPO_ROOT / "telegram_bot" / "bot.py"
    tree = ast.parse(bot_path.read_text(encoding="utf-8"))
    for cls in ast.walk(tree):
        if not isinstance(cls, ast.ClassDef) or cls.name != "PropertyBot":
            continue
        for node in cls.body:
            if isinstance(node, ast.FunctionDef) and node.name == "_register_handlers":
                return ast.unparse(node)
    pytest.fail("PropertyBot._register_handlers not found in telegram_bot/bot.py")


@pytest.mark.parametrize(("factory_name", "module_name"), list(_REQUIRED_ROUTER_INCLUSIONS.items()))
def test_property_bot_includes_feature_router(factory_name: str, module_name: str) -> None:
    """_register_handlers must include each per-feature callback router (#2980)."""
    body = _propertybot_register_handlers_source()
    assert factory_name in body, (
        f"PropertyBot._register_handlers must call {factory_name}() and include "
        f"the resulting router via self.dp.include_router(). "
        f"Dropping this wires out all callbacks registered in {module_name}.py."
    )
    assert "include_router" in body, (
        "PropertyBot._register_handlers must use self.dp.include_router() "
        "to wire per-feature routers. Direct self.dp.callback_query() registration "
        "was replaced by include_router() in #2980 (P17)."
    )


# ---------------------------------------------------------------------------
# 4. Each per-feature router module must define a create_*_router factory.
# ---------------------------------------------------------------------------


_ROUTER_FACTORY_NAMES: list[tuple[str, str]] = [
    ("telegram_bot/handlers/service_callbacks.py", "create_service_router"),
    ("telegram_bot/handlers/results_callbacks.py", "create_results_router"),
    ("telegram_bot/handlers/favorites_callbacks.py", "create_favorites_router"),
]


@pytest.mark.parametrize(("rel_path", "factory_name"), _ROUTER_FACTORY_NAMES)
def test_router_module_defines_factory(rel_path: str, factory_name: str) -> None:
    """Each per-feature router module must define its create_*_router factory."""
    src_path = REPO_ROOT / rel_path
    tree = ast.parse(src_path.read_text(encoding="utf-8"))
    func_names = {n.name for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)}
    assert factory_name in func_names, (
        f"{rel_path} must define {factory_name}() — the factory that "
        "creates and returns the aiogram Router for this callback group."
    )

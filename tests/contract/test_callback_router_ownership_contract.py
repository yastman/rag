***REMOVED*** tests/contract/test_callback_router_ownership_contract.py
"""Single-owner contract for Telegram callback routing (***REMOVED***1598).

***REMOVED***1598 audit (2026-05-19, refreshed 2026-05-21) showed that
``telegram_bot/handlers/{service_callbacks,results_callbacks,favorites_callbacks}.py``
each defined ``create_*_router()`` factories that were NEVER included in bot
startup, while ``PropertyBot._register_handlers`` registered the same
callback prefixes (``svc:``, ``cta:``, ``card:``, ``fav:``,
``FavoriteCB.filter(...)``, ``ResultsCB.filter()``) directly on
``self.dp``. Tests exercised the orphan modules but production runtime never
loaded them.

Resolution: ``PropertyBot`` is the single owner of these callback prefixes.
This contract pins that decision so a future refactor cannot:

1. Re-introduce orphan ``create_*_router`` factories under
   ``telegram_bot/handlers/`` for the same callback prefixes, AND
2. Keep ``PropertyBot._register_handlers`` shadowing them, AND/OR
3. Wire both paths into startup, leading to double-handling of the same
   callback.

The contract is purely AST-static and runs in <0.1s.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]


***REMOVED*** ---------------------------------------------------------------------------
***REMOVED*** 1. Orphan callback router modules must stay deleted.
***REMOVED*** ---------------------------------------------------------------------------


_ORPHAN_MODULES = pytest.mark.parametrize(
    "rel_path",
    [
        "telegram_bot/handlers/service_callbacks.py",
        "telegram_bot/handlers/results_callbacks.py",
        "telegram_bot/handlers/favorites_callbacks.py",
    ],
)


@_ORPHAN_MODULES
def test_orphan_callback_router_module_is_gone(rel_path: str) -> None:
    """The orphan callback router modules must not exist (***REMOVED***1598)."""
    src_path = REPO_ROOT / rel_path
    assert not src_path.is_file(), (
        f"{rel_path} was removed in ***REMOVED***1598 because PropertyBot._register_handlers"
        " owns the same callback prefixes directly. Re-introducing the orphan"
        " router would create duplicate handler ownership unless wiring also"
        " removes the corresponding PropertyBot.handle_*_callback methods."
    )


***REMOVED*** ---------------------------------------------------------------------------
***REMOVED*** 2. Orphan-only test modules must also be gone — they imported the deleted
***REMOVED***    create_*_router factories and would break collection if kept.
***REMOVED*** ---------------------------------------------------------------------------


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
    """Tests that imported the orphan ``create_*_router`` factories must be gone."""
    src_path = REPO_ROOT / rel_path
    assert not src_path.is_file(), (
        f"{rel_path} imported the orphan create_*_router factories from"
        " telegram_bot/handlers/*_callbacks.py. With the orphan modules deleted"
        " the test file must be deleted too. Behaviour for the same callback"
        " prefixes is covered by tests/unit/test_bot_handlers.py and friends"
        " against PropertyBot's methods."
    )


***REMOVED*** ---------------------------------------------------------------------------
***REMOVED*** 3. PropertyBot._register_handlers must keep registering each callback
***REMOVED***    prefix exactly once. This is the positive lock that pins the
***REMOVED***    "single-owner" decision so a future refactor can't accidentally drop
***REMOVED***    a registration.
***REMOVED*** ---------------------------------------------------------------------------


***REMOVED*** NOTE: ``ast.unparse`` always emits single quotes for str literals in
***REMOVED*** Python 3.12+. The tokens below are matched against the unparsed source,
***REMOVED*** not against the original ``bot.py`` text, so single quotes are correct.
_REQUIRED_REGISTRATION_TOKENS: dict[str, str] = {
    "F.data.startswith('svc:')": "self.handle_service_callback",
    "F.data.startswith('cta:')": "self.handle_cta_callback",
    "F.data.startswith('card:')": "self.handle_card_callback",
    "ResultsCB.filter()": "self.handle_results_callback",
    "FavoriteCB.filter(F.action == 'add')": "self.handle_fav_add",
    "FavoriteCB.filter(F.action == 'remove')": "self.handle_fav_remove",
    "FavoriteCB.filter(F.action == 'viewing')": "self.handle_fav_viewing",
    "F.data == 'fav:viewing_all'": "self.handle_favorite_callback",
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


@pytest.mark.parametrize(
    ("filter_token", "handler_token"), list(_REQUIRED_REGISTRATION_TOKENS.items())
)
def test_property_bot_registers_callback_prefix_exactly_once(
    filter_token: str, handler_token: str
) -> None:
    """Each callback filter must be registered exactly once on ``self.dp``."""
    body = _propertybot_register_handlers_source()
    filter_count = body.count(filter_token)
    handler_count = body.count(handler_token)
    assert filter_count == 1, (
        f"PropertyBot._register_handlers must register filter {filter_token!r}"
        f" exactly once; found {filter_count}. Drift here means either a"
        " duplicate registration (double-handling the same callback) or a"
        " missing registration (orphaning the prefix again, ***REMOVED***1598)."
    )
    assert handler_count >= 1, (
        f"PropertyBot._register_handlers must reference handler {handler_token!r}"
        f" at least once; found {handler_count}."
    )

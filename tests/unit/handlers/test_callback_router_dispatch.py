"""Direct dispatch behavior of the retained per-feature callback routers (#3436).

Replaces the deleted callback extraction/source-shape contracts with real
aiogram routing: a representative callback per router family is fed through
the dispatcher of a real ``make_property_bot`` bot and must reach exactly its
own canonical collaborator with the bound bot — never a sibling family's
handler. Clear-cache and feedback side effects stay with their canonical
suites (``test_command_handlers.py`` and the feedback suites).
"""

from __future__ import annotations

from contextlib import ExitStack
from datetime import UTC, datetime
from types import ModuleType
from unittest.mock import AsyncMock, patch

import pytest
from aiogram import Bot
from aiogram.types import CallbackQuery, Chat, Message, Update, User

from telegram_bot.handlers import bot_crm_callbacks, catalog, favorites
from tests.unit._property_bot_factory import make_property_bot


def _callback_update(data: str, update_id: int = 1) -> Update:
    """Build a real aiogram Update carrying an inline-button callback."""
    return Update(
        update_id=update_id,
        callback_query=CallbackQuery(
            id=str(update_id),
            from_user=User(id=42, is_bot=False, first_name="Test"),
            chat_instance="test-instance",
            data=data,
            message=Message(
                message_id=1,
                date=datetime(2026, 1, 1, tzinfo=UTC),
                chat=Chat(id=42, type="private"),
            ),
        ),
    )


# family -> (representative callback payload, canonical collaborator module/name)
_FAMILY_ROUTES: dict[str, tuple[str, ModuleType, str]] = {
    "crm": ("cc:all", bot_crm_callbacks, "handle_clearcache_callback"),
    "service": ("svc:costs", catalog, "handle_service_callback"),
    "favorites": ("fav:add:apt1", favorites, "handle_fav_add"),
    "results": ("results:more", catalog, "handle_results_callback"),
}

# Every collaborator any per-feature router can delegate to.
_COLLABORATORS: tuple[tuple[ModuleType, str], ...] = (
    (bot_crm_callbacks, "handle_clearcache_callback"),
    (catalog, "handle_service_callback"),
    (catalog, "handle_cta_callback"),
    (catalog, "handle_ask_callback"),
    (catalog, "handle_results_callback"),
    (catalog, "handle_card_callback"),
    (favorites, "handle_fav_add"),
    (favorites, "handle_fav_remove"),
    (favorites, "handle_fav_viewing"),
    (favorites, "handle_fav_viewing_all"),
    (favorites, "handle_favorite_callback"),
)


@pytest.mark.parametrize("family", sorted(_FAMILY_ROUTES))
async def test_router_family_routes_to_its_own_collaborator(family: str) -> None:
    """The wired dispatcher routes each family to exactly one canonical handler."""
    data, module, name = _FAMILY_ROUTES[family]
    bot = make_property_bot()
    with ExitStack() as stack:
        mocks = {
            (collab.__name__, collab_name): stack.enter_context(
                patch.object(collab, collab_name, AsyncMock())
            )
            for collab, collab_name in _COLLABORATORS
        }
        # The real dp auto-answers callbacks — stub the Telegram transport.
        stack.enter_context(patch.object(Bot, "__call__", new=AsyncMock()))
        await bot.dp.feed_update(bot.bot, _callback_update(data))

        target = mocks[(module.__name__, name)]
        target.assert_awaited_once()
        assert target.await_args is not None
        assert target.await_args.args[0] is bot
        assert target.await_args.args[1].data == data
        for key, injected in mocks.items():
            if key != (module.__name__, name):
                injected.assert_not_awaited()

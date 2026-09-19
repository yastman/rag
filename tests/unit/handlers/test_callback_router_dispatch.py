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
from functools import wraps
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


@pytest.mark.parametrize("route", ["menu", "group", "feedback", "feedback_done", "reason"])
async def test_bound_handler_receives_dispatcher_dependencies(route: str) -> None:
    """Native partial binding preserves dispatch and SDK dependency injection."""
    from telegram_bot.callback_data import FeedbackCB, FeedbackReasonCB
    from telegram_bot.handlers import bot_handoff, command_handlers, feedback_handlers
    from tests.unit._bot_config_factory import make_full_bot_config

    targets = {
        "menu": (command_handlers, "handle_menu_button"),
        "group": (bot_handoff, "_handle_group_message"),
        "feedback": (feedback_handlers, "handle_feedback"),
        "feedback_done": (feedback_handlers, "handle_feedback"),
        "reason": (feedback_handlers, "handle_feedback_reason"),
    }
    module, name = targets[route]
    recorder = AsyncMock()

    @wraps(getattr(module, name))
    async def handler(*args, **kwargs):
        await recorder(*args, **kwargs)

    config = make_full_bot_config()
    config.managers_group_id = -10042
    manager = object()
    feedback_store = object()
    with patch.object(module, name, handler), patch.object(Bot, "__call__", new=AsyncMock()):
        bot = make_property_bot(config)
        if route in {"feedback", "feedback_done", "reason"}:
            data = {
                "feedback": FeedbackCB(action="like", trace_id="trace").pack(),
                "feedback_done": "fb:done",
                "reason": FeedbackReasonCB(code="wrong_topic", trace_id="trace").pack(),
            }[route]
            update = _callback_update(data)
        else:
            update = Update(
                update_id=1,
                message=Message(
                    message_id=1,
                    date=datetime(2026, 1, 1, tzinfo=UTC),
                    from_user=User(id=42, is_bot=False, first_name="Test"),
                    chat=Chat(
                        id=-10042 if route == "group" else 42,
                        type="supergroup" if route == "group" else "private",
                    ),
                    message_thread_id=7 if route == "group" else None,
                    text="🔑 Услуги" if route == "menu" else "question",
                ),
            )
        await bot.dp.feed_update(
            bot.bot, update, dialog_manager=manager, feedback_store=feedback_store, locale="uk"
        )
        recorder.assert_awaited_once()
        assert recorder.await_args.args[0] is bot
        if route == "menu":
            assert recorder.await_args.kwargs["dialog_manager"] is manager
            assert recorder.await_args.kwargs["state"] is not None
        elif route in {"feedback", "reason"}:
            assert recorder.await_args.kwargs["callback_data"].trace_id == "trace"
            assert recorder.await_args.kwargs["feedback_store"] is feedback_store
        elif route == "group":
            assert recorder.await_args.args[1].message_thread_id == 7
        await bot.dp.storage.close()

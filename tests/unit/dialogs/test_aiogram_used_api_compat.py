"""Behavior compatibility tests for the aiogram surface the bot actually uses (#3409).

Versions live in ``pyproject.toml`` + ``uv.lock`` (the ``telegram`` extra) and are
not asserted here. These tests exercise the aiogram / aiogram-dialog primitives
the application depends on, so an incompatible upgrade fails with a behavior
break instead of a version-string equality miss:

- Dispatcher/Router registration and include ordering (lifecycle router wiring);
- ``StateFilter(None)`` matching semantics (catch-all free-text route);
- ``DialogManager`` start/done/reset_stack coroutine API and call shapes;
- Start/Show/Launch mode enums the bot selects;
- CallbackData pack/unpack round-trip (telegram_bot.callback_data classes);
- inline/reply keyboard serialization to the Telegram wire format;
- ``setup_dialogs`` registering the dialog stack exactly once per dispatcher;
- ``remove_intent_id`` and ``UnknownIntent`` used for stale-dialog recovery.

Dialog/Window construction and per-dialog routing are behavior-owned by the
sibling dialog tests (test_catalog_dialog.py, test_ask_routing_ownership.py, ...).
"""

from __future__ import annotations

import inspect

import pytest


# ---------------------------------------------------------------------------
# Dispatcher / Router registration and ordering (telegram_bot/lifecycle/lifecycle.py)
# ---------------------------------------------------------------------------


def test_dispatcher_include_router_preserves_registration_order() -> None:
    from aiogram import Dispatcher, Router

    dp = Dispatcher()
    first = Router(name="first")
    second = Router(name="second")

    dp.include_router(first)
    dp.include_router(second)

    assert dp.sub_routers == [first, second]


def test_router_message_decorator_registers_handler_with_state_and_magic_filters() -> None:
    from aiogram import F, Router
    from aiogram.filters import StateFilter

    router = Router(name="catch_all_query")

    async def handle_query(message: object) -> None:  # pragma: no cover - stub
        return None

    registered = router.message(StateFilter(None), F.text)(handle_query)

    assert registered is handle_query
    (handler,) = router.message.handlers
    assert handler.callback is handle_query
    assert handler.filters is not None
    callbacks = [filter_object.callback for filter_object in handler.filters]
    assert any(isinstance(cb, StateFilter) and cb.states == (None,) for cb in callbacks), (
        "StateFilter(None) must survive decorator registration"
    )
    assert any(filter_object.magic is not None for filter_object in handler.filters), (
        "F.text magic filter must survive decorator registration"
    )


# ---------------------------------------------------------------------------
# StateFilter(None) semantics (catch-all free-text route, lifecycle.py:461)
# ---------------------------------------------------------------------------


async def test_state_filter_none_matches_only_stateless_events() -> None:
    from aiogram.filters import StateFilter
    from aiogram.types import TelegramObject

    state_filter = StateFilter(None)

    assert await state_filter(TelegramObject(), raw_state=None) is True
    assert await state_filter(TelegramObject(), raw_state="SomeStates:some_state") is False


def test_state_filter_requires_at_least_one_state() -> None:
    from aiogram.filters import StateFilter

    with pytest.raises(ValueError, match="At least one state"):
        StateFilter()


# ---------------------------------------------------------------------------
# DialogManager start/done/reset_stack and mode enums (dialogs/*, handlers/*)
# ---------------------------------------------------------------------------


def test_dialog_manager_exposes_coroutine_api_for_bot_call_shapes() -> None:
    from aiogram_dialog import DialogManager, StartMode

    for method_name in ("start", "done", "reset_stack"):
        method = getattr(DialogManager, method_name)
        assert inspect.iscoroutinefunction(method), (
            f"DialogManager.{method_name} must stay awaitable"
        )

    # Bot call shapes: start(state, mode=StartMode.RESET_STACK), done(),
    # reset_stack(remove_keyboard=True/False). DialogManager is a Protocol, so
    # bind a placeholder for the manager instance.
    inspect.signature(DialogManager.start).bind(object(), object(), mode=StartMode.RESET_STACK)
    inspect.signature(DialogManager.done).bind(object())
    inspect.signature(DialogManager.reset_stack).bind(object(), remove_keyboard=False)
    inspect.signature(DialogManager.reset_stack).bind(object(), remove_keyboard=True)


def test_dialog_mode_enums_expose_members_used_by_bot() -> None:
    from aiogram_dialog import LaunchMode, ShowMode, StartMode

    assert StartMode.RESET_STACK is not None
    for show_mode in (
        ShowMode.NO_UPDATE,
        ShowMode.SEND,
        ShowMode.EDIT,
        ShowMode.DELETE_AND_SEND,
    ):
        assert show_mode is not None
    assert LaunchMode.ROOT is not None


# ---------------------------------------------------------------------------
# CallbackData packing (telegram_bot/callback_data.py)
# ---------------------------------------------------------------------------


def test_callback_data_packs_with_prefix_and_roundtrips() -> None:
    from telegram_bot.callback_data import (
        DemoCB,
        FavoriteCB,
        FeedbackCB,
        FeedbackReasonCB,
        ResultsCB,
    )

    feedback = FeedbackCB(action="like", trace_id="abc")
    packed = feedback.pack()
    assert packed.startswith("fb:")
    unpacked = FeedbackCB.unpack(packed)
    assert unpacked.action == "like"
    assert unpacked.trace_id == "abc"

    reason = FeedbackReasonCB(code="quality", trace_id="abc")
    assert reason.pack().startswith("fbr:")
    reason_unpacked = FeedbackReasonCB.unpack(reason.pack())
    assert (reason_unpacked.code, reason_unpacked.trace_id) == ("quality", "abc")

    demo = DemoCB(action="apartments", idx=2)
    demo_unpacked = DemoCB.unpack(demo.pack())
    assert demo_unpacked.action == "apartments"
    assert demo_unpacked.idx == 2
    assert isinstance(demo_unpacked.idx, int), "int fields must survive pack/unpack"

    favorite = FavoriteCB(action="add")
    favorite_unpacked = FavoriteCB.unpack(favorite.pack())
    assert favorite_unpacked.action == "add"
    assert favorite_unpacked.apartment_id == ""

    results = ResultsCB(action="more")
    assert results.pack().startswith("results:")


# ---------------------------------------------------------------------------
# Message / keyboard serialization (telegram_bot/keyboards/*, handlers/*)
# ---------------------------------------------------------------------------


def test_inline_keyboard_builder_serializes_to_telegram_wire_format() -> None:
    from aiogram.types import InlineKeyboardMarkup
    from aiogram.utils.keyboard import InlineKeyboardBuilder

    builder = InlineKeyboardBuilder()
    builder.button(text="A", callback_data="cb:a")
    builder.button(text="B", callback_data="cb:b")
    builder.adjust(1)

    markup = builder.as_markup()
    assert isinstance(markup, InlineKeyboardMarkup)

    dumped = markup.model_dump(exclude_none=True)
    assert dumped == {
        "inline_keyboard": [
            [{"text": "A", "callback_data": "cb:a"}],
            [{"text": "B", "callback_data": "cb:b"}],
        ]
    }


def test_reply_keyboard_markup_serializes_to_telegram_wire_format() -> None:
    from aiogram.types import KeyboardButton, ReplyKeyboardMarkup

    markup = ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="Hi")]], resize_keyboard=True)
    assert markup.model_dump(exclude_none=True) == {
        "keyboard": [[{"text": "Hi"}]],
        "resize_keyboard": True,
    }


# ---------------------------------------------------------------------------
# setup_dialogs registers the dialog stack exactly once (lifecycle.py:467)
# ---------------------------------------------------------------------------


def test_setup_dialogs_registers_dialog_stack_once_per_dispatcher() -> None:
    from aiogram import Dispatcher
    from aiogram_dialog import setup_dialogs

    dp = Dispatcher()
    setup_dialogs(dp)

    assert [router.name for router in dp.sub_routers].count("AiogramDialogStates") == 1

    update_outer = [type(m).__name__ for m in dp.update.outer_middleware]
    assert update_outer.count("BgFactoryMiddleware") == 1, (
        "the dialog background-manager middleware must be registered exactly once"
    )
    for observer_name in ("message", "callback_query"):
        observer = getattr(dp, observer_name)
        inner = [type(m).__name__ for m in observer.middleware]
        assert inner.count("ManagerMiddleware") == 1, (
            f"dp.{observer_name} must receive exactly one DialogManager middleware"
        )


# ---------------------------------------------------------------------------
# Stale-dialog recovery primitives (dialogs/filter/_state.py, middlewares/error_handler.py)
# ---------------------------------------------------------------------------


def test_remove_intent_id_strips_intent_prefix() -> None:
    from aiogram_dialog.utils import CB_SEP, remove_intent_id

    intent_id, dialog_data = remove_intent_id(f"12{CB_SEP}fb:like:abc")
    assert (intent_id, dialog_data) == ("12", "fb:like:abc")
    assert remove_intent_id("fb:like:abc") == (None, "fb:like:abc")


def test_unknown_intent_is_an_exception_available_for_recovery_filtering() -> None:
    from aiogram_dialog.api.exceptions import UnknownIntent

    assert issubclass(UnknownIntent, Exception)

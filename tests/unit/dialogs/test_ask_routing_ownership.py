"""Deterministic Ask/FAQ/root-menu FSM routing ownership (#3204).

Contracts proven here:

1. **Ask owns its free-text step by exiting cleanly** — the Ask action invites
   the user to type a question, so any active aiogram-dialog stack or raw FSM
   state must be closed first; otherwise the typed question is consumed by the
   stale flow instead of the single free-text Q&A route (catch-all
   ``StateFilter(None)`` → ``handle_query``).
2. **Popular FAQ callbacks (``ask:*``) stay on the same grounded Q&A
   contract** — one callback answer, one dispatch, stale flows exited first.
3. **Dialog routers are included ahead of the final catch-all** and the
   catch-all owns only stateless text.
4. **``ask:*`` callbacks have exactly one registered owner** (no duplicate
   ownership / duplicate sends).
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock

from aiogram import Dispatcher

from telegram_bot.dialogs.root_nav import exit_to_client_root
from telegram_bot.handlers import catalog as _bot_catalog


_TELEGRAM_BOT_DIR = Path(__file__).resolve().parents[3] / "telegram_bot"


def _make_manager(*, has_context: bool) -> MagicMock:
    manager = MagicMock()
    manager.has_context = lambda: has_context
    manager.reset_stack = AsyncMock()
    return manager


def _make_state() -> MagicMock:
    state = MagicMock()
    state.clear = AsyncMock()
    return state


# ---------------------------------------------------------------------------
# 1. Ask exits cleanly to the single free-text Q&A route
# ---------------------------------------------------------------------------


async def test_handle_ask_exits_active_flow_and_sends_prompt_once():
    """_handle_ask closes an active dialog stack + FSM state, then prompts once."""
    message = MagicMock()
    message.answer = AsyncMock()
    state = _make_state()
    manager = _make_manager(has_context=True)

    await _bot_catalog._handle_ask(
        MagicMock(), message, i18n=None, state=state, dialog_manager=manager
    )

    manager.reset_stack.assert_awaited_once_with(remove_keyboard=False)
    state.clear.assert_awaited_once()
    message.answer.assert_awaited_once()
    prompt, kwargs = message.answer.call_args.args[0], message.answer.call_args.kwargs
    assert "вопрос" in prompt.lower()
    buttons = [btn for row in kwargs["reply_markup"].inline_keyboard for btn in row]
    assert {btn.callback_data for btn in buttons} == {
        "ask:docs",
        "ask:costs",
        "ask:vnzh",
        "ask:installment",
    }


async def test_handle_ask_without_active_flow_only_sends_prompt():
    """Without an active flow there is nothing to reset — a single prompt is sent."""
    message = MagicMock()
    message.answer = AsyncMock()

    await _bot_catalog._handle_ask(MagicMock(), message, i18n=None, state=None, dialog_manager=None)

    message.answer.assert_awaited_once()


async def test_handle_ask_keeps_persistent_reply_keyboard():
    """Ask is launched from the persistent reply keyboard — never remove it."""
    message = MagicMock()
    message.answer = AsyncMock()
    manager = _make_manager(has_context=True)

    await _bot_catalog._handle_ask(
        MagicMock(), message, i18n=None, state=None, dialog_manager=manager
    )

    manager.reset_stack.assert_awaited_once_with(remove_keyboard=False)


async def test_exit_to_client_root_is_tolerant_to_missing_context():
    """The shared exit primitive no-ops without state/manager and survives mocks."""
    await exit_to_client_root(state=None, dialog_manager=None)  # does not raise

    manager = MagicMock(spec=["reset_stack"])  # no has_context attr at all
    manager.reset_stack = AsyncMock()
    state = _make_state()

    await exit_to_client_root(state=state, dialog_manager=manager)

    manager.reset_stack.assert_not_awaited()
    state.clear.assert_awaited_once()


# ---------------------------------------------------------------------------
# 2. Popular FAQ callbacks stay on the grounded Q&A contract
# ---------------------------------------------------------------------------


async def test_ask_callback_exits_flow_then_dispatches_mapped_query():
    bot = MagicMock()
    bot.handle_menu_action_text = AsyncMock()
    callback = MagicMock()
    callback.data = "ask:vnzh"
    callback.answer = AsyncMock()
    callback.message = MagicMock()
    state = _make_state()
    manager = _make_manager(has_context=True)

    await _bot_catalog.handle_ask_callback(bot, callback, state=state, dialog_manager=manager)

    callback.answer.assert_awaited_once()
    manager.reset_stack.assert_awaited_once_with(remove_keyboard=False)
    state.clear.assert_awaited_once()
    bot.handle_menu_action_text.assert_awaited_once_with(
        callback.message,
        "Как получить ВНЖ в Болгарии?",
    )


async def test_ask_callback_unknown_key_answers_without_dispatch_or_reset():
    bot = MagicMock()
    bot.handle_menu_action_text = AsyncMock()
    callback = MagicMock()
    callback.data = "ask:unknown_key"
    callback.answer = AsyncMock()
    callback.message = MagicMock()
    state = _make_state()
    manager = _make_manager(has_context=True)

    await _bot_catalog.handle_ask_callback(bot, callback, state=state, dialog_manager=manager)

    callback.answer.assert_awaited_once()
    bot.handle_menu_action_text.assert_not_awaited()
    state.clear.assert_not_awaited()
    manager.reset_stack.assert_not_awaited()


async def test_ask_callback_without_message_answers_without_dispatch():
    bot = MagicMock()
    bot.handle_menu_action_text = AsyncMock()
    callback = MagicMock()
    callback.data = "ask:docs"
    callback.answer = AsyncMock()
    callback.message = None

    await _bot_catalog.handle_ask_callback(bot, callback, state=None, dialog_manager=None)

    callback.answer.assert_awaited_once()
    bot.handle_menu_action_text.assert_not_awaited()


# ---------------------------------------------------------------------------
# 3. Registration order: dialog routers ahead of the final catch-all
# ---------------------------------------------------------------------------


_DIALOG_ROUTERS: tuple[str, ...] = (
    "ClientMenuSG",
    "CatalogSG",
    "SettingsSG",
    "DemoSG",
    "FunnelSG",
    "FilterSG",
    "FaqSG",
    "ViewingSG",
    "HandoffSG",
)


@lru_cache(maxsize=1)
def _build_dialog_dispatcher() -> tuple[Dispatcher, Any]:
    """Build the setup_dialogs dispatcher once.

    Dialog routers are module-level singletons and a Router can only be
    attached to one dispatcher, so the built dispatcher is shared between
    tests in this module.
    """
    from telegram_bot.lifecycle.lifecycle import setup_dialogs

    async def _catch_all_query(message: Any) -> None:  # pragma: no cover - stub
        return None

    stub = SimpleNamespace(dp=Dispatcher(), handle_query=_catch_all_query)
    setup_dialogs(stub)
    return stub.dp, stub


def test_setup_dialogs_includes_all_client_dialogs_before_catch_all():
    dp, _ = _build_dialog_dispatcher()

    names = [getattr(router, "name", "") for router in dp.sub_routers]
    positions = [names.index(name) for name in _DIALOG_ROUTERS]
    catch_all_position = names.index("catch_all_query")
    assert all(pos < catch_all_position for pos in positions), (
        f"catch_all_query must be included after all dialog routers, got order: {names}"
    )


def test_catch_all_owns_only_stateless_text():
    from aiogram.filters import StateFilter

    _, stub = _build_dialog_dispatcher()

    handlers = stub._catch_all_router.message.handlers
    assert len(handlers) == 1, "catch-all must register exactly one text owner"
    filter_objects = handlers[0].filters
    stateless = [
        fo
        for fo in filter_objects
        if isinstance(fo.callback, StateFilter) and fo.callback.states == (None,)
    ]
    free_text = [fo for fo in filter_objects if fo.magic is not None]
    assert stateless, "catch-all must be gated by StateFilter(None)"
    assert free_text, "catch-all must be gated by F.text"
    assert handlers[0].callback == stub.handle_query


# ---------------------------------------------------------------------------
# 4. Single ownership of the ask:* callback family
# ---------------------------------------------------------------------------


def test_ask_callback_family_has_single_owner():
    """Exactly one production module registers the ask: callback prefix."""
    registrations: list[Path] = []
    for path in sorted(_TELEGRAM_BOT_DIR.rglob("*.py")):
        if "__pycache__" in path.parts or ".venv" in path.parts:
            continue
        text = path.read_text(encoding="utf-8")
        if 'F.data.startswith("ask:")' in text:
            registrations.append(path)
    assert registrations == [_TELEGRAM_BOT_DIR / "handlers" / "service_callbacks.py"]


# ---------------------------------------------------------------------------
# 5. Inline root menu Ask threads state through to the exit primitive
# ---------------------------------------------------------------------------


async def test_inline_root_menu_ask_passes_state_and_manager():
    from telegram_bot.dialogs.client_menu import on_menu_action

    mock_bot = AsyncMock()
    mock_bot._handle_ask = AsyncMock()

    callback = MagicMock()
    callback.from_user = None
    callback.message = MagicMock()
    button = MagicMock()
    button.widget_id = "ask"

    manager = AsyncMock()
    manager.done = AsyncMock()
    manager.middleware_data = {
        "property_bot": mock_bot,
        "i18n": "i18n-stub",
        "state": "state-stub",
    }

    await on_menu_action(callback, button, manager)

    manager.done.assert_awaited_once()
    mock_bot._handle_ask.assert_awaited_once_with(
        callback.message,
        i18n="i18n-stub",
        state="state-stub",
        dialog_manager=manager,
    )

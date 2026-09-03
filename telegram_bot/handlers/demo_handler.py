"""Demo flow trigger handlers (#2054).

This module is now a thin trigger layer: the previous custom-FSM apartment
search (``DemoStates.waiting_query`` + free-text/voice message handlers)
moved into the aiogram-dialog ``demo_dialog`` in
``telegram_bot/dialogs/demo.py`` (issue #2054, parent #1232). This module
keeps only:

* ``handle_demo_button`` — the ``/menu`` button handler that posts the
  inline demo menu (still called directly from ``PropertyBot``).
* ``handle_demo_apartments`` — the inline-button callback that opens the
  aiogram-dialog demo flow via ``dialog_manager.start(...)``.

``transcribe_voice`` moved to
:mod:`telegram_bot.services.voice_transcription` (#3238) so the catalog and
demo dialogs share one import; it is re-exported here for compatibility.

The old ``handle_demo_example`` / ``handle_demo_search_text`` /
``handle_demo_search_voice`` / ``_run_demo_search`` / ``DemoStates``
surface was deleted: example clicks land on the dialog's
``on_example_selected`` / ``Select`` widget; text and voice land on the
dialog's ``MessageInput`` widgets.
"""

from __future__ import annotations

import logging

from aiogram import F, Router
from aiogram.types import CallbackQuery, Message
from aiogram_dialog import DialogManager, ShowMode, StartMode

from telegram_bot.callback_data import DemoCB
from telegram_bot.dialogs.states import DemoSG
from telegram_bot.keyboards.demo_keyboard import build_demo_menu
from telegram_bot.services.voice_transcription import transcribe_voice


logger = logging.getLogger(__name__)


async def handle_demo_button(message: Message) -> None:
    """Handle '🎯 Демонстрация' menu button — post inline demo menu."""
    await message.answer(
        "🎯 Демонстрация возможностей\n\nПосмотрите, как работает умный подбор недвижимости:",
        reply_markup=build_demo_menu(),
    )


async def handle_demo_apartments(
    callback: CallbackQuery,
    dialog_manager: DialogManager,
) -> None:
    """Handle ``demo:apartments`` — open aiogram-dialog demo flow.

    The trigger callback comes from an inline button rendered on top of the
    demo menu; opening the dialog with ``RESET_STACK`` lets the user cancel
    cleanly without ending up in an unrelated parent dialog. ``ShowMode.SEND``
    posts the dialog window as a fresh message (the button bubble stays as
    history).
    """
    await callback.answer()
    await dialog_manager.start(
        DemoSG.intro,
        mode=StartMode.RESET_STACK,
        show_mode=ShowMode.SEND,
    )


# Backward-compatible re-export (#3238): the implementation lives in
# telegram_bot.services.voice_transcription.
__all__ = ["handle_demo_apartments", "handle_demo_button", "transcribe_voice"]


def create_demo_router() -> Router:
    """Return a fresh demo router instance.

    Issue #2054: the router now only registers the
    ``demo:apartments`` callback that bridges the inline menu into the
    aiogram-dialog ``demo_dialog``. Free-text / voice / example-button
    handling lives entirely inside the dialog (see
    ``telegram_bot/dialogs/demo.py``).
    """
    router = Router(name="demo")
    router.callback_query.register(
        handle_demo_apartments,
        DemoCB.filter(F.action == "apartments"),
    )
    return router

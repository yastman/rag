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
* ``transcribe_voice`` — Whisper helper still used by the dialog's
  ``on_voice_input`` handler.

The old ``handle_demo_example`` / ``handle_demo_search_text`` /
``handle_demo_search_voice`` / ``_run_demo_search`` / ``DemoStates``
surface was deleted: example clicks land on the dialog's
``on_example_selected`` / ``Select`` widget; text and voice land on the
dialog's ``MessageInput`` widgets.
"""

from __future__ import annotations

import io
import logging
import os
from typing import Any

from aiogram import F, Router
from aiogram.types import CallbackQuery, Message
from aiogram_dialog import DialogManager, ShowMode, StartMode

from telegram_bot.callback_data import DemoCB
from telegram_bot.dialogs.states import DemoSG
from telegram_bot.keyboards.demo_keyboard import build_demo_menu
from telegram_bot.observability import observe


logger = logging.getLogger(__name__)


async def handle_demo_button(message: Message) -> None:
    """Handle '🎯 Демонстрация' menu button — post inline demo menu."""
    await message.answer(
        "🎯 Демонстрация возможностей\n\nПосмотрите, как работает умный подбор недвижимости:",
        reply_markup=build_demo_menu(),
    )


@observe(name="demo-apartments-prompt", capture_input=False, capture_output=False)
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


async def transcribe_voice(message: Message, *, llm: Any = None) -> str | None:
    """Download a Telegram voice message and transcribe via Whisper.

    Used by ``telegram_bot.dialogs.demo.on_voice_input``. The optional
    ``llm`` parameter accepts an ``AsyncOpenAI`` (or compatible) client so
    tests can inject a mock; the default ``langfuse.openai.AsyncOpenAI``
    is constructed inline so failures degrade to ``None`` rather than
    raising at import time.
    """
    from langfuse.openai import AsyncOpenAI

    @observe(name="demo-transcribe-voice")
    async def _run() -> str | None:
        bot = message.bot
        if bot is None or message.voice is None:
            return None
        file = await bot.get_file(message.voice.file_id)
        data = io.BytesIO()
        await bot.download_file(file.file_path, data)  # type: ignore[arg-type]
        data.seek(0)
        data.name = "voice.ogg"  # type: ignore[attr-defined]

        # #2214: route the default client through the LiteLLM proxy. model="whisper"
        # is a LiteLLM alias, so a bare AsyncOpenAI() (public OpenAI) would 404 and
        # bypass the proxy's success_callback=["langfuse"]. Honour LLM_BASE_URL /
        # LLM_API_KEY (the canonical proxy env, e.g. http://litellm:4000/v1).
        client = (
            llm
            if llm is not None
            else AsyncOpenAI(
                api_key=os.getenv("LLM_API_KEY"),
                base_url=os.getenv("LLM_BASE_URL"),
            )
        )
        transcript = await client.audio.transcriptions.create(
            model="whisper",
            file=data,
            language="ru",
        )
        return transcript.text or None

    return await _run()


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

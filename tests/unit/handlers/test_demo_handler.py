"""Tests for the thin demo trigger router (#2054).

After #2054 the demo-apartment flow is an aiogram-dialog
(``telegram_bot/dialogs/demo.py``); the legacy ``DemoStates`` FSM and the
free-text/voice/example message handlers are gone. This module's
``demo_handler`` keeps only:

* ``handle_demo_button`` — posts the inline demo menu;
* ``handle_demo_apartments`` — bridges the inline button into the dialog
  via ``dialog_manager.start(DemoSG.intro, ...)``;
* ``transcribe_voice`` — Whisper helper still used by the dialog;
* ``create_demo_router`` — registers only the ``demo:apartments``
  callback.

The free-text/voice/example tests live with the dialog itself in
``tests/unit/dialogs/test_demo_dialog.py``.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from aiogram.types import CallbackQuery
from aiogram_dialog import DialogManager, ShowMode, StartMode

from telegram_bot.dialogs.states import DemoSG
from telegram_bot.handlers.demo_handler import (
    create_demo_router,
    handle_demo_apartments,
    handle_demo_button,
)


class TestDemoButton:
    @pytest.mark.asyncio
    async def test_demo_button_sends_inline_menu(self) -> None:
        message = AsyncMock()
        await handle_demo_button(message)
        message.answer.assert_awaited_once()
        call_kwargs = message.answer.await_args
        assert "Демонстрация" in call_kwargs.args[0]
        assert call_kwargs.kwargs.get("reply_markup") is not None


class TestDemoApartmentsBridgesToDialog:
    @pytest.mark.asyncio
    async def test_demo_apartments_starts_dialog(self) -> None:
        callback = AsyncMock(spec=CallbackQuery)
        callback.answer = AsyncMock()
        dialog_manager = AsyncMock(spec=DialogManager)

        await handle_demo_apartments(callback, dialog_manager)

        callback.answer.assert_awaited_once()
        dialog_manager.start.assert_awaited_once()
        kwargs = dialog_manager.start.await_args.kwargs
        args = dialog_manager.start.await_args.args
        # First positional arg is the target state
        assert args[0] is DemoSG.intro
        # RESET_STACK so the dialog opens as fresh top-of-stack
        assert kwargs["mode"] == StartMode.RESET_STACK
        # SEND so the dialog window posts as a new message
        assert kwargs["show_mode"] == ShowMode.SEND

    @pytest.mark.asyncio
    async def test_demo_apartments_acknowledges_callback_first(self) -> None:
        """``callback.answer()`` must run before ``dialog_manager.start``
        so Telegram clears the inline-button spinner immediately."""
        callback = AsyncMock(spec=CallbackQuery)
        callback.answer = AsyncMock()
        dialog_manager = AsyncMock(spec=DialogManager)

        order: list[str] = []
        callback.answer.side_effect = lambda *_a, **_k: order.append("answer")
        dialog_manager.start.side_effect = lambda *_a, **_k: order.append("start")

        await handle_demo_apartments(callback, dialog_manager)

        assert order == ["answer", "start"]


class TestDemoRouterRegistration:
    def test_router_registers_only_apartments_callback(self) -> None:
        """The router must NOT register message handlers anymore — the
        dialog's MessageInput widgets handle text and voice."""
        router = create_demo_router()
        assert router.message.handlers == [], (
            "demo_handler.create_demo_router() must not register message handlers; "
            "free-text and voice input now flow through demo_dialog's MessageInput."
        )
        # Exactly one callback handler: demo:apartments
        assert len(router.callback_query.handlers) == 1
        cb_handler = router.callback_query.handlers[0]
        assert cb_handler.callback.__name__ == "handle_demo_apartments"


class TestTranscribeVoice:
    async def test_transcribe_voice_uses_injected_llm(self) -> None:
        """transcribe_voice must use the injected llm, not construct its
        own AsyncOpenAI."""
        from telegram_bot.handlers.demo_handler import transcribe_voice

        message = AsyncMock()
        message.voice = MagicMock(file_id="f1")
        message.bot = AsyncMock()
        file_mock = AsyncMock()
        file_mock.file_path = "voice/test.ogg"
        message.bot.get_file.return_value = file_mock

        llm = AsyncMock()
        llm.audio.transcriptions.create.return_value = AsyncMock(text="hello")

        result = await transcribe_voice(message, llm=llm)

        assert result == "hello"
        llm.audio.transcriptions.create.assert_awaited_once()

    async def test_transcribe_voice_returns_none_when_voice_missing(self) -> None:
        from telegram_bot.handlers.demo_handler import transcribe_voice

        message = AsyncMock()
        message.voice = None
        message.bot = AsyncMock()

        result = await transcribe_voice(message, llm=AsyncMock())
        assert result is None


class TestHandleVoiceStateFilter:
    """``handle_voice`` registration must keep ``StateFilter(None)``.

    aiogram-dialog manages FSM state under the hood (when the user is in
    ``DemoSG.intro`` the FSM state is set). ``StateFilter(None)`` on the
    catch-all ``handle_voice`` is what prevents the bot from intercepting
    voice messages while the user is inside ``demo_dialog`` — the
    dialog's ``MessageInput(on_voice_input, ...)`` resolves first.
    """

    def test_handle_voice_has_state_filter(self) -> None:
        import inspect

        from telegram_bot.bot import PropertyBot

        source = inspect.getsource(PropertyBot._register_handlers)
        assert "StateFilter(None)" in source and "F.voice" in source, (
            "handle_voice must be registered with StateFilter(None) so the "
            "demo_dialog MessageInput can intercept voice messages first."
        )

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

from types import SimpleNamespace
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
    """``transcribe_voice`` is config-driven and text-fallback safe (#3240)."""

    @staticmethod
    def _voice_message() -> AsyncMock:
        message = AsyncMock()
        message.voice = MagicMock(file_id="f1")
        message.bot = AsyncMock()
        file_mock = AsyncMock()
        file_mock.file_path = "voice/test.ogg"
        message.bot.get_file.return_value = file_mock
        return message

    @staticmethod
    def _ready_config(**overrides):
        from types import SimpleNamespace

        defaults = {
            "voice_enabled": True,
            "llm_api_key": "cfg-key",
            "stt_model": "whisper-large-v3",
            "voice_language": "bg",
            "voice_timeout": 30,
            "show_transcription": True,
        }
        defaults.update(overrides)
        return SimpleNamespace(**defaults)

    async def test_transcribe_voice_uses_configured_model_language_and_key(
        self, monkeypatch
    ) -> None:
        """Model, language, and API key must come from BotConfig (#3240)."""
        import openai

        from telegram_bot.handlers.demo_handler import transcribe_voice

        monkeypatch.setenv("OPENAI_API_KEY", "env-key")

        created: dict = {}
        create = AsyncMock(return_value=MagicMock(text="здравей"))

        def _factory(*args, **kwargs):
            created["kwargs"] = kwargs
            client = MagicMock()
            client.audio.transcriptions.create = create
            return client

        monkeypatch.setattr(openai, "AsyncOpenAI", _factory)

        message = self._voice_message()
        config = self._ready_config()

        result = await transcribe_voice(message, config=config)

        assert result == "здравей"
        assert created["kwargs"]["api_key"] == "cfg-key"
        create.assert_awaited_once()
        call_kwargs = create.await_args.kwargs
        assert call_kwargs["model"] == "whisper-large-v3"
        assert call_kwargs["language"] == "bg"

    async def test_transcribe_voice_download_failure_returns_none(self) -> None:
        """Telegram download errors must degrade to None, never raise."""
        from telegram_bot.handlers.demo_handler import transcribe_voice

        message = self._voice_message()
        message.bot.get_file.side_effect = RuntimeError("telegram down")

        result = await transcribe_voice(message, config=self._ready_config())
        assert result is None

    async def test_transcribe_voice_provider_failure_returns_none(self, monkeypatch) -> None:
        """Provider errors must degrade to None, never raise."""
        import openai

        from telegram_bot.handlers.demo_handler import transcribe_voice

        def _factory(*args, **kwargs):
            client = MagicMock()
            client.audio.transcriptions.create = AsyncMock(
                side_effect=RuntimeError("provider 500")
            )
            return client

        monkeypatch.setattr(openai, "AsyncOpenAI", _factory)

        message = self._voice_message()
        result = await transcribe_voice(message, config=self._ready_config())
        assert result is None

    async def test_transcribe_voice_timeout_returns_none(self, monkeypatch) -> None:
        """A stuck provider must hit the configured timeout and return None."""
        import asyncio

        import openai

        from telegram_bot.handlers.demo_handler import transcribe_voice

        def _factory(*args, **kwargs):
            client = MagicMock()

            async def _slow(*_a, **_k):
                await asyncio.sleep(5)
                return MagicMock(text="late")

            client.audio.transcriptions.create = _slow
            return client

        monkeypatch.setattr(openai, "AsyncOpenAI", _factory)

        message = self._voice_message()
        config = self._ready_config(voice_timeout=1)
        result = await transcribe_voice(message, config=config)
        assert result is None

    async def test_transcribe_voice_returns_none_when_voice_missing(self) -> None:
        from telegram_bot.handlers.demo_handler import transcribe_voice

        message = AsyncMock()
        message.voice = None
        message.bot = AsyncMock()

        result = await transcribe_voice(message, config=self._ready_config())
        assert result is None


class TestVoiceReady:
    """Voice is exposed only when enabled and keyed (#3240)."""

    def test_voice_ready_none_config_is_false(self) -> None:
        from telegram_bot.handlers.demo_handler import voice_ready

        assert voice_ready(None) is False

    def test_voice_ready_disabled_is_false(self) -> None:
        from telegram_bot.handlers.demo_handler import voice_ready

        config = SimpleNamespace(voice_enabled=False, llm_api_key="k")
        assert voice_ready(config) is False

    def test_voice_ready_enabled_without_key_is_false(self) -> None:
        from telegram_bot.handlers.demo_handler import voice_ready

        config = SimpleNamespace(voice_enabled=True, llm_api_key="")
        assert voice_ready(config) is False

    def test_voice_ready_enabled_with_key_is_true(self) -> None:
        from telegram_bot.handlers.demo_handler import voice_ready

        config = SimpleNamespace(voice_enabled=True, llm_api_key="sk-test")
        assert voice_ready(config) is True

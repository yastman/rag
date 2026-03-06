"""Tests for tracing_context — make_session_id and classify_action."""

from __future__ import annotations

from unittest.mock import MagicMock

from telegram_bot.tracing_context import classify_action, make_session_id


class TestMakeSessionId:
    def test_format(self):
        result = make_session_id("chat", 12345)
        parts = result.split("-")
        assert parts[0] == "chat"
        assert len(parts[1]) == 8  # sha256[:8]
        assert len(parts[2]) == 8  # YYYYMMDD

    def test_deterministic_hash(self):
        a = make_session_id("chat", 42)
        b = make_session_id("chat", 42)
        assert a == b

    def test_different_ids_differ(self):
        a = make_session_id("chat", 1)
        b = make_session_id("chat", 2)
        assert a != b

    def test_string_identifier(self):
        result = make_session_id("voice", "user-abc")
        assert result.startswith("voice-")


class TestClassifyAction:
    def test_callback_with_prefix(self):
        event = MagicMock(spec=["data"])
        event.__class__ = type("CallbackQuery", (), {})
        # Use real CallbackQuery-like object
        from aiogram.types import CallbackQuery

        cb = MagicMock(spec=CallbackQuery)
        cb.data = "svc:passive_income"
        assert classify_action(cb) == "callback-svc"

    def test_callback_without_prefix(self):
        from aiogram.types import CallbackQuery

        cb = MagicMock(spec=CallbackQuery)
        cb.data = "approve"
        assert classify_action(cb) == "callback"

    def test_callback_empty_data(self):
        from aiogram.types import CallbackQuery

        cb = MagicMock(spec=CallbackQuery)
        cb.data = ""
        assert classify_action(cb) == "callback"

    def test_message_command(self):
        from aiogram.types import Message

        msg = MagicMock(spec=Message)
        msg.text = "/start"
        assert classify_action(msg) == "cmd-start"

    def test_message_command_with_bot_mention(self):
        from aiogram.types import Message

        msg = MagicMock(spec=Message)
        msg.text = "/help@mybot"
        assert classify_action(msg) == "cmd-help"

    def test_message_text(self):
        from aiogram.types import Message

        msg = MagicMock(spec=Message)
        msg.text = "Привет!"
        assert classify_action(msg) == "message"

    def test_unknown_event(self):
        assert classify_action(MagicMock()) == "update"

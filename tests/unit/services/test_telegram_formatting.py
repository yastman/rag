from __future__ import annotations

from types import SimpleNamespace

from telegram_bot.services.generation.telegram_formatting import build_reply_parameters


def test_build_reply_parameters_returns_none_for_multiline_text() -> None:
    message = SimpleNamespace(message_id=42)
    user_text = "Первая строка\nВторая <строка>  с  пробелами?\nТретья строка"

    reply_parameters = build_reply_parameters(message, user_text)

    assert reply_parameters is None


def test_build_reply_parameters_returns_none_for_long_text() -> None:
    message = SimpleNamespace(message_id=42)
    user_text = "Очень длинный вопрос? " + ("данные " * 80)

    reply_parameters = build_reply_parameters(message, user_text)

    assert reply_parameters is None

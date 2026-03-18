from __future__ import annotations

import html
from types import SimpleNamespace

from telegram_bot.services.telegram_formatting import (
    _QUOTE_MAX_LEN,
    build_reply_parameters,
)


def test_build_reply_parameters_preserves_exact_substring_for_multiline_text() -> None:
    message = SimpleNamespace(message_id=42)
    user_text = "Первая строка\nВторая <строка>  с  пробелами?\nТретья строка"

    reply_parameters = build_reply_parameters(message, user_text)

    assert reply_parameters is not None
    assert reply_parameters.message_id == 42
    assert reply_parameters.quote_parse_mode == "HTML"
    assert reply_parameters.quote == html.escape(user_text, quote=False)


def test_build_reply_parameters_truncates_without_ellipsis() -> None:
    message = SimpleNamespace(message_id=42)
    user_text = "Очень длинный вопрос? " + ("данные " * 80)

    reply_parameters = build_reply_parameters(message, user_text)

    assert reply_parameters is not None
    assert not reply_parameters.quote.endswith("...")

    unescaped_quote = html.unescape(reply_parameters.quote)
    assert len(unescaped_quote) == _QUOTE_MAX_LEN
    assert user_text.startswith(unescaped_quote)

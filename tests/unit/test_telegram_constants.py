"""Shared Telegram bot constant contracts."""

from __future__ import annotations


def test_shared_telegram_constants_are_exported() -> None:
    from telegram_bot.constants import STALE_RESULTS_CALLBACK_TEXT, TELEGRAM_MESSAGE_LIMIT

    assert TELEGRAM_MESSAGE_LIMIT == 4096
    assert STALE_RESULTS_CALLBACK_TEXT == "Это устаревшая кнопка. Используйте актуальное меню ниже."

"""Constant values used by telegram_bot modules."""

STALE_RESULTS_CALLBACK_TEXT = "Это устаревшая кнопка. Используйте актуальное меню ниже."
TELEGRAM_MESSAGE_LIMIT = 4096


def split_telegram_response(text: str, limit: int = TELEGRAM_MESSAGE_LIMIT) -> list[str]:
    """Split text into Telegram-safe chunks."""
    if not text:
        return []
    if len(text) <= limit:
        return [text]
    return [text[i : i + limit] for i in range(0, len(text), limit)]

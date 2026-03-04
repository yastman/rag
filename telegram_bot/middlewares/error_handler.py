"""Error handler registered on dp.errors router for all event types."""

from __future__ import annotations

import logging

from aiogram import Dispatcher
from aiogram.filters import ExceptionTypeFilter
from aiogram.types import ErrorEvent


logger = logging.getLogger(__name__)

_ERROR_TEXT = (
    "❌ Произошла ошибка при обработке запроса. Попробуйте позже или обратитесь к администратору."
)


async def handle_error(event: ErrorEvent) -> None:
    """Handle any exception raised in an aiogram handler.

    Covers all event types: Message, CallbackQuery, InlineQuery, etc.
    Logs the error and sends a user-friendly reply when possible.
    """
    exception = event.exception
    update = event.update

    logger.error(
        "Error in handler for update %s: %s",
        type(update).__name__,
        exception,
        exc_info=exception,
    )

    # Resolve a message to reply to, if the update carries one.
    message = None
    if update.message is not None:
        message = update.message
    elif update.callback_query is not None and update.callback_query.message is not None:
        message = update.callback_query.message  # type: ignore[assignment]

    if message is not None:
        await message.answer(_ERROR_TEXT)


def setup_error_handler(dp: Dispatcher) -> None:
    """Register handle_error on dp.errors, covering all aiogram event types.

    Args:
        dp: Dispatcher instance
    """
    dp.errors.register(handle_error, ExceptionTypeFilter(Exception))
    logger.info("Error handler registered via dp.errors")

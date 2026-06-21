"""Error handler registered on dp.errors router for all event types."""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware, Dispatcher
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import ExceptionTypeFilter
from aiogram.types import ErrorEvent, Message, TelegramObject
from aiogram_dialog.api.exceptions import UnknownIntent


logger = logging.getLogger(__name__)

_ERROR_TEXT = (
    "❌ Произошла ошибка при обработке запроса. Попробуйте позже или обратитесь к администратору."
)
_STALE_DIALOG_TEXT = "Это устаревшая кнопка. Используйте актуальное меню ниже."


class ErrorHandlerMiddleware(BaseMiddleware):
    """Backward-compatible middleware wrapper for legacy imports/tests."""

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        try:
            return await handler(event, data)
        except Exception as exc:
            logger.error(
                "Error in handler for event %s: %s",
                type(event).__name__,
                exc,
                exc_info=True,
            )
            if isinstance(event, Message):
                await event.answer(_ERROR_TEXT)
            raise


async def _answer_callback_safe(callback_query: Any, text: str | None = None) -> None:
    """Answer callback query, swallowing expired/invalid query errors silently."""
    try:
        if text is not None:
            await callback_query.answer(text)
        else:
            await callback_query.answer()
    except TelegramBadRequest as exc:
        if "query is too old" in str(exc) or "query ID is invalid" in str(exc):
            logger.debug("Skipping expired callback query answer in error handler")
        else:
            logger.warning("Failed to answer callback query in error handler", exc_info=True)
    except Exception:
        logger.warning("Failed to answer callback query in error handler", exc_info=True)


async def _handle_stale_dialog(callback_query: Any) -> None:
    """Handle a stale aiogram-dialog UnknownIntent via callback_query."""
    if callback_query is None:
        return
    await _answer_callback_safe(callback_query, _STALE_DIALOG_TEXT)
    if callback_query.message is not None and hasattr(callback_query.message, "delete"):
        try:
            await callback_query.message.delete()
        except TelegramBadRequest:
            logger.debug("Failed to delete stale dialog message", exc_info=True)
        except Exception:
            logger.debug("Unexpected failure while deleting stale dialog message", exc_info=True)


def _resolve_reply_message(update: Any, callback_query: Any) -> Any:
    """Return the message to reply to, or None."""
    if update.message is not None:
        return update.message
    if callback_query is not None and callback_query.message is not None:
        return callback_query.message  # type: ignore[return-value]
    return None


async def handle_error(event: ErrorEvent) -> None:
    """Handle any exception raised in an aiogram handler.

    Covers all event types: Message, CallbackQuery, InlineQuery, etc.
    Logs the error and sends a user-friendly reply when possible.
    """
    exception = event.exception
    update = event.update
    callback_query = update.callback_query

    if isinstance(exception, UnknownIntent):
        logger.warning(
            "Stale aiogram-dialog callback for update %s: %s",
            type(update).__name__,
            exception,
        )
        await _handle_stale_dialog(callback_query)
        return

    logger.error(
        "Error in handler for update %s: %s",
        type(update).__name__,
        exception,
        exc_info=exception,
    )

    if callback_query is not None:
        await _answer_callback_safe(callback_query)

    message = _resolve_reply_message(update, callback_query)
    if message is not None:
        await message.answer(_ERROR_TEXT)


def setup_error_handler(dp: Dispatcher) -> None:
    """Register handle_error on dp.errors, covering all aiogram event types.

    Args:
        dp: Dispatcher instance
    """
    dp.errors.register(handle_error, ExceptionTypeFilter(Exception))
    logger.info("Error handler registered via dp.errors")


def setup_error_middleware(dp: Dispatcher) -> None:
    """Backward-compatible legacy registration helper."""
    dp.message.outer_middleware.register(ErrorHandlerMiddleware())
    logger.info("Error handling middleware registered")

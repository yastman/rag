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

        if callback_query is not None:
            try:
                await callback_query.answer(_STALE_DIALOG_TEXT)
            except TelegramBadRequest as exc:
                if "query is too old" in str(exc) or "query ID is invalid" in str(exc):
                    logger.debug("Skipping stale callback answer for expired query")
                else:
                    logger.warning("Failed to answer stale callback query", exc_info=True)
            except Exception:
                logger.warning("Failed to answer stale callback query", exc_info=True)

            if callback_query.message is not None and hasattr(callback_query.message, "delete"):
                try:
                    await callback_query.message.delete()
                except TelegramBadRequest:
                    logger.debug("Failed to delete stale dialog message", exc_info=True)
                except Exception:
                    logger.debug(
                        "Unexpected failure while deleting stale dialog message", exc_info=True
                    )

        return

    logger.error(
        "Error in handler for update %s: %s",
        type(update).__name__,
        exception,
        exc_info=exception,
    )

    # Report error to Langfuse if trace is active
    try:
        from telegram_bot.observability import get_client

        lf = get_client()
        if lf is not None and lf.get_current_trace_id():
            status_message = f"{type(exception).__name__}: {str(exception)[:200]}"
            update_observation = getattr(lf, "update_current_observation", None)
            if callable(update_observation):
                update_observation(level="ERROR", status_message=status_message)
            else:
                update_span = getattr(lf, "update_current_span", None)
                if callable(update_span):
                    update_span(level="ERROR", status_message=status_message)
                else:
                    update_generation = getattr(lf, "update_current_generation", None)
                    if callable(update_generation):
                        update_generation(level="ERROR", status_message=status_message)
    except Exception:
        logger.debug("Failed to report error to Langfuse", exc_info=True)

    if callback_query is not None:
        try:
            await callback_query.answer()
        except TelegramBadRequest as exc:
            if "query is too old" in str(exc) or "query ID is invalid" in str(exc):
                logger.debug("Skipping expired callback query answer in error handler")
            else:
                logger.warning("Failed to answer callback query in error handler", exc_info=True)
        except Exception:
            logger.warning("Failed to answer callback query in error handler", exc_info=True)

    # Resolve a message to reply to, if the update carries one.
    message = None
    if update.message is not None:
        message = update.message
    elif callback_query is not None and callback_query.message is not None:
        message = callback_query.message  # type: ignore[assignment]

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

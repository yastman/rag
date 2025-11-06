"""Error handling middleware for bot."""

from __future__ import annotations

import logging
from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware, Dispatcher
from aiogram.types import Message, TelegramObject

logger = logging.getLogger(__name__)


class ErrorHandlerMiddleware(BaseMiddleware):
    """
    Middleware for centralized error handling.

    Catches exceptions in handlers and provides user-friendly error messages.
    """

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        """Process event with error handling."""
        try:
            return await handler(event, data)
        except Exception as e:
            logger.error(
                f"Error in handler for event {type(event).__name__}: {e}",
                exc_info=True,
            )

            # Send user-friendly error message
            if isinstance(event, Message):
                await event.answer(
                    "❌ Произошла ошибка при обработке запроса. "
                    "Попробуйте позже или обратитесь к администратору."
                )

            # Re-raise to allow error router to handle if needed
            raise


def setup_error_middleware(dp: Dispatcher) -> None:
    """
    Setup error handling middleware.

    Args:
        dp: Dispatcher instance
    """
    middleware = ErrorHandlerMiddleware()
    dp.message.outer_middleware.register(middleware)
    logger.info("Error handling middleware registered")

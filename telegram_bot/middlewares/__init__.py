"""Middlewares for bot."""

from .error_handler import (
    ErrorHandlerMiddleware,
    handle_error,
    setup_error_handler,
    setup_error_middleware,
)
from .i18n import I18nMiddleware, create_translator_hub, setup_i18n_middleware
from .throttling import ThrottlingMiddleware, setup_throttling_middleware


__all__ = [
    "ErrorHandlerMiddleware",
    "I18nMiddleware",
    "ThrottlingMiddleware",
    "create_translator_hub",
    "handle_error",
    "setup_error_handler",
    "setup_error_middleware",
    "setup_i18n_middleware",
    "setup_throttling_middleware",
]

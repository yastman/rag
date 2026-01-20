"""Middlewares for bot."""

from .error_handler import ErrorHandlerMiddleware, setup_error_middleware
from .throttling import ThrottlingMiddleware, setup_throttling_middleware


__all__ = [
    "ErrorHandlerMiddleware",
    "ThrottlingMiddleware",
    "setup_error_middleware",
    "setup_throttling_middleware",
]

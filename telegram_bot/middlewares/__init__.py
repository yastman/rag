"""Middlewares for bot."""

from .throttling import ThrottlingMiddleware, setup_throttling_middleware
from .error_handler import ErrorHandlerMiddleware, setup_error_middleware

__all__ = [
    "ThrottlingMiddleware",
    "setup_throttling_middleware",
    "ErrorHandlerMiddleware",
    "setup_error_middleware",
]

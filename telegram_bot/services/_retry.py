"""Shared retry decorators for HTTP clients.

Re-exports from src.services._retry for backward compatibility.
"""

from src.services._retry import (
    RETRYABLE_HTTP_STATUS_CODES,
    RETRYABLE_TRANSPORT_ERRORS,
    bge_retry,
    kommo_retry,
    make_retry_decorator,
)


__all__ = [
    "RETRYABLE_HTTP_STATUS_CODES",
    "RETRYABLE_TRANSPORT_ERRORS",
    "bge_retry",
    "kommo_retry",
    "make_retry_decorator",
]

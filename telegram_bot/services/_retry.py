"""Shared retry decorators for HTTP clients.

Consolidates retry logic from kommo_client and bge_m3_client.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any, TypeVar

import httpx
from tenacity import (
    before_sleep_log,
    retry,
    retry_if_exception,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential_jitter,
)


logger = logging.getLogger(__name__)
RetryWrappedFn = TypeVar("RetryWrappedFn", bound=Callable[..., Any])

# Transient transport errors worth retrying
RETRYABLE_TRANSPORT_ERRORS = (
    httpx.RemoteProtocolError,
    httpx.ConnectError,
    httpx.ReadTimeout,
    httpx.ConnectTimeout,
    httpx.PoolTimeout,
)

# Kommo-specific: also retry on certain HTTP status codes
RETRYABLE_HTTP_STATUS_CODES = frozenset({429, 500, 502, 503, 504})


def _retryable_http_status(exc: BaseException) -> bool:
    if not isinstance(exc, httpx.HTTPStatusError):
        return False
    return exc.response.status_code in RETRYABLE_HTTP_STATUS_CODES


def make_retry_decorator(
    *,
    retry_on_http_status: bool = False,
    initial: float = 1.0,
    max_: float = 8.0,
    jitter: float = 2.0,
    max_attempts: int = 3,
) -> Callable[[RetryWrappedFn], RetryWrappedFn]:
    """Factory for retry decorators with common configuration.

    Args:
        retry_on_http_status: Include HTTP 5xx/429 status codes
        initial: Initial wait time in seconds
        max_: Maximum wait time in seconds
        jitter: Maximum jitter in seconds
        max_attempts: Maximum retry attempts
    """
    retry_predicate: Any = retry_if_exception_type(RETRYABLE_TRANSPORT_ERRORS)
    if retry_on_http_status:
        retry_predicate = retry_predicate | retry_if_exception(_retryable_http_status)

    return retry(
        retry=retry_predicate,
        wait=wait_exponential_jitter(initial=initial, max=max_, jitter=jitter),
        stop=stop_after_attempt(max_attempts),
        before_sleep=before_sleep_log(logger, logging.WARNING),
        reraise=True,
    )


# Convenience decorators matching original configurations
kommo_retry = make_retry_decorator(
    retry_on_http_status=True,
    initial=1,
    max_=8,
    jitter=2,
    max_attempts=3,
)

bge_retry = make_retry_decorator(
    retry_on_http_status=False,
    initial=0.5,
    max_=4,
    jitter=1,
    max_attempts=3,
)

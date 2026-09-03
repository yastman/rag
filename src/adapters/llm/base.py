"""Normalized LLM error types shared by runtime consumers."""

from __future__ import annotations


class LLMError(Exception):
    """Generic error raised by LLM providers."""

    def __init__(
        self,
        message: str,
        error_type: str = "api_error",
        raw_error: Exception | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.error_type = error_type
        self.raw_error = raw_error


class LLMAuthenticationError(LLMError):
    """Authentication or API key error raised by LLM providers."""

    def __init__(self, message: str, raw_error: Exception | None = None) -> None:
        super().__init__(message, error_type="authentication_error", raw_error=raw_error)


class LLMRateLimitError(LLMError):
    """Rate limit or quota exhaustion error raised by LLM providers."""

    def __init__(self, message: str, raw_error: Exception | None = None) -> None:
        super().__init__(message, error_type="rate_limit_error", raw_error=raw_error)


class LLMTimeoutError(LLMError):
    """Timeout error raised by LLM providers."""

    def __init__(self, message: str, raw_error: Exception | None = None) -> None:
        super().__init__(message, error_type="timeout_error", raw_error=raw_error)


class LLMConnectionError(LLMError):
    """Connection or network error raised by LLM providers."""

    def __init__(self, message: str, raw_error: Exception | None = None) -> None:
        super().__init__(message, error_type="connection_error", raw_error=raw_error)

"""Log context propagation via ContextVar for structured observability."""

from __future__ import annotations

import logging
from contextvars import ContextVar
from typing import Any


_observability_context: ContextVar[dict[str, Any]] = ContextVar(
    "_observability_context",
)


def set_log_context(**kwargs: Any) -> None:
    """Update the observability context with provided non-None values."""
    current = _observability_context.get({}).copy()
    for key, value in kwargs.items():
        if value is not None:
            current[key] = value
    _observability_context.set(current)


def clear_log_context() -> None:
    """Reset the observability context to an empty dict."""
    _observability_context.set({})


def get_log_context() -> dict[str, Any]:
    """Return the current observability context dict."""
    return _observability_context.get({})


class ObservabilityLogFilter(logging.Filter):
    """Logging filter that injects observability context into log records."""

    def filter(self, record: logging.LogRecord) -> bool:
        """Inject context fields onto the log record. Always returns True."""
        context = _observability_context.get({})
        for key, value in context.items():
            setattr(record, key, value)
        return True

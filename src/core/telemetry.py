"""SDK-friendly telemetry dispatch for core/runtime product events."""

from __future__ import annotations

import logging
from typing import Any


_LOGGER = logging.getLogger("src.core.telemetry")


def emit_product_event(telemetry: object | None, event: str, **fields: Any) -> None:
    """Emit a product event via an injected listener or standard logging.

    The SDK core no longer imports the repository-level ``log_event`` helper
    directly. Host applications can pass ``CoreDependencies.telemetry`` with a
    ``log_event(event, **fields)`` method; otherwise events are emitted through
    Python's standard logging with sanitized structured extras.
    """

    if telemetry is not None:
        log_event = getattr(telemetry, "log_event", None)
        if callable(log_event):
            log_event(event, **fields)
            return

    extra = {"event": event, **fields}
    _LOGGER.info(event, extra=extra)

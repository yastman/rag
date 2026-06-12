"""SDK-friendly telemetry dispatch for core/runtime product events."""

from __future__ import annotations

import logging
from typing import Any

from src.utils.product_events import log_event as _product_log_event


_LOGGER = logging.getLogger(__name__)


def emit_product_event(telemetry: object | None, event: str, **fields: Any) -> None:
    """Emit a product event via an injected listener or safe JSON-log fallback.

    Host applications can pass ``CoreDependencies.telemetry`` with a
    ``log_event(event, **fields)`` method. Listener failures are fail-open: the
    assistant request path must continue, and the event falls back to the
    existing product log helper so allowlist-based PII/secret filtering remains
    in force.
    """

    if telemetry is not None:
        telemetry_log_event = getattr(telemetry, "log_event", None)
        if callable(telemetry_log_event):
            try:
                telemetry_log_event(event, **fields)
                return
            except Exception:
                _LOGGER.warning(
                    "Telemetry listener failed; falling back to product event log",
                    exc_info=True,
                )

    _product_log_event(event, **fields)

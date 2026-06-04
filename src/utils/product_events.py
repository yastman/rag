"""Minimal product event logging helper — no Langfuse / OTel / FastAPI / Telegram deps.

Provides:

- :func:`log_event` — typed helper that emits a structured JSON log line via
  standard :mod:`logging` at ``INFO`` level.
- :class:`ProductEventsFormatter` — :class:`logging.Formatter` subclass that
  serialises event metadata as flat JSON (one event per line).

Falsy values (``0``, ``False``, ``None``) are preserved in the output.
"""

from __future__ import annotations

import json
import logging
from typing import Any


# Standard :class:`logging.LogRecord` constructor parameter names.
# Any attribute NOT in this set that is present on the record is treated as
# product-level metadata and serialised into the JSON output.
_STANDARD_LOG_ATTRS: frozenset[str] = frozenset(
    {
        "args",
        "asctime",
        "created",
        "exc_info",
        "exc_text",
        "filename",
        "funcName",
        "levelname",
        "levelno",
        "lineno",
        "message",
        "module",
        "msecs",
        "msg",
        "name",
        "pathname",
        "process",
        "processName",
        "relativeCreated",
        "stack_info",
        "thread",
        "threadName",
        "taskName",
    }
)

# ---------------------------------------------------------------------------
# Known product-event field names (additive-only to keep scope small).
# log_event silently ignores keys not in this set so callers cannot
# accidentally log arbitrary PII / secrets by passing stray kwargs.
# ---------------------------------------------------------------------------
_PRODUCT_FIELDS: frozenset[str] = frozenset(
    {
        "event",
        "request_id",
        "route",
        "request_type",
        "latency_ms",
        "error_type",
        "retrieved_doc_ids",
        "llm_model",
        "input_tokens",
        "output_tokens",
    }
)


class ProductEventsFormatter(logging.Formatter):
    """JSON formatter that preserves falsy product-event fields.

    Output is a single JSON object per log line, suitable for structured-log
    consumers (e.g. ``jq``, Loki).
    """

    def format(self, record: logging.LogRecord) -> str:
        """Render *record* as a JSON string."""
        log_data: dict[str, Any] = {
            "timestamp": self.formatTime(record, self.datefmt),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
        }

        # Attach every non-standard LogRecord attribute — this is how
        # ``extra={...}`` fields reach the formatter.  hasattr + getattr
        # is used instead of ``record.__dict__`` so that falsy values
        # (0, False, None) survive; ``record.__dict__.get(k)`` would drop
        # None for unset optional fields on LogRecord itself.
        for attr in dir(record):
            if attr in _STANDARD_LOG_ATTRS or attr.startswith("_"):
                continue
            if hasattr(record, attr):
                log_data[attr] = getattr(record, attr)

        # Include exception info when present.
        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)

        return json.dumps(log_data, ensure_ascii=False, default=str)


# Module-level logger — no pre-configured handler so callers retain full
# control over routing (pytest caplog, file sinks, etc.).
_logger = logging.getLogger("src.utils.product_events")
_logger.setLevel(logging.INFO)


def log_event(event: str, **fields: Any) -> None:
    """Emit a structured product event as a JSON log line at ``INFO`` level.

    Args:
        event: Machine-readable event name (e.g. ``"query_executed"``).
        **fields: Optional key-value pairs. Supported keys are those listed
            in ``_PRODUCT_FIELDS``; unknown keys are ignored silently so
            callers cannot accidentally log arbitrary PII/secrets.

    Example::

        log_event("query_executed", request_id="req-1", latency_ms=42.5)
    """
    extra: dict[str, Any] = {
        "event": event,
        **{k: v for k, v in fields.items() if k in _PRODUCT_FIELDS},
    }

    # Extra dict keys become LogRecord attributes when passed via ``extra=``.
    _logger.info(event, extra=extra)

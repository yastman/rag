"""Structured JSON logging configuration for production observability."""

import json
import logging
import sys
from datetime import UTC, datetime
from typing import Any


class JSONFormatter(logging.Formatter):
    """
    JSON formatter for structured logging.

    Outputs logs in JSON format for easy parsing by log aggregation tools
    (ELK, Grafana Loki, CloudWatch, etc.).
    """

    def format(self, record: logging.LogRecord) -> str:
        """
        Format log record as JSON.

        Args:
            record: Log record to format

        Returns:
            JSON-formatted log string
        """
        log_data: dict[str, Any] = {
            "timestamp": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
        }

        # Logs <-> Traces correlation (#2217 / Epic G).
        # ``opentelemetry.instrumentation.logging.LoggingInstrumentor`` (activated
        # in src/observability_otel.py per #2225) injects ``otelTraceID`` and
        # ``otelSpanID`` into every LogRecord from the active OTEL context.
        # Langfuse v4 SDK runs on top of OTEL, so these IDs match
        # ``langfuse.get_current_trace_id()`` / ``get_current_observation_id()``
        # — the same values that:
        #   * land in Sentry events as ``langfuse_trace_id`` tag (#2218);
        #   * carry ``traceparent`` across HTTP boundaries (#2225 + #2226).
        # The OTEL "no active trace" sentinel is the literal string ``"0"``
        # — treat it as absence so Loki queries can use ``| trace_id != ""``
        # without matching every line.
        otel_trace_id = getattr(record, "otelTraceID", None)
        if otel_trace_id and otel_trace_id != "0":
            log_data["trace_id"] = otel_trace_id
        otel_span_id = getattr(record, "otelSpanID", None)
        if otel_span_id and otel_span_id != "0":
            log_data["span_id"] = otel_span_id

        # Add exception info if present
        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)

        # Add extra fields from record
        if hasattr(record, "user_id"):
            log_data["user_id"] = record.user_id
        if hasattr(record, "query"):
            log_data["query"] = record.query
        if hasattr(record, "latency_ms"):
            log_data["latency_ms"] = record.latency_ms
        if hasattr(record, "cache_hit"):
            log_data["cache_hit"] = record.cache_hit
        if hasattr(record, "service"):
            log_data["service"] = record.service

        return json.dumps(log_data, ensure_ascii=False)


def setup_logging(
    level: str = "INFO",
    json_format: bool = True,
    log_file: str | None = None,
) -> None:
    """
    Setup structured logging for the application.

    Args:
        level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        json_format: Use JSON format (True) or plain text (False)
        log_file: Optional file path to write logs to
    """
    # Get root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(level)

    # Remove existing handlers
    for handler in list(root_logger.handlers):
        handler.close()
        root_logger.removeHandler(handler)

    # Create console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(level)

    # Set formatter
    formatter: logging.Formatter
    if json_format:
        formatter = JSONFormatter()
    else:
        formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")

    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)

    # Add file handler if specified
    if log_file:
        file_handler = logging.FileHandler(log_file, encoding="utf-8")
        file_handler.setLevel(level)
        file_handler.setFormatter(formatter)
        root_logger.addHandler(file_handler)

    # Set third-party loggers to WARNING to reduce noise
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("aiogram").setLevel(logging.INFO)
    logging.getLogger("aiogram_dialog").setLevel(logging.WARNING)
    logging.getLogger("aiogram_dialog.manager").setLevel(logging.WARNING)
    logging.getLogger("aiogram_dialog.manager.message_manager").setLevel(logging.WARNING)
    logging.getLogger("qdrant_client").setLevel(logging.WARNING)

    logging.info(
        f"Logging configured: level={level}, json_format={json_format}, "
        f"log_file={log_file or 'None'}"
    )

"""Structured JSON logging configuration for production observability."""

import json
import logging
import os
import sys
from datetime import UTC, datetime
from typing import Any


# Read release version once at module load
_RELEASE: str = os.environ.get("SENTRY_RELEASE", "")

# Fields that must never appear in log output (PII / secrets)
_PII_BLOCKED_KEYS: frozenset[str] = frozenset(
    {"user_id", "query", "phone", "email", "token", "password", "secret"}
)

# Optional observability fields to propagate when non-None
_OPTIONAL_FIELDS: tuple[str, ...] = (
    "component",
    "event",
    "release",
    "trace_id",
    "langfuse_trace_id",
    "request_id",
    "telegram_user_id_hash",
    "chat_id_hash",
    "tenant_id",
    "bot_instance_id",
    "deployment_id",
    "route",
    "pipeline_mode",
    "llm_model",
    "dependency_status",
    "error_type",
)


class JSONFormatter(logging.Formatter):
    """
    JSON formatter for structured logging.

    Outputs logs in JSON format for easy parsing by log aggregation tools
    (ELK, Grafana Loki, CloudWatch, etc.).
    """

    SERVICE_DEFAULT: str = "telegram-bot"

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

        # Always include service and environment
        log_data["service"] = getattr(record, "service", None) or self.SERVICE_DEFAULT
        log_data["environment"] = os.environ.get("ENV", "development")

        # Add exception info if present
        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)

        # Safe operational metrics
        if hasattr(record, "latency_ms"):
            log_data["latency_ms"] = record.latency_ms
        if hasattr(record, "cache_hit"):
            log_data["cache_hit"] = record.cache_hit

        # Optional observability fields (only when non-None)
        for field in _OPTIONAL_FIELDS:
            value = getattr(record, field, None)
            if value is not None:
                log_data[field] = value

        # Inject release from module-level constant if not already set
        if "release" not in log_data and _RELEASE:
            log_data["release"] = _RELEASE

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

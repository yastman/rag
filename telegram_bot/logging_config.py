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
    root_logger.handlers.clear()

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
    logging.getLogger("qdrant_client").setLevel(logging.WARNING)

    logging.info(
        f"Logging configured: level={level}, json_format={json_format}, "
        f"log_file={log_file or 'None'}"
    )


class StructuredLogger:
    """
    Wrapper for logging with structured context.

    Makes it easy to add contextual fields to log messages.
    """

    def __init__(self, name: str):
        """
        Initialize structured logger.

        Args:
            name: Logger name (usually __name__)
        """
        self.logger = logging.getLogger(name)

    def info(self, message: str, **kwargs):
        """Log info with extra context."""
        self.logger.info(message, extra=kwargs)

    def warning(self, message: str, **kwargs):
        """Log warning with extra context."""
        self.logger.warning(message, extra=kwargs)

    def error(self, message: str, exc_info: bool = False, **kwargs):
        """Log error with extra context."""
        self.logger.error(message, exc_info=exc_info, extra=kwargs)

    def debug(self, message: str, **kwargs):
        """Log debug with extra context."""
        self.logger.debug(message, extra=kwargs)


# Example usage:
# from telegram_bot.logging_config import setup_logging, StructuredLogger
#
# # Setup at application start
# setup_logging(level="INFO", json_format=True)
#
# # Use in modules
# logger = StructuredLogger(__name__)
# logger.info("User query received", user_id=123, query="apartments", latency_ms=45.3)
#
# Output:
# {
#   "timestamp": "2025-01-06T12:34:56.789Z",
#   "level": "INFO",
#   "logger": "telegram_bot.bot",
#   "message": "User query received",
#   "user_id": 123,
#   "query": "apartments",
#   "latency_ms": 45.3
# }

"""Unit tests for telegram_bot/logging_config.py."""

import json
import logging
import tempfile
from unittest.mock import patch

from telegram_bot.logging_config import JSONFormatter, StructuredLogger, setup_logging


class TestJSONFormatter:
    """Test JSONFormatter class."""

    def test_format_basic_record(self):
        """Test formatting a basic log record."""
        formatter = JSONFormatter()

        record = logging.LogRecord(
            name="test.logger",
            level=logging.INFO,
            pathname="/test/path.py",
            lineno=42,
            msg="Test message",
            args=(),
            exc_info=None,
        )

        result = formatter.format(record)
        data = json.loads(result)

        assert data["level"] == "INFO"
        assert data["logger"] == "test.logger"
        assert data["message"] == "Test message"
        assert data["line"] == 42
        assert "timestamp" in data
        assert data["timestamp"].endswith("Z")

    def test_format_record_with_args(self):
        """Test formatting record with message arguments."""
        formatter = JSONFormatter()

        record = logging.LogRecord(
            name="test",
            level=logging.WARNING,
            pathname="/test.py",
            lineno=10,
            msg="Value is %s",
            args=("hello",),
            exc_info=None,
        )

        result = formatter.format(record)
        data = json.loads(result)

        assert data["message"] == "Value is hello"
        assert data["level"] == "WARNING"

    def test_format_record_with_exception(self):
        """Test formatting record with exception info."""
        formatter = JSONFormatter()

        try:
            raise ValueError("Test error")
        except ValueError:
            import sys

            exc_info = sys.exc_info()

        record = logging.LogRecord(
            name="test",
            level=logging.ERROR,
            pathname="/test.py",
            lineno=20,
            msg="An error occurred",
            args=(),
            exc_info=exc_info,
        )

        result = formatter.format(record)
        data = json.loads(result)

        assert data["level"] == "ERROR"
        assert "exception" in data
        assert "ValueError: Test error" in data["exception"]

    def test_format_record_with_user_id(self):
        """Test formatting record with user_id extra field."""
        formatter = JSONFormatter()

        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="/test.py",
            lineno=5,
            msg="User action",
            args=(),
            exc_info=None,
        )
        record.user_id = 12345

        result = formatter.format(record)
        data = json.loads(result)

        assert data["user_id"] == 12345

    def test_format_record_with_query(self):
        """Test formatting record with query extra field."""
        formatter = JSONFormatter()

        record = logging.LogRecord(
            name="test",
            level=logging.DEBUG,
            pathname="/test.py",
            lineno=5,
            msg="Query received",
            args=(),
            exc_info=None,
        )
        record.query = "apartments in Varna"

        result = formatter.format(record)
        data = json.loads(result)

        assert data["query"] == "apartments in Varna"

    def test_format_record_with_latency_ms(self):
        """Test formatting record with latency_ms extra field."""
        formatter = JSONFormatter()

        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="/test.py",
            lineno=5,
            msg="Request completed",
            args=(),
            exc_info=None,
        )
        record.latency_ms = 123.45

        result = formatter.format(record)
        data = json.loads(result)

        assert data["latency_ms"] == 123.45

    def test_format_record_with_cache_hit(self):
        """Test formatting record with cache_hit extra field."""
        formatter = JSONFormatter()

        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="/test.py",
            lineno=5,
            msg="Cache check",
            args=(),
            exc_info=None,
        )
        record.cache_hit = True

        result = formatter.format(record)
        data = json.loads(result)

        assert data["cache_hit"] is True

    def test_format_record_with_service(self):
        """Test formatting record with service extra field."""
        formatter = JSONFormatter()

        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="/test.py",
            lineno=5,
            msg="Service call",
            args=(),
            exc_info=None,
        )
        record.service = "voyage"

        result = formatter.format(record)
        data = json.loads(result)

        assert data["service"] == "voyage"

    def test_format_record_with_all_extra_fields(self):
        """Test formatting record with all extra fields."""
        formatter = JSONFormatter()

        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="/test.py",
            lineno=5,
            msg="Full context",
            args=(),
            exc_info=None,
        )
        record.user_id = 99
        record.query = "test"
        record.latency_ms = 50.0
        record.cache_hit = False
        record.service = "qdrant"

        result = formatter.format(record)
        data = json.loads(result)

        assert data["user_id"] == 99
        assert data["query"] == "test"
        assert data["latency_ms"] == 50.0
        assert data["cache_hit"] is False
        assert data["service"] == "qdrant"

    def test_format_unicode_message(self):
        """Test formatting record with unicode characters."""
        formatter = JSONFormatter()

        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="/test.py",
            lineno=5,
            msg="Квартиры в Варне",
            args=(),
            exc_info=None,
        )

        result = formatter.format(record)
        data = json.loads(result)

        assert data["message"] == "Квартиры в Варне"


class TestSetupLogging:
    """Test setup_logging function."""

    @staticmethod
    def _close_root_handlers() -> None:
        """Close and remove all root handlers to avoid ResourceWarning leaks."""
        root_logger = logging.getLogger()
        for handler in list(root_logger.handlers):
            handler.close()
            root_logger.removeHandler(handler)

    def setup_method(self):
        """Reset root logger before each test."""
        self._close_root_handlers()
        logging.getLogger().setLevel(logging.WARNING)

    def teardown_method(self):
        """Clean up after each test."""
        self._close_root_handlers()

    def test_setup_logging_default_settings(self):
        """Test setup with default settings."""
        setup_logging()

        root_logger = logging.getLogger()

        assert root_logger.level == logging.INFO
        assert len(root_logger.handlers) == 1
        assert isinstance(root_logger.handlers[0], logging.StreamHandler)
        assert isinstance(root_logger.handlers[0].formatter, JSONFormatter)

    def test_setup_logging_custom_level(self):
        """Test setup with custom log level."""
        setup_logging(level="DEBUG")

        root_logger = logging.getLogger()

        assert root_logger.level == logging.DEBUG

    def test_setup_logging_warning_level(self):
        """Test setup with WARNING level."""
        setup_logging(level="WARNING")

        root_logger = logging.getLogger()

        assert root_logger.level == logging.WARNING

    def test_setup_logging_plain_text_format(self):
        """Test setup with plain text format."""
        setup_logging(json_format=False)

        root_logger = logging.getLogger()
        formatter = root_logger.handlers[0].formatter

        assert not isinstance(formatter, JSONFormatter)
        assert isinstance(formatter, logging.Formatter)

    def test_setup_logging_with_file(self):
        """Test setup with log file."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".log", delete=False) as f:
            log_file = f.name

        try:
            setup_logging(log_file=log_file)

            root_logger = logging.getLogger()

            # Should have 2 handlers: console + file
            assert len(root_logger.handlers) == 2

            # Find file handler
            file_handler = None
            for handler in root_logger.handlers:
                if isinstance(handler, logging.FileHandler):
                    file_handler = handler
                    break

            assert file_handler is not None
            assert file_handler.baseFilename == log_file
        finally:
            import os

            self._close_root_handlers()
            os.unlink(log_file)

    def test_setup_logging_clears_existing_handlers(self):
        """Test that setup clears existing handlers."""
        root_logger = logging.getLogger()

        # Clear any existing handlers first
        root_logger.handlers.clear()

        # Add some handlers
        root_logger.addHandler(logging.StreamHandler())
        root_logger.addHandler(logging.StreamHandler())
        initial_count = len(root_logger.handlers)
        assert initial_count >= 2

        setup_logging()

        # Should have only 1 handler now (the console handler added by setup_logging)
        assert len(root_logger.handlers) == 1

    def test_setup_logging_sets_third_party_loggers(self):
        """Test that third-party loggers are set to appropriate levels."""
        setup_logging()

        assert logging.getLogger("httpx").level == logging.WARNING
        assert logging.getLogger("httpcore").level == logging.WARNING
        assert logging.getLogger("aiogram").level == logging.INFO
        assert logging.getLogger("aiogram_dialog").level == logging.WARNING
        assert logging.getLogger("aiogram_dialog.manager").level == logging.WARNING
        assert logging.getLogger("aiogram_dialog.manager.message_manager").level == logging.WARNING
        assert logging.getLogger("qdrant_client").level == logging.WARNING

    def test_setup_logging_logs_configuration(self):
        """Test that setup logs its configuration."""
        with patch("telegram_bot.logging_config.logging.info") as mock_info:
            setup_logging(level="DEBUG", json_format=False, log_file="/tmp/test.log")

            # Verify info was called with configuration message
            mock_info.assert_called()
            call_args = mock_info.call_args[0][0]
            assert "DEBUG" in call_args
            assert "json_format=False" in call_args


class TestStructuredLogger:
    """Test StructuredLogger class."""

    def test_init_creates_logger(self):
        """Test that init creates underlying logger."""
        slogger = StructuredLogger("test.module")

        assert slogger.logger.name == "test.module"

    def test_info_logs_message(self):
        """Test info method logs message."""
        slogger = StructuredLogger("test")

        with patch.object(slogger.logger, "info") as mock_info:
            slogger.info("Test message")

            mock_info.assert_called_once()
            assert mock_info.call_args[0][0] == "Test message"

    def test_info_with_extra_kwargs(self):
        """Test info method passes extra kwargs."""
        slogger = StructuredLogger("test")

        with patch.object(slogger.logger, "info") as mock_info:
            slogger.info("Message", user_id=123, latency_ms=45.0)

            mock_info.assert_called_once()
            assert mock_info.call_args[1]["extra"] == {"user_id": 123, "latency_ms": 45.0}

    def test_warning_logs_message(self):
        """Test warning method logs message."""
        slogger = StructuredLogger("test")

        with patch.object(slogger.logger, "warning") as mock_warning:
            slogger.warning("Warning message", service="cache")

            mock_warning.assert_called_once()
            assert mock_warning.call_args[0][0] == "Warning message"
            assert mock_warning.call_args[1]["extra"] == {"service": "cache"}

    def test_error_logs_message(self):
        """Test error method logs message."""
        slogger = StructuredLogger("test")

        with patch.object(slogger.logger, "error") as mock_error:
            slogger.error("Error message", cache_hit=False)

            mock_error.assert_called_once()
            assert mock_error.call_args[0][0] == "Error message"
            assert mock_error.call_args[1]["exc_info"] is False
            assert mock_error.call_args[1]["extra"] == {"cache_hit": False}

    def test_error_with_exc_info(self):
        """Test error method with exc_info=True."""
        slogger = StructuredLogger("test")

        with patch.object(slogger.logger, "error") as mock_error:
            slogger.error("Error with trace", exc_info=True)

            mock_error.assert_called_once()
            assert mock_error.call_args[1]["exc_info"] is True

    def test_debug_logs_message(self):
        """Test debug method logs message."""
        slogger = StructuredLogger("test")

        with patch.object(slogger.logger, "debug") as mock_debug:
            slogger.debug("Debug info", query="test query")

            mock_debug.assert_called_once()
            assert mock_debug.call_args[0][0] == "Debug info"
            assert mock_debug.call_args[1]["extra"] == {"query": "test query"}

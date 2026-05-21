"""Tests for structured JSON log contract in JSONFormatter."""

from __future__ import annotations

import json
import logging
import os
from unittest.mock import patch

import pytest

from telegram_bot.logging_config import JSONFormatter


@pytest.fixture
def formatter() -> JSONFormatter:
    return JSONFormatter()


@pytest.fixture
def log_record() -> logging.LogRecord:
    return logging.LogRecord(
        name="test.logger",
        level=logging.INFO,
        pathname="test.py",
        lineno=42,
        msg="hello world",
        args=None,
        exc_info=None,
    )


class TestJSONFormatterServiceField:
    def test_json_formatter_includes_service_field(
        self, formatter: JSONFormatter, log_record: logging.LogRecord
    ) -> None:
        output = json.loads(formatter.format(log_record))
        assert "service" in output
        assert output["service"] == "telegram-bot"

    def test_json_formatter_uses_record_service_if_set(
        self, formatter: JSONFormatter, log_record: logging.LogRecord
    ) -> None:
        log_record.service = "custom-service"  # type: ignore[attr-defined]
        output = json.loads(formatter.format(log_record))
        assert output["service"] == "custom-service"


class TestJSONFormatterEnvironment:
    def test_json_formatter_includes_environment_from_env(
        self, formatter: JSONFormatter, log_record: logging.LogRecord
    ) -> None:
        with patch.dict(os.environ, {"ENV": "staging"}):
            output = json.loads(formatter.format(log_record))
        assert output["environment"] == "staging"

    def test_json_formatter_defaults_environment_to_development(
        self, formatter: JSONFormatter, log_record: logging.LogRecord
    ) -> None:
        with patch.dict(os.environ, {}, clear=True):
            # Remove ENV if present
            os.environ.pop("ENV", None)
            output = json.loads(formatter.format(log_record))
        assert output["environment"] == "development"


class TestJSONFormatterCorrelationIDs:
    def test_json_formatter_includes_correlation_ids_when_set(
        self, formatter: JSONFormatter, log_record: logging.LogRecord
    ) -> None:
        log_record.trace_id = "abc-123"  # type: ignore[attr-defined]
        log_record.langfuse_trace_id = "lf-456"  # type: ignore[attr-defined]
        log_record.request_id = "req-789"  # type: ignore[attr-defined]
        output = json.loads(formatter.format(log_record))
        assert output["trace_id"] == "abc-123"
        assert output["langfuse_trace_id"] == "lf-456"
        assert output["request_id"] == "req-789"


class TestJSONFormatterNoneExclusion:
    def test_json_formatter_excludes_none_fields(
        self, formatter: JSONFormatter, log_record: logging.LogRecord
    ) -> None:
        # Do NOT set any optional fields - they should be absent
        output = json.loads(formatter.format(log_record))
        assert "trace_id" not in output
        assert "langfuse_trace_id" not in output
        assert "component" not in output
        assert "tenant_id" not in output
        assert "error_type" not in output


class TestJSONFormatterPIISafety:
    def test_json_formatter_does_not_propagate_raw_pii(
        self, formatter: JSONFormatter, log_record: logging.LogRecord
    ) -> None:
        # Set PII fields on the record
        log_record.user_id = "12345"  # type: ignore[attr-defined]
        log_record.query = "find me apartments"  # type: ignore[attr-defined]
        log_record.phone = "+1234567890"  # type: ignore[attr-defined]
        log_record.email = "user@example.com"  # type: ignore[attr-defined]
        log_record.token = "secret-token"  # type: ignore[attr-defined]
        log_record.password = "secret-pass"  # type: ignore[attr-defined]
        log_record.secret = "top-secret"  # type: ignore[attr-defined]

        output = json.loads(formatter.format(log_record))
        assert "user_id" not in output
        assert "query" not in output
        assert "phone" not in output
        assert "email" not in output
        assert "token" not in output
        assert "password" not in output
        assert "secret" not in output

"""Tests for src.observability.sentry_integration module."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from src.observability.correlation import build_correlation_context
from src.observability.sentry_integration import (
    _filter_pii,
    initialize_sentry,
    set_sentry_context,
    set_sentry_user,
)


class TestInitializeSentry:
    """Tests for initialize_sentry function."""

    @patch("src.observability.sentry_integration.sentry_sdk.init")
    def test_initialize_sentry_noop_when_dsn_empty(self, mock_init: MagicMock) -> None:
        """When DSN is empty, sentry_sdk.init must NOT be called."""
        initialize_sentry(
            dsn="",
            environment="development",
            release="1.0.0",
            traces_sample_rate=0.0,
        )
        mock_init.assert_not_called()

    @patch("src.observability.sentry_integration.sentry_sdk.init")
    def test_initialize_sentry_calls_init_with_dsn(self, mock_init: MagicMock) -> None:
        """When DSN is provided, sentry_sdk.init must be called with correct params."""
        initialize_sentry(
            dsn="https://key@sentry.io/123",
            environment="production",
            release="2.0.0",
            traces_sample_rate=0.1,
            service_name="test-service",
        )
        mock_init.assert_called_once()
        call_kwargs = mock_init.call_args[1]
        assert call_kwargs["dsn"] == "https://key@sentry.io/123"
        assert call_kwargs["environment"] == "production"
        assert call_kwargs["release"] == "2.0.0"
        assert call_kwargs["traces_sample_rate"] == 0.1
        assert call_kwargs["server_name"] == "test-service"
        assert callable(call_kwargs["before_send"])
        assert callable(call_kwargs["before_breadcrumb"])


class TestFilterPII:
    """Tests for _filter_pii before_send hook."""

    def test_filter_pii_strips_phone_and_email(self) -> None:
        """PII in message and extras must be redacted."""
        event = {
            "message": "User called from +380501234567 and emailed user@example.com",
            "extra": {
                "phone": "+380501234567",
                "email": "test@test.com",
                "safe_key": "no-pii-here",
            },
        }
        filtered = _filter_pii(event, {})
        # Phone and email in message should be redacted
        assert "+380501234567" not in filtered["message"]
        assert "user@example.com" not in filtered["message"]
        # Blocked keys should be [REDACTED]
        assert filtered["extra"]["phone"] == "[REDACTED]"
        assert filtered["extra"]["email"] == "[REDACTED]"
        # Safe key should remain
        assert filtered["extra"]["safe_key"] == "no-pii-here"

    def test_filter_pii_does_not_modify_safe_data(self) -> None:
        """Events without PII should pass through unchanged."""
        event = {
            "message": "System started successfully",
            "extra": {"version": "1.0.0", "uptime": "120s"},
        }
        filtered = _filter_pii(event, {})
        assert filtered["message"] == "System started successfully"
        assert filtered["extra"]["version"] == "1.0.0"
        assert filtered["extra"]["uptime"] == "120s"

    def test_filter_pii_blocked_keys_redacted(self) -> None:
        """All blocked keys must have their values replaced with [REDACTED]."""
        event = {
            "extra": {
                "text": "user message",
                "query": "search query",
                "raw_query": "raw",
                "answer_text": "answer",
                "token": "secret-token",
                "password": "pass123",
                "secret": "shh",
                "api_key": "key-value",
            },
        }
        filtered = _filter_pii(event, {})
        for key in event["extra"]:
            assert filtered["extra"][key] == "[REDACTED]"


class TestSetSentryContext:
    """Tests for set_sentry_context."""

    @patch("src.observability.sentry_integration.sentry_sdk.set_tag")
    @patch("src.observability.sentry_integration.sentry_sdk.set_context")
    def test_set_sentry_context_sets_tags(
        self, mock_set_context: MagicMock, mock_set_tag: MagicMock
    ) -> None:
        """Non-None values should be set as context and tags."""
        set_sentry_context(
            trace_id="abc-123",
            service="telegram-bot",
            component="retrieval",
        )
        mock_set_context.assert_called_once()
        context_data = mock_set_context.call_args[0][1]
        assert context_data["trace_id"] == "abc-123"
        assert context_data["service"] == "telegram-bot"
        assert context_data["component"] == "retrieval"
        # Tags should be set for each non-None value
        tag_calls = {call[0][0]: call[0][1] for call in mock_set_tag.call_args_list}
        assert tag_calls["trace_id"] == "abc-123"
        assert tag_calls["service"] == "telegram-bot"

    @patch("src.observability.sentry_integration.sentry_sdk.set_tag")
    @patch("src.observability.sentry_integration.sentry_sdk.set_context")
    def test_set_sentry_context_skips_none_values(
        self, mock_set_context: MagicMock, mock_set_tag: MagicMock
    ) -> None:
        """None values should not appear in context or tags."""
        set_sentry_context(trace_id="x", langfuse_trace_id=None)
        context_data = mock_set_context.call_args[0][1]
        assert "langfuse_trace_id" not in context_data


class TestSetSentryUser:
    """Tests for set_sentry_user."""

    @patch("src.observability.sentry_integration.sentry_sdk.set_user")
    def test_set_sentry_user_uses_hash(self, mock_set_user: MagicMock) -> None:
        """User dict should contain hashed identifiers."""
        set_sentry_user(
            telegram_user_id_hash="hash-abc",
            chat_id_hash="hash-chat",
        )
        mock_set_user.assert_called_once_with(
            {"id": "hash-abc", "chat_id_hash": "hash-chat"}
        )


class TestBuildCorrelationContext:
    """Tests for build_correlation_context."""

    def test_build_correlation_context_excludes_none(self) -> None:
        """None values should be excluded from the result."""
        result = build_correlation_context(
            trace_id="t-1",
            service="bot",
            component=None,
            environment=None,
        )
        assert result == {"trace_id": "t-1", "service": "bot"}
        assert "component" not in result
        assert "environment" not in result

    def test_build_correlation_context_all_provided(self) -> None:
        """All non-None values should appear in the result."""
        result = build_correlation_context(
            environment="prod",
            release="2.0",
            service="bot",
        )
        assert result == {"environment": "prod", "release": "2.0", "service": "bot"}

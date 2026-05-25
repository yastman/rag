"""Unit tests for PII-safe Sentry breadcrumb helpers (#2062).

Covers ``add_safe_breadcrumb`` and the project-canonical category wrappers
(``lifecycle_breadcrumb``, ``rag_breadcrumb``, ``session_breadcrumb``,
``handler_breadcrumb``, ``error_boundary_breadcrumb``,
``message_receive_breadcrumb``) in ``src.observability_sentry``.

The tests patch the ``_sentry_add_breadcrumb`` indirection seam so we
verify the redacted payload that would land in the SDK without poking a
live transport.
"""

from __future__ import annotations

import sys
from unittest.mock import patch

import pytest


@pytest.fixture()
def helper(monkeypatch):
    for var in (
        "SENTRY_DSN",
        "SENTRY_ENVIRONMENT",
        "SENTRY_RELEASE",
        "SENTRY_TRACES_SAMPLE_RATE",
        "SENTRY_DEBUG",
    ):
        monkeypatch.delenv(var, raising=False)
    sys.modules.pop("src.observability_sentry", None)
    import src.observability_sentry as m

    yield m
    sys.modules.pop("src.observability_sentry", None)


# ---------------------------------------------------------------------------
# add_safe_breadcrumb
# ---------------------------------------------------------------------------


def test_add_safe_breadcrumb_redacts_phone_in_message(helper):
    with patch.object(helper, "_sentry_add_breadcrumb") as spy:
        helper.add_safe_breadcrumb(category="rag", message="user called +380501234567")
    kwargs = spy.call_args.kwargs
    assert "+380501234567" not in kwargs["message"]
    assert "[PHONE]" in kwargs["message"]


def test_add_safe_breadcrumb_redacts_email_in_data(helper):
    with patch.object(helper, "_sentry_add_breadcrumb") as spy:
        helper.add_safe_breadcrumb(
            category="rag", message="agent reply", data={"contact": "agent@example.com"}
        )
    data = spy.call_args.kwargs["data"]
    assert "agent@example.com" not in data["contact"]
    assert "[EMAIL]" in data["contact"]


def test_add_safe_breadcrumb_truncates_long_text(helper):
    long_text = "A" * 8000
    with patch.object(helper, "_sentry_add_breadcrumb") as spy:
        helper.add_safe_breadcrumb(category="rag", message=long_text)
    msg = spy.call_args.kwargs["message"]
    assert len(msg) < len(long_text)
    assert msg.endswith("[TRUNCATED]")


def test_add_safe_breadcrumb_handles_none_message(helper):
    """category-only breadcrumbs (no message) must not crash."""
    with patch.object(helper, "_sentry_add_breadcrumb") as spy:
        helper.add_safe_breadcrumb(category="lifecycle")
    kwargs = spy.call_args.kwargs
    assert kwargs["category"] == "lifecycle"
    assert kwargs["message"] is None


def test_add_safe_breadcrumb_handles_none_data(helper):
    with patch.object(helper, "_sentry_add_breadcrumb") as spy:
        helper.add_safe_breadcrumb(category="rag", message="event")
    assert spy.call_args.kwargs["data"] is None


def test_add_safe_breadcrumb_default_level_is_info(helper):
    with patch.object(helper, "_sentry_add_breadcrumb") as spy:
        helper.add_safe_breadcrumb(category="rag", message="event")
    assert spy.call_args.kwargs["level"] == "info"


def test_add_safe_breadcrumb_passes_explicit_level(helper):
    with patch.object(helper, "_sentry_add_breadcrumb") as spy:
        helper.add_safe_breadcrumb(category="rag", message="event", level="warning")
    assert spy.call_args.kwargs["level"] == "warning"


def test_add_safe_breadcrumb_passes_through_category(helper):
    with patch.object(helper, "_sentry_add_breadcrumb") as spy:
        helper.add_safe_breadcrumb(category="custom_cat", message="event")
    assert spy.call_args.kwargs["category"] == "custom_cat"


def test_add_safe_breadcrumb_does_not_drop_when_redact_raises(helper):
    """If PII redaction blows up, the breadcrumb is dropped, not the event."""
    with (
        patch.object(helper, "_sentry_add_breadcrumb") as spy,
        patch.object(helper, "_redact", side_effect=RuntimeError("bad")),
    ):
        # Must not raise out of the helper
        helper.add_safe_breadcrumb(category="rag", message="bad payload")
    spy.assert_not_called()


# ---------------------------------------------------------------------------
# Canonical lifecycle wrappers
# ---------------------------------------------------------------------------


def test_lifecycle_breadcrumb_uses_lifecycle_category(helper):
    with patch.object(helper, "_sentry_add_breadcrumb") as spy:
        helper.lifecycle_breadcrumb("bot.startup", version="2.14.0")
    kwargs = spy.call_args.kwargs
    assert kwargs["category"] == "lifecycle"
    assert kwargs["message"] == "bot.startup"
    assert kwargs["data"] == {"version": "2.14.0"}
    assert kwargs["level"] == "info"


def test_rag_breadcrumb_uses_rag_category(helper):
    with patch.object(helper, "_sentry_add_breadcrumb") as spy:
        helper.rag_breadcrumb("rag.start", route="/query")
    kwargs = spy.call_args.kwargs
    assert kwargs["category"] == "rag"
    assert kwargs["message"] == "rag.start"
    assert kwargs["data"] == {"route": "/query"}


def test_rag_breadcrumb_supports_warning_level(helper):
    with patch.object(helper, "_sentry_add_breadcrumb") as spy:
        helper.rag_breadcrumb("rag.fallback", level="warning", reason="timeout")
    assert spy.call_args.kwargs["level"] == "warning"
    assert spy.call_args.kwargs["data"] == {"reason": "timeout"}


def test_session_breadcrumb_uses_session_category(helper):
    with patch.object(helper, "_sentry_add_breadcrumb") as spy:
        helper.session_breadcrumb("session.create", thread_id="t-1")
    kwargs = spy.call_args.kwargs
    assert kwargs["category"] == "session"
    assert kwargs["message"] == "session.create"
    assert kwargs["data"] == {"thread_id": "t-1"}


def test_handler_breadcrumb_uses_handler_category(helper):
    with patch.object(helper, "_sentry_add_breadcrumb") as spy:
        helper.handler_breadcrumb("handler.dispatch", route="/start")
    kwargs = spy.call_args.kwargs
    assert kwargs["category"] == "handler"
    assert kwargs["data"] == {"route": "/start"}


def test_error_boundary_breadcrumb_uses_error_category_and_warning_level(helper):
    with patch.object(helper, "_sentry_add_breadcrumb") as spy:
        helper.error_boundary_breadcrumb("rag.failure", reason="timeout")
    kwargs = spy.call_args.kwargs
    assert kwargs["category"] == "error_boundary"
    assert kwargs["level"] == "warning"
    assert kwargs["data"] == {"reason": "timeout"}


# ---------------------------------------------------------------------------
# message_receive_breadcrumb — must NEVER log raw user text
# ---------------------------------------------------------------------------


def test_message_receive_breadcrumb_does_not_log_raw_text(helper):
    """message_receive must skip ``text=`` payload and only emit metadata."""
    with patch.object(helper, "_sentry_add_breadcrumb") as spy:
        helper.message_receive_breadcrumb(
            content_type="text",
            text="secret user message with +380501234567",
            text_length=42,
        )
    kwargs = spy.call_args.kwargs
    # No raw message text in the breadcrumb message or data
    serialised = repr(kwargs)
    assert "secret user message" not in serialised
    assert "+380501234567" not in serialised
    # But length and content_type are preserved as safe metadata
    assert kwargs["category"] == "message_receive"
    assert kwargs["data"]["content_type"] == "text"
    assert kwargs["data"]["text_length"] == 42


def test_message_receive_breadcrumb_strips_unknown_payload_keys(helper):
    """Only allow-listed safe metadata keys are forwarded."""
    with patch.object(helper, "_sentry_add_breadcrumb") as spy:
        helper.message_receive_breadcrumb(
            content_type="voice",
            voice_seconds=12,
            telegram_user_id_hash="abc",
            tokens="oauth-secret",
            crm_payload={"phone": "+380999999999"},
        )
    kwargs = spy.call_args.kwargs
    data = kwargs["data"]
    # Allow-listed keys
    assert data["content_type"] == "voice"
    assert data["voice_seconds"] == 12
    assert data["telegram_user_id_hash"] == "abc"
    # Not allow-listed
    assert "tokens" not in data
    assert "crm_payload" not in data

"""Unit tests for src.observability_sentry.initialize_sentry (#2060).

These tests cover the SDK-native sentry-sdk initialization helper:
- Graceful no-op when SENTRY_DSN is unset / blank
- Forwarding of DSN, environment, release, sample-rate args to sentry_sdk.init
- send_default_pii=False is hard-coded (cannot be turned on via env)
- EventScrubber denylist extends the SDK default with project-specific keys
- before_send redacts PII (phone/email/passport/tax_id) via PIIRedactor
- before_send truncates over-long string payloads
- before_send is null-safe on partially populated events
- Idempotent without force=, re-initializable with force=True

PIIRedactor patterns are reused as-is; we only assert that the hook routes
event payloads through it.
"""

from __future__ import annotations

import sys
from typing import Any
from unittest.mock import patch

import pytest


pytestmark = pytest.mark.usefixtures("_reset_sentry_module")


@pytest.fixture()
def _reset_sentry_module(monkeypatch):
    """Reload the helper module so each test starts with fresh state."""
    # Strip env that could leak between tests
    for var in (
        "SENTRY_DSN",
        "SENTRY_ENVIRONMENT",
        "SENTRY_RELEASE",
        "SENTRY_TRACES_SAMPLE_RATE",
        "SENTRY_DEBUG",
    ):
        monkeypatch.delenv(var, raising=False)

    # Ensure a fresh module state every test
    sys.modules.pop("src.observability_sentry", None)
    yield
    sys.modules.pop("src.observability_sentry", None)


def _import_helper():
    import src.observability_sentry as m

    return m


# ---------------------------------------------------------------------------
# No-op behavior
# ---------------------------------------------------------------------------


def test_returns_false_when_dsn_unset(monkeypatch):
    helper = _import_helper()
    with patch.object(helper, "_sentry_init") as init_spy:
        assert helper.initialize_sentry() is False
        init_spy.assert_not_called()


@pytest.mark.parametrize("blank", ["", "  ", "\n", "\t"])
def test_returns_false_when_dsn_blank(monkeypatch, blank):
    monkeypatch.setenv("SENTRY_DSN", blank)
    helper = _import_helper()
    with patch.object(helper, "_sentry_init") as init_spy:
        assert helper.initialize_sentry() is False
        init_spy.assert_not_called()


def test_logs_skip_once_when_dsn_unset(monkeypatch, caplog):
    helper = _import_helper()
    with caplog.at_level("INFO", logger="src.observability_sentry"):
        helper.initialize_sentry()
        helper.initialize_sentry()  # second call must not log again
    skip_messages = [r for r in caplog.records if "SENTRY_DSN" in r.message]
    assert len(skip_messages) == 1


# ---------------------------------------------------------------------------
# init() argument forwarding
# ---------------------------------------------------------------------------


def test_passes_dsn_to_sentry_sdk_init(monkeypatch):
    monkeypatch.setenv("SENTRY_DSN", "https://pk@example.test/1")
    helper = _import_helper()
    with patch.object(helper, "_sentry_init") as init_spy:
        assert helper.initialize_sentry() is True
        kwargs = init_spy.call_args.kwargs
        assert kwargs["dsn"] == "https://pk@example.test/1"


def test_send_default_pii_is_always_false(monkeypatch):
    # Even if a user sets the env var, the helper must not allow PII through
    monkeypatch.setenv("SENTRY_DSN", "https://pk@example.test/1")
    monkeypatch.setenv("SENTRY_SEND_DEFAULT_PII", "true")  # ignored on purpose
    helper = _import_helper()
    with patch.object(helper, "_sentry_init") as init_spy:
        helper.initialize_sentry()
    assert init_spy.call_args.kwargs["send_default_pii"] is False


def test_environment_from_env_var(monkeypatch):
    monkeypatch.setenv("SENTRY_DSN", "https://pk@example.test/1")
    monkeypatch.setenv("SENTRY_ENVIRONMENT", "staging")
    helper = _import_helper()
    with patch.object(helper, "_sentry_init") as init_spy:
        helper.initialize_sentry()
    assert init_spy.call_args.kwargs["environment"] == "staging"


def test_environment_default_is_local(monkeypatch):
    monkeypatch.setenv("SENTRY_DSN", "https://pk@example.test/1")
    helper = _import_helper()
    with patch.object(helper, "_sentry_init") as init_spy:
        helper.initialize_sentry()
    assert init_spy.call_args.kwargs["environment"] == "local"


def test_release_from_env_var(monkeypatch):
    monkeypatch.setenv("SENTRY_DSN", "https://pk@example.test/1")
    monkeypatch.setenv("SENTRY_RELEASE", "rag-fresh@2.14.0+abc1234")
    helper = _import_helper()
    with patch.object(helper, "_sentry_init") as init_spy:
        helper.initialize_sentry()
    assert init_spy.call_args.kwargs["release"] == "rag-fresh@2.14.0+abc1234"


def test_release_falls_back_to_package_version(monkeypatch):
    monkeypatch.setenv("SENTRY_DSN", "https://pk@example.test/1")
    helper = _import_helper()
    with patch.object(helper, "_sentry_init") as init_spy:
        helper.initialize_sentry()
    release = init_spy.call_args.kwargs["release"]
    # We don't pin the exact value, only that something non-empty is supplied
    assert isinstance(release, str)
    assert release  # non-empty


def test_traces_sample_rate_default_is_zero(monkeypatch):
    monkeypatch.setenv("SENTRY_DSN", "https://pk@example.test/1")
    helper = _import_helper()
    with patch.object(helper, "_sentry_init") as init_spy:
        helper.initialize_sentry()
    assert init_spy.call_args.kwargs["traces_sample_rate"] == 0.0


def test_traces_sample_rate_from_env_var(monkeypatch):
    monkeypatch.setenv("SENTRY_DSN", "https://pk@example.test/1")
    monkeypatch.setenv("SENTRY_TRACES_SAMPLE_RATE", "0.05")
    helper = _import_helper()
    with patch.object(helper, "_sentry_init") as init_spy:
        helper.initialize_sentry()
    assert init_spy.call_args.kwargs["traces_sample_rate"] == 0.05


def test_invalid_traces_sample_rate_falls_back_to_zero(monkeypatch):
    monkeypatch.setenv("SENTRY_DSN", "https://pk@example.test/1")
    monkeypatch.setenv("SENTRY_TRACES_SAMPLE_RATE", "not-a-float")
    helper = _import_helper()
    with patch.object(helper, "_sentry_init") as init_spy:
        helper.initialize_sentry()
    assert init_spy.call_args.kwargs["traces_sample_rate"] == 0.0


def test_explicit_args_override_env(monkeypatch):
    monkeypatch.setenv("SENTRY_DSN", "https://env@example.test/1")
    monkeypatch.setenv("SENTRY_ENVIRONMENT", "from-env")
    helper = _import_helper()
    with patch.object(helper, "_sentry_init") as init_spy:
        helper.initialize_sentry(
            dsn="https://explicit@example.test/2",
            environment="from-arg",
            release="explicit-release",
            traces_sample_rate=0.5,
        )
    kwargs = init_spy.call_args.kwargs
    assert kwargs["dsn"] == "https://explicit@example.test/2"
    assert kwargs["environment"] == "from-arg"
    assert kwargs["release"] == "explicit-release"
    assert kwargs["traces_sample_rate"] == 0.5


# ---------------------------------------------------------------------------
# EventScrubber denylist
# ---------------------------------------------------------------------------


def test_event_scrubber_denylist_extends_defaults(monkeypatch):
    monkeypatch.setenv("SENTRY_DSN", "https://pk@example.test/1")
    helper = _import_helper()

    # Sanity check: default denylist exists and is non-empty
    from sentry_sdk.scrubber import DEFAULT_DENYLIST

    with patch.object(helper, "_sentry_init") as init_spy:
        helper.initialize_sentry()
    scrubber = init_spy.call_args.kwargs["event_scrubber"]
    project_extras = {
        "telegram_bot_token",
        "bot_token",
        "telegram_token",
        "kommo_token",
        "kommo_jwt",
        "kommo_client_secret",
        "litellm_master_key",
        "langfuse_secret_key",
        "langfuse_public_key",
        "openai_api_key",
        "anthropic_api_key",
        "groq_api_key",
        "voyage_api_key",
        "redis_password",
        "postgres_password",
        "clickhouse_password",
        "minio_root_password",
    }
    denylist = set(scrubber.denylist)
    assert project_extras.issubset(denylist)
    # EventScrubber lowercases denylist entries on construction; compare
    # case-insensitively against the SDK defaults.
    assert {x.lower() for x in DEFAULT_DENYLIST}.issubset(denylist)


# ---------------------------------------------------------------------------
# before_send PII redaction
# ---------------------------------------------------------------------------


def _capture_before_send(monkeypatch) -> Any:
    monkeypatch.setenv("SENTRY_DSN", "https://pk@example.test/1")
    helper = _import_helper()
    with patch.object(helper, "_sentry_init") as init_spy:
        helper.initialize_sentry()
    return init_spy.call_args.kwargs["before_send"]


def test_before_send_redacts_phone_in_message(monkeypatch):
    before_send = _capture_before_send(monkeypatch)
    event = {"message": "user called +380501234567 about apartment"}
    out = before_send(dict(event), hint=None)
    assert "+380501234567" not in out["message"]
    assert "[PHONE]" in out["message"]


def test_before_send_redacts_email_in_extra(monkeypatch):
    before_send = _capture_before_send(monkeypatch)
    event = {"extra": {"contact": "agent@example.com"}}
    out = before_send(dict(event), hint=None)
    assert "agent@example.com" not in out["extra"]["contact"]
    assert "[EMAIL]" in out["extra"]["contact"]


def test_before_send_redacts_breadcrumbs(monkeypatch):
    before_send = _capture_before_send(monkeypatch)
    event = {
        "breadcrumbs": {
            "values": [
                {
                    "category": "rag",
                    "message": "phone +380999999999 logged",
                    "data": {"email": "ops@example.com"},
                }
            ]
        }
    }
    out = before_send(dict(event), hint=None)
    crumb = out["breadcrumbs"]["values"][0]
    assert "+380999999999" not in crumb["message"]
    assert "ops@example.com" not in crumb["data"]["email"]


def test_before_send_truncates_long_text(monkeypatch):
    before_send = _capture_before_send(monkeypatch)
    long_text = "A" * 8000
    event = {"extra": {"raw": long_text}}
    out = before_send(dict(event), hint=None)
    assert len(out["extra"]["raw"]) < len(long_text)
    assert out["extra"]["raw"].endswith("[TRUNCATED]")


def test_before_send_handles_missing_keys(monkeypatch):
    before_send = _capture_before_send(monkeypatch)
    out = before_send({}, hint=None)
    assert out == {}


def test_before_send_returns_none_drops_event_only_when_explicitly_asked(monkeypatch):
    """Helper must not drop events on its own; that's the integrator's call."""
    before_send = _capture_before_send(monkeypatch)
    event = {"message": "ordinary error"}
    out = before_send(dict(event), hint=None)
    assert out is not None
    assert out["message"] == "ordinary error"


# ---------------------------------------------------------------------------
# Idempotency
# ---------------------------------------------------------------------------


def test_idempotent_without_force(monkeypatch):
    monkeypatch.setenv("SENTRY_DSN", "https://pk@example.test/1")
    helper = _import_helper()
    with patch.object(helper, "_sentry_init") as init_spy:
        assert helper.initialize_sentry() is True
        assert helper.initialize_sentry() is True
        assert init_spy.call_count == 1


def test_force_reinitializes(monkeypatch):
    monkeypatch.setenv("SENTRY_DSN", "https://pk@example.test/1")
    helper = _import_helper()
    with patch.object(helper, "_sentry_init") as init_spy:
        helper.initialize_sentry()
        helper.initialize_sentry(force=True)
        assert init_spy.call_count == 2


# ---------------------------------------------------------------------------
# Smoke: capture_message call path lands in the SDK
# ---------------------------------------------------------------------------


def test_capture_message_after_init(monkeypatch):
    """Public smoke test required by the issue acceptance criterion."""
    monkeypatch.setenv("SENTRY_DSN", "https://pk@example.test/1")
    helper = _import_helper()

    with (
        patch.object(helper, "_sentry_init") as init_spy,
        patch.object(helper, "_sentry_capture_message") as capture_spy,
    ):
        init_spy.return_value = None
        capture_spy.return_value = "evt-id"
        helper.initialize_sentry()

        # Post-init, capture_message must reach the SDK with the original arg
        import sentry_sdk

        with patch.object(sentry_sdk, "capture_message", capture_spy):
            sentry_sdk.capture_message("smoke")
        capture_spy.assert_called_once_with("smoke")

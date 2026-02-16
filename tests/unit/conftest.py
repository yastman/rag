"""Unit test specific fixtures for isolation."""

import pytest


@pytest.fixture(autouse=True)
def isolate_otel_langfuse(monkeypatch):
    """Block OTEL/Langfuse network calls without mutating import state.

    The fixture must not clear or replace ``sys.modules`` entries because that
    breaks package imports inside the same xdist worker process.
    """

    # Reset prompt_manager singleton so it picks up mocked Langfuse
    from telegram_bot.integrations.prompt_manager import _reset_client

    _reset_client()

    # Force environment variables (override, not setdefault)
    monkeypatch.setenv("OTEL_SDK_DISABLED", "true")
    monkeypatch.setenv("OTEL_TRACES_EXPORTER", "none")
    monkeypatch.setenv("OTEL_METRICS_EXPORTER", "none")
    monkeypatch.setenv("OTEL_LOGS_EXPORTER", "none")
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "")
    monkeypatch.setenv("LANGFUSE_ENABLED", "false")
    monkeypatch.setenv("LANGFUSE_HOST", "")
    monkeypatch.setenv("LANGFUSE_TRACING_ENABLED", "false")
    monkeypatch.setenv("RAGAS_DO_NOT_TRACK", "true")
    monkeypatch.delenv("LANGFUSE_SECRET_KEY", raising=False)
    monkeypatch.delenv("LANGFUSE_PUBLIC_KEY", raising=False)

    yield

    _reset_client()

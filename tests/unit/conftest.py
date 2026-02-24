"""Unit test specific fixtures for isolation."""

import contextlib
from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture(autouse=True)
def isolate_otel_langfuse(monkeypatch):
    """Block OTEL/Langfuse network calls in unit tests.

    Uses env vars + targeted patches only.  Does NOT manipulate sys.modules
    because deleting/replacing modules breaks import references in other
    tests running in the same xdist worker process.
    """
    ***REMOVED*** Reset prompt_manager singleton so it uses fresh env vars each test
    from telegram_bot.integrations.prompt_manager import _reset_client

    _reset_client()

    ***REMOVED*** Force environment variables (override, not setdefault)
    monkeypatch.setenv("OTEL_SDK_DISABLED", "true")
    monkeypatch.setenv("OTEL_TRACES_EXPORTER", "none")
    monkeypatch.setenv("OTEL_METRICS_EXPORTER", "none")
    monkeypatch.setenv("OTEL_LOGS_EXPORTER", "none")
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "")
    monkeypatch.setenv("LANGFUSE_ENABLED", "false")
    monkeypatch.setenv("LANGFUSE_HOST", "")
    monkeypatch.setenv("LANGFUSE_TRACING_ENABLED", "false")
    monkeypatch.delenv("LANGFUSE_SECRET_KEY", raising=False)

    ***REMOVED*** Create no-op mocks
    mock_noop = MagicMock()

    ***REMOVED*** Patch at entry points to prevent any network initialization.
    ***REMOVED*** Do NOT patch "langfuse.Langfuse" — the patch() call itself imports
    ***REMOVED*** langfuse and can corrupt module state on stop().  Instead, patch the
    ***REMOVED*** higher-level wrappers that our code actually calls.
    patches = [
        ***REMOVED*** Langfuse — patch our wrapper, not the SDK class directly
        patch("telegram_bot.services.observability.get_client", lambda: mock_noop),
        ***REMOVED*** Fallback: patch low-level OTEL exporters
        patch(
            "opentelemetry.exporter.otlp.proto.grpc.trace_exporter.OTLPSpanExporter",
            mock_noop,
        ),
        patch(
            "opentelemetry.exporter.otlp.proto.grpc.metric_exporter.OTLPMetricExporter",
            mock_noop,
        ),
        patch("opentelemetry.sdk.trace.export.BatchSpanProcessor", mock_noop),
        patch(
            "opentelemetry.sdk.metrics.export.PeriodicExportingMetricReader",
            mock_noop,
        ),
    ]

    for p in patches:
        with contextlib.suppress(Exception):
            p.start()

    yield

    for p in patches:
        with contextlib.suppress(Exception):
            p.stop()

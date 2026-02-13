"""Unit test specific fixtures for isolation."""

import contextlib
import sys
from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture(autouse=True)
def isolate_otel_langfuse(monkeypatch):
    """Block OTEL/Langfuse network calls and clear module cache in unit tests.

    This fixture runs automatically before each unit test to prevent:
    - OTEL exporters from attempting network connections
    - Langfuse from initializing real clients
    - Test hangs due to blocking network I/O
    - Module state pollution from mocks in other tests
    """
    # Clear potentially polluted modules
    prefixes = ("opentelemetry", "langfuse", "telegram_bot.services.observability")
    for key in list(sys.modules.keys()):
        if key.startswith(prefixes):
            sys.modules.pop(key, None)

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
    monkeypatch.delenv("LANGFUSE_SECRET_KEY", raising=False)

    # Create no-op mocks
    mock_noop = MagicMock()

    # Mock langfuse module with __version__ attribute (for pollution test)
    mock_langfuse_module = MagicMock()
    mock_langfuse_module.__version__ = "0.0.0-test"
    if "langfuse" not in sys.modules or not hasattr(sys.modules["langfuse"], "__file__"):
        sys.modules["langfuse"] = mock_langfuse_module

    # Patch at entry points to prevent any network initialization
    patches = [
        # OTEL entry point - make setup_opentelemetry a no-op
        patch("src.observability.otel_setup.setup_opentelemetry", mock_noop),
        # Langfuse entry point - return mock client
        patch("langfuse.Langfuse", mock_noop),
        patch("telegram_bot.services.observability.get_client", lambda: mock_noop),
        # Fallback: patch low-level OTEL exporters in case setup_opentelemetry is called
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

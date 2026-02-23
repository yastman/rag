import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


_OTEL_MODULE_NAMES = (
    "opentelemetry",
    "opentelemetry.metrics",
    "opentelemetry.trace",
    "opentelemetry.exporter",
    "opentelemetry.exporter.otlp",
    "opentelemetry.exporter.otlp.proto",
    "opentelemetry.exporter.otlp.proto.grpc",
    "opentelemetry.exporter.otlp.proto.grpc.metric_exporter",
    "opentelemetry.exporter.otlp.proto.grpc.trace_exporter",
    "opentelemetry.instrumentation",
    "opentelemetry.instrumentation.aiohttp_client",
    "opentelemetry.instrumentation.redis",
    "opentelemetry.sdk",
    "opentelemetry.sdk.metrics",
    "opentelemetry.sdk.metrics.export",
    "opentelemetry.sdk.resources",
    "opentelemetry.sdk.trace",
    "opentelemetry.sdk.trace.export",
)


@pytest.fixture(autouse=True)
def fresh_otel_setup_module():
    """Clear src.observability.otel_setup from cache to ensure fresh import.

    Keep cleanup scoped to our module to avoid cross-test leakage.
    """
    sys.modules.pop("src.observability.otel_setup", None)
    sys.modules.pop("src.observability", None)
    yield
    sys.modules.pop("src.observability.otel_setup", None)
    sys.modules.pop("src.observability", None)


@pytest.fixture(autouse=True)
def isolated_otel_modules():
    """Provide missing opentelemetry modules per-test and teardown safely.

    Nightly marker runs collect all test modules; import-time sys.modules mutation
    here can leak into unrelated voice tests. Keep this fixture-scoped.
    """
    injected: list[str] = []
    for name in _OTEL_MODULE_NAMES:
        if name not in sys.modules:
            sys.modules[name] = MagicMock()
            injected.append(name)
    yield
    for name in injected:
        sys.modules.pop(name, None)


def test_setup_opentelemetry():
    """Test OpenTelemetry setup creates providers and configures exporters."""
    # Import INSIDE test to get fresh module after fixture clears cache
    # Then patches on module attributes will take effect
    from src.observability.otel_setup import setup_opentelemetry

    # Use patching on the module's imported names
    with (
        patch("src.observability.otel_setup.trace") as mock_trace,
        patch("src.observability.otel_setup.metrics"),
        patch("src.observability.otel_setup.TracerProvider") as mock_tracer_provider,
        patch("src.observability.otel_setup.MeterProvider"),
        patch("src.observability.otel_setup.OTLPSpanExporter") as mock_span_exporter,
        patch("src.observability.otel_setup.OTLPMetricExporter"),
        patch("src.observability.otel_setup.BatchSpanProcessor"),
        patch("src.observability.otel_setup.PeriodicExportingMetricReader"),
        patch("src.observability.otel_setup.Resource"),
        patch("src.observability.otel_setup.AioHttpClientInstrumentor") as mock_aiohttp,
        patch("src.observability.otel_setup.RedisInstrumentor") as mock_redis,
    ):
        setup_opentelemetry("test-service")

        # Check trace provider setup
        mock_tracer_provider.assert_called_once()
        mock_trace.set_tracer_provider.assert_called_once()

        # Check exporters
        mock_span_exporter.assert_called_with(endpoint="http://localhost:4317", insecure=True)

        # Check instrumentation
        mock_aiohttp.return_value.instrument.assert_called_once()
        mock_redis.return_value.instrument.assert_called_once()


async def test_traced_pipeline_query():
    # Import INSIDE test to get fresh module after fixture clears cache
    from src.observability.otel_setup import TracedRAGPipeline

    pipeline = TracedRAGPipeline()
    pipeline.embedding_latency = MagicMock()
    pipeline.search_latency = MagicMock()
    pipeline.rerank_latency = MagicMock()
    pipeline.query_latency = MagicMock()
    pipeline.query_counter = MagicMock()

    # Mock internal methods using patches on instance
    with patch.object(pipeline, "_embed", new_callable=AsyncMock) as mock_embed:
        with patch.object(pipeline, "_search", new_callable=AsyncMock) as mock_search:
            with patch.object(pipeline, "_rerank", new_callable=AsyncMock) as mock_rerank:
                # Setup mocks
                mock_embed.return_value = [0.1] * 10
                mock_search.return_value = [{"score": 0.9, "text": "result"}]
                mock_rerank.return_value = [{"score": 0.9, "text": "result"}]

                # Setup tracer mock context managers
                mock_span = MagicMock()
                with patch.object(pipeline.tracer, "start_as_current_span") as mock_start_span:
                    mock_start_span.return_value.__enter__.return_value = mock_span

                    # Execute
                    result = await pipeline.query("test query", top_k=5)

                # Assert
                assert len(result["results"]) == 1
                mock_embed.assert_called_once()
                mock_search.assert_called_once()
                # Check metrics recorded
                pipeline.embedding_latency.record.assert_called()
                pipeline.search_latency.record.assert_called()
                pipeline.query_counter.add.assert_called()

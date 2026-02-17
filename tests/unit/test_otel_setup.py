import importlib.util
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# Skip entire module if opentelemetry.instrumentation is not installed
if importlib.util.find_spec("opentelemetry.instrumentation") is None:
    pytest.skip(
        "opentelemetry-instrumentation not installed",
        allow_module_level=True,
    )

pytestmark = pytest.mark.requires_extras


@pytest.fixture(autouse=True)
def fresh_otel_setup_module():
    """Clear src.observability.otel_setup from cache to ensure fresh import.

    NOTE: We do NOT mock opentelemetry hierarchy in sys.modules - that's fragile.
    Instead, we rely on targeted patches inside test functions.
    """
    # Clear only our module, not opentelemetry itself
    sys.modules.pop("src.observability.otel_setup", None)
    sys.modules.pop("src.observability", None)
    yield
    sys.modules.pop("src.observability.otel_setup", None)
    sys.modules.pop("src.observability", None)


def reset_otel_mocks():
    """Reset all OpenTelemetry mocks to fresh state."""
    mocks = {
        "opentelemetry": MagicMock(),
        "opentelemetry.metrics": MagicMock(),
        "opentelemetry.trace": MagicMock(),
        "opentelemetry.exporter": MagicMock(),
        "opentelemetry.exporter.otlp": MagicMock(),
        "opentelemetry.exporter.otlp.proto": MagicMock(),
        "opentelemetry.exporter.otlp.proto.grpc": MagicMock(),
        "opentelemetry.exporter.otlp.proto.grpc.metric_exporter": MagicMock(),
        "opentelemetry.exporter.otlp.proto.grpc.trace_exporter": MagicMock(),
        "opentelemetry.instrumentation": MagicMock(),
        "opentelemetry.instrumentation.aiohttp_client": MagicMock(),
        "opentelemetry.instrumentation.redis": MagicMock(),
        "opentelemetry.sdk": MagicMock(),
        "opentelemetry.sdk.metrics": MagicMock(),
        "opentelemetry.sdk.metrics.export": MagicMock(),
        "opentelemetry.sdk.resources": MagicMock(),
        "opentelemetry.sdk.trace": MagicMock(),
        "opentelemetry.sdk.trace.export": MagicMock(),
    }
    sys.modules.update(mocks)
    return mocks


# Pre-mock opentelemetry to avoid import side effects
reset_otel_mocks()


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
                mock_start_span = pipeline.tracer.start_as_current_span
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

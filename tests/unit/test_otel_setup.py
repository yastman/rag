import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# Pre-mock opentelemetry to avoid import side effects
mock_otel = MagicMock()
sys.modules["opentelemetry"] = mock_otel
sys.modules["opentelemetry.metrics"] = MagicMock()
sys.modules["opentelemetry.trace"] = MagicMock()
sys.modules["opentelemetry.exporter"] = MagicMock()
sys.modules["opentelemetry.exporter.otlp"] = MagicMock()
sys.modules["opentelemetry.exporter.otlp.proto"] = MagicMock()
sys.modules["opentelemetry.exporter.otlp.proto.grpc"] = MagicMock()
sys.modules["opentelemetry.exporter.otlp.proto.grpc.metric_exporter"] = MagicMock()
sys.modules["opentelemetry.exporter.otlp.proto.grpc.trace_exporter"] = MagicMock()
sys.modules["opentelemetry.instrumentation"] = MagicMock()
sys.modules["opentelemetry.instrumentation.aiohttp_client"] = MagicMock()
sys.modules["opentelemetry.instrumentation.redis"] = MagicMock()
sys.modules["opentelemetry.sdk"] = MagicMock()
sys.modules["opentelemetry.sdk.metrics"] = MagicMock()
sys.modules["opentelemetry.sdk.metrics.export"] = MagicMock()
sys.modules["opentelemetry.sdk.resources"] = MagicMock()
sys.modules["opentelemetry.sdk.trace"] = MagicMock()
sys.modules["opentelemetry.sdk.trace.export"] = MagicMock()

from src.observability.otel_setup import TracedRAGPipeline, setup_opentelemetry


def test_setup_opentelemetry():
    setup_opentelemetry("test-service")

    # Check trace provider setup
    sys.modules["opentelemetry.sdk.trace"].TracerProvider.assert_called_once()
    sys.modules["opentelemetry.trace"].set_tracer_provider.assert_called_once()

    # Check exporters
    sys.modules[
        "opentelemetry.exporter.otlp.proto.grpc.trace_exporter"
    ].OTLPSpanExporter.assert_called_with(endpoint="http://localhost:4317", insecure=True)

    # Check instrumentation
    sys.modules[
        "opentelemetry.instrumentation.aiohttp_client"
    ].AioHttpClientInstrumentor.return_value.instrument.assert_called_once()
    sys.modules[
        "opentelemetry.instrumentation.redis"
    ].RedisInstrumentor.return_value.instrument.assert_called_once()


@pytest.mark.asyncio
async def test_traced_pipeline_query():
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

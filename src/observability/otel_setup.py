"""OpenTelemetry setup for system-level observability."""

import time

from opentelemetry import metrics, trace
from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import OTLPMetricExporter
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.aiohttp_client import AioHttpClientInstrumentor
from opentelemetry.instrumentation.redis import RedisInstrumentor
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor


def setup_opentelemetry(service_name: str = "contextual-rag"):
    """
    Setup OpenTelemetry for distributed tracing.

    Exports to:
    - Traces → Tempo (http://localhost:4317)
    - Metrics → Prometheus (via OTLP endpoint)

    Integration with existing stack:
    - Tempo for trace storage
    - Grafana for visualization
    - Prometheus for metrics
    """

    # Resource identification
    resource = Resource(
        attributes={
            "service.name": service_name,
            "service.version": "2.0.1",
            "deployment.environment": "production",
        }
    )

    # === TRACES ===
    # Configure trace provider
    trace_provider = TracerProvider(resource=resource)

    # OTLP exporter for Tempo
    otlp_trace_exporter = OTLPSpanExporter(
        endpoint="http://localhost:4317",  # Tempo OTLP endpoint
        insecure=True,
    )

    trace_provider.add_span_processor(BatchSpanProcessor(otlp_trace_exporter))

    trace.set_tracer_provider(trace_provider)

    # === METRICS ===
    # Configure metrics provider
    otlp_metric_exporter = OTLPMetricExporter(
        endpoint="http://localhost:4317",
        insecure=True,
    )

    metric_reader = PeriodicExportingMetricReader(
        otlp_metric_exporter,
        export_interval_millis=60000,  # Export every 60s
    )

    meter_provider = MeterProvider(resource=resource, metric_readers=[metric_reader])

    metrics.set_meter_provider(meter_provider)

    # === AUTO-INSTRUMENTATION ===
    # Instrument HTTP clients
    AioHttpClientInstrumentor().instrument()

    # Instrument Redis
    RedisInstrumentor().instrument()

    print("✅ OpenTelemetry initialized")
    print(f"   Service: {service_name}")
    print("   Traces → Tempo: http://localhost:4317")
    print("   Metrics → Prometheus: http://localhost:4317")


# Usage in RAG pipeline
class TracedRAGPipeline:
    """RAG Pipeline with OpenTelemetry tracing."""

    def __init__(self):
        self.tracer = trace.get_tracer(__name__)
        self.meter = metrics.get_meter(__name__)

        # Custom metrics
        self.query_counter = self.meter.create_counter(
            name="rag_queries_total",
            description="Total RAG queries",
            unit="1",
        )

        self.query_latency = self.meter.create_histogram(
            name="rag_query_latency_seconds",
            description="RAG query latency",
            unit="s",
        )

        self.embedding_latency = self.meter.create_histogram(
            name="embedding_latency_seconds",
            description="Embedding generation latency",
            unit="s",
        )

        self.search_latency = self.meter.create_histogram(
            name="vector_search_latency_seconds",
            description="Vector search latency",
            unit="s",
        )

    async def _embed(self, query_text: str) -> list[float]:
        """Embed query text. Override in subclass or mock in tests."""
        raise NotImplementedError("Subclass must implement _embed")

    async def _search(self, embedding: list[float], top_k: int) -> list[dict]:
        """Search for results. Override in subclass or mock in tests."""
        raise NotImplementedError("Subclass must implement _search")

    async def _rerank(self, results: list[dict]) -> list[dict]:
        """Rerank results. Override in subclass or mock in tests."""
        raise NotImplementedError("Subclass must implement _rerank")

    async def query(self, query_text: str, top_k: int = 10):
        """Execute query with full OTEL tracing."""

        with self.tracer.start_as_current_span("rag_query") as span:
            span.set_attribute("query.length", len(query_text))
            span.set_attribute("query.top_k", top_k)

            start_time = time.time()

            try:
                # Step 1: Embed query
                with self.tracer.start_as_current_span("embed_query") as embed_span:
                    embed_start = time.time()
                    query_embedding = await self._embed(query_text)
                    embed_duration = time.time() - embed_start

                    embed_span.set_attribute("embedding.dimension", len(query_embedding))
                    self.embedding_latency.record(embed_duration)

                # Step 2: Vector search
                with self.tracer.start_as_current_span("vector_search") as search_span:
                    search_start = time.time()
                    results = await self._search(query_embedding, top_k)
                    search_duration = time.time() - search_start

                    search_span.set_attribute("results.count", len(results))
                    search_span.set_attribute(
                        "results.top_score", results[0]["score"] if results else 0
                    )
                    self.search_latency.record(search_duration)

                # Step 3: Rerank (if enabled)
                with self.tracer.start_as_current_span("rerank_results"):
                    results = await self._rerank(results)

                # Record total latency
                total_duration = time.time() - start_time
                self.query_latency.record(total_duration)
                self.query_counter.add(1, {"status": "success"})

                span.set_attribute("query.latency_ms", total_duration * 1000)
                span.set_attribute("query.results_count", len(results))

                return {"results": results, "latency_ms": total_duration * 1000}

            except Exception as e:
                span.set_attribute("error", True)
                span.set_attribute("error.message", str(e))
                self.query_counter.add(1, {"status": "error"})
                raise


# Initialize on startup
if __name__ == "__main__":
    setup_opentelemetry("contextual-rag")

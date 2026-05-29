# Cross-service tracing contract

How one user workflow stays a single distributed trace as it crosses HTTP
service boundaries (bot/RAG -> internal FastAPI services -> third-party APIs).
This is the propagation layer behind the single-trace gate (#2244) and the
trace-coverage audit (#2246). It is enforced by
`tests/contract/test_cross_service_trace_instrumentation_contract.py` (#2256).

## The contract

| Direction | Mechanism | Where |
|-----------|-----------|-------|
| Inbound (server) | `FastAPIInstrumentor.instrument_app(app)` extracts `traceparent` + `baggage` from request headers and continues the caller's trace | `services/bge-m3-api/app.py`, `services/user-base/main.py`, `src/api/main.py`, `mini_app/api.py` (via `instrument_fastapi_app(app)`) |
| Outbound (client) | process-wide `HTTPXClientInstrumentor` injects `traceparent` + `baggage` on every `httpx` request | `src/services/bge_m3_client.py`, `src/services/kommo_client.py`, `src/voice/rag_api_client.py`, `src/ingestion/docling_client.py` |
| Activation | `activate_otel_instrumentations()` wires httpx/asyncpg/redis/grpc/logging at startup | `src/observability.py` -> `src/observability_otel.py` |
| Context format | W3C **TraceContext** + W3C **Baggage** | `OTEL_PROPAGATORS=tracecontext,baggage` declared per service (#2254) |

SDK-native APIs verified against the OpenTelemetry Python Contrib docs via
Context7 (`/open-telemetry/opentelemetry-python-contrib`):
`FastAPIInstrumentor.instrument_app(app)` for inbound extraction (it carries a
built-in double-instrumentation guard) and `HTTPXClientInstrumentor().instrument()`
for outbound injection. *Content was rephrased for compliance with licensing
restrictions.*

### Why a contract test

Because all four FastAPI entrypoints and all four httpx clients are already
wired, the risk is **silent regression** — a new service or client that forgets
to instrument fragments the trace without any error. The contract walks the
source and fails CI if an inbound entrypoint stops instrumenting or an outbound
client stops using `httpx`. It is also the precondition for removing the legacy
manual BGE-M3 propagation (#2253): the manual `inject()` / `x-langfuse-*`
headers can be dropped only once auto-instrumentation is guaranteed present.

## Third-party APIs (Kommo)

`src/services/kommo_client.py` uses `httpx`, so `HTTPXClientInstrumentor` adds a
`traceparent` header to outbound Kommo CRM requests. Kommo ignores unknown
request headers, so this is harmless and **no exclusion is required**. If a
third-party API is ever found to reject `traceparent`, add a per-client
exclusion via an httpx request hook rather than disabling instrumentation
globally.

## Why Prometheus / Loki / Sentry are not replaced by OpenTelemetry traces

OpenTelemetry tracing is one signal among several; the others stay as-is and are
cross-linked rather than replaced:

- **Prometheus** — application metrics are pull-based via `prometheus_client`
  and the `/metrics` endpoint. Traces do not replace counters/histograms; the
  metrics stack is unchanged. (Whether to unify on the OTel Metrics API is an
  open ADR question, #2228.)
- **Loki** — structured JSON logs carry `trace_id`/`span_id` (#2217/#2239) so a
  log line links back to its trace. Logs remain the high-cardinality,
  full-detail signal; traces are the sampled causal view.
- **Sentry** — error tracking is cross-linked to Langfuse traces (#2238). Sentry
  remains the exception aggregator; traces are not an error backend.

No OTLP gRPC exporter is introduced by this layer; the only export path is the
existing Langfuse OTel ingestion.

## References

- Gate: #2244 · Audit: #2246 · Runtime continuity: #2252 · Propagators: #2254
- Cleanup unblocked by this contract: #2253
- Foundation PRs: #2225 (auto-instrumentations), #2226/#2235 (baggage)

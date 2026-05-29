# ADR-0016: OpenTelemetry Metrics vs Prometheus

**Status:** Accepted

**Date:** 2026-05-29

**Closes:** [#2228](https://github.com/yastman/rag/issues/2228) (roadmap ADRs)

**Related:** [#2215](https://github.com/yastman/rag/issues/2215) (observability audit umbrella), [ADR-0015](0015-sdk-native-baseline.md) (observability baseline)

## Context

The runtime carries two metric systems:

- **Prometheus (pull):** application metrics via `prometheus_client` — `pipeline_latency_seconds` Histogram, `rag_pipeline_events_total` Counter — registered against the default `prometheus_client.REGISTRY` and scraped over an ASGI `/metrics` mount. This feeds Grafana dashboards and alert rules.
- **OpenTelemetry Metrics (SDK-internal):** the Langfuse v4 SDK uses an OTel `MeterProvider` internally for its own SDK metrics. No operator-visible exporter is wired to it (it is mocked to no-op in unit tests).

The audit (#2215) flagged that this duality is undocumented: there is no recorded decision about whether to unify on the OTel Metrics API (`meter.create_counter(...)`), which could route to Prometheus or OTLP by configuration.

## Decision

**Keep the dual stack, deliberately.** Prometheus pull remains the production metrics backbone. The OTel Metrics API stays SDK-internal and is **not** wired to an operator-visible backend. No OTLP metric exporter is introduced.

Rationale:

- The production observability surface (Grafana dashboards, alert rules, scrape config) is built on Prometheus. Migrating application metrics to the OTel Metrics API + `PrometheusMetricReader` is a pure refactor with no functional gain today.
- Traces (Langfuse/OTel) and metrics (Prometheus) are complementary signals; logs↔traces and Sentry↔traces are already cross-linked (#2217/#2239, #2218). Metrics do not need to move under the trace exporter.

## Consequences

- Two metrics systems coexist by design; new application metrics go through `prometheus_client`, not the OTel Metrics API.
- If a future need arises to export metrics over OTLP centrally (e.g., a collector), revisit with a migration to the OTel Metrics API + `PrometheusMetricReader`, keeping the `/metrics` scrape contract unchanged. That is explicitly out of scope here.

## Implementation notes

- Application metrics: `src/runtime/services/metrics.py` (`PipelineMetrics` facade over Histogram + Counter), `/metrics` ASGI mount.
- Langfuse SDK OTel `MeterProvider`: internal only; no exporter wired.

# 📈 Observability & System Monitoring

This folder contains OpenTelemetry (OTEL) instrumentation for system-level observability.

## 📁 Contents

| File | Purpose |
|------|---------|
| `otel_setup.py` | OpenTelemetry setup (traces + metrics) |

---

## 🔭 What is OpenTelemetry?

OpenTelemetry (OTEL) provides **system-level observability** beyond LLM calls:
- CPU usage
- RAM usage
- Disk I/O
- Network latency
- Database queries (Redis, PostgreSQL, Qdrant)
- HTTP requests

**Why separate from Langfuse?**
- **Langfuse**: LLM-specific (queries, prompts, costs, tokens)
- **OpenTelemetry**: Infrastructure-level (CPU, RAM, I/O, DB latency)

---

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────┐
│                 RAG Application                      │
│  (Instrumented with OpenTelemetry Python SDK)       │
└────────────────┬────────────────────────────────────┘
                 │
                 │ Traces + Metrics (OTLP)
                 ▼
┌────────────────────────────────────────────────────┐
│          Grafana Alloy (Collector)                 │
│  Receives: OTLP traces + metrics on :4317          │
└─────────────┬──────────────────────┬───────────────┘
              │                      │
        Traces│                      │Metrics
              ▼                      ▼
    ┌─────────────────┐    ┌──────────────────┐
    │  Grafana Tempo  │    │   Prometheus     │
    │  (Traces Store) │    │  (Metrics Store) │
    └─────────────────┘    └──────────────────┘
              │                      │
              └──────────┬───────────┘
                         ▼
                  ┌─────────────┐
                  │   Grafana   │
                  │  (Dashboards)│
                  └─────────────┘
```

---

## 📦 OpenTelemetry Setup (`otel_setup.py`)

**Purpose**: Initialize OpenTelemetry instrumentation for traces and metrics.

### Features

1. **Automatic Traces** → Tempo
   - Spans for HTTP requests, Redis queries, Qdrant searches
   - Distributed tracing across services
   - Exported via OTLP to Grafana Alloy (:4317)

2. **System Metrics** → Prometheus
   - CPU usage (per core, average)
   - RAM usage (used, available, percent)
   - Disk I/O (read/write bytes, latency)
   - Network I/O (bytes sent/received)
   - Exported via OTLP to Grafana Alloy (:4317)

3. **Auto-Instrumentation**
   - `aiohttp` (async HTTP client)
   - `redis` (Redis client)
   - `httpx` (HTTP client)
   - `requests` (HTTP client)

---

### Usage

#### Initialize in Application Startup

```python
from observability.otel_setup import setup_opentelemetry

# Initialize OpenTelemetry (call once at startup)
setup_opentelemetry(
    service_name="contextual-rag",
    service_version="2.1.0",
    environment="production"
)

# Your application code continues...
# All HTTP, Redis, DB calls are now auto-instrumented!
```

---

#### Example: Trace RAG Query

```python
from opentelemetry import trace

tracer = trace.get_tracer(__name__)

async def rag_query(query: str, user_id: str):
    with tracer.start_as_current_span("rag-query") as span:
        span.set_attribute("user.id", user_id)
        span.set_attribute("query.length", len(query))

        # Retrieval (auto-instrumented by OTEL)
        with tracer.start_as_current_span("retrieval"):
            results = await qdrant_client.search(
                collection_name="contextual_rag_criminal_code_v1",
                query_vector=embedding,
                limit=10
            )
            span.set_attribute("results.count", len(results))

        # Reranking
        with tracer.start_as_current_span("reranking"):
            reranked = rerank(results, query)

        # Cache check (auto-instrumented by OTEL)
        with tracer.start_as_current_span("cache-check"):
            cached = await redis_client.get(f"response_{query_hash}")

        return reranked
```

**Result**: Full trace visible in Grafana Tempo showing:
- Total query latency
- Breakdown by stage (retrieval, reranking, cache)
- Qdrant search latency
- Redis cache hit/miss

---

#### Example: Custom Metrics

```python
from opentelemetry import metrics

meter = metrics.get_meter(__name__)

# Create custom metrics
query_counter = meter.create_counter(
    name="rag.queries.total",
    description="Total number of RAG queries",
    unit="1"
)

query_latency = meter.create_histogram(
    name="rag.query.latency",
    description="RAG query latency",
    unit="ms"
)

# Record metrics
query_counter.add(1, {"user_id": user_id, "status": "success"})
query_latency.record(latency_ms, {"endpoint": "search"})
```

---

## 🔌 Integration with Infrastructure

### Grafana Alloy (OTLP Collector)

OpenTelemetry data is sent to **Grafana Alloy** (running in Docker):

```yaml
# docker-compose.yml
services:
  alloy:
    image: grafana/alloy:latest
    ports:
      - "4317:4317"  # OTLP gRPC receiver
      - "4318:4318"  # OTLP HTTP receiver
    volumes:
      - ./alloy/config.alloy:/etc/alloy/config.alloy
```

**Alloy Configuration** (`/home/admin/alloy/config.alloy`):
```hcl
otelcol.receiver.otlp "default" {
  grpc {
    endpoint = "0.0.0.0:4317"
  }
  http {
    endpoint = "0.0.0.0:4318"
  }

  output {
    traces  = [otelcol.exporter.otlp.tempo.input]
    metrics = [otelcol.exporter.prometheus.default.input]
  }
}

otelcol.exporter.otlp "tempo" {
  client {
    endpoint = "tempo:4317"
    tls {
      insecure = true
    }
  }
}

otelcol.exporter.prometheus "default" {
  forward_to = [prometheus.remote_write.default.receiver]
}

prometheus.remote_write "default" {
  endpoint {
    url = "http://prometheus:9090/api/v1/write"
  }
}
```

---

### Grafana Tempo (Trace Storage)

All traces are stored in **Tempo** and queryable via Grafana.

**Tempo Configuration** (`/home/admin/tempo/tempo.yaml`):
```yaml
server:
  http_listen_port: 3200

distributor:
  receivers:
    otlp:
      protocols:
        grpc:
          endpoint: "0.0.0.0:4317"

storage:
  trace:
    backend: local
    local:
      path: /tmp/tempo/traces
```

**Access Tempo**:
- Directly: http://localhost:3200
- Via Grafana: http://localhost:3000 (Data Sources → Tempo)

---

### Prometheus (Metrics Storage)

All metrics are stored in **Prometheus**.

**Prometheus Configuration** (`/home/admin/prometheus/prometheus.yml`):
```yaml
scrape_configs:
  - job_name: 'otel-metrics'
    static_configs:
      - targets: ['alloy:4317']
```

**Access Prometheus**:
- Directly: http://localhost:9090
- Via Grafana: http://localhost:3000 (Data Sources → Prometheus)

---

## 📊 Grafana Dashboards

### Pre-built Dashboards

Import these dashboards in Grafana (http://localhost:3000):

1. **OpenTelemetry System Metrics** (ID: 19419)
   - CPU usage (per core, avg)
   - RAM usage (used, available, %)
   - Disk I/O (read/write, latency)
   - Network I/O (bytes sent/received)

2. **OpenTelemetry Traces** (ID: 15983)
   - Trace timeline
   - Span duration breakdown
   - Error rates by service

3. **RAG Query Performance** (Custom)
   - Query latency (P50, P95, P99)
   - Throughput (queries/sec)
   - Error rate
   - Cache hit rate

---

### Creating Custom Dashboard

```json
{
  "dashboard": {
    "title": "RAG System Performance",
    "panels": [
      {
        "title": "Query Latency",
        "targets": [
          {
            "expr": "histogram_quantile(0.95, rag_query_latency_bucket)",
            "legendFormat": "P95"
          }
        ]
      },
      {
        "title": "CPU Usage",
        "targets": [
          {
            "expr": "system_cpu_utilization{service_name=\"contextual-rag\"}",
            "legendFormat": "CPU %"
          }
        ]
      }
    ]
  }
}
```

---

## 🚨 Alerts

Configure alerts in Grafana based on OTEL metrics:

### High Latency Alert

```yaml
alert: HighRAGLatency
expr: histogram_quantile(0.95, rag_query_latency_bucket) > 1000
for: 5m
labels:
  severity: warning
annotations:
  summary: "RAG query P95 latency > 1s"
  description: "P95 latency: {{ $value }}ms"
```

### High CPU Usage Alert

```yaml
alert: HighCPU
expr: avg(system_cpu_utilization{service_name="contextual-rag"}) > 0.8
for: 10m
labels:
  severity: warning
annotations:
  summary: "RAG service CPU > 80%"
```

### High Memory Usage Alert

```yaml
alert: HighMemory
expr: system_memory_utilization{service_name="contextual-rag"} > 0.9
for: 5m
labels:
  severity: critical
annotations:
  summary: "RAG service memory > 90%"
```

---

## 🔍 Troubleshooting

### Issue: No traces appearing in Tempo

**Cause**: OTLP exporter not configured or Alloy not receiving data.

**Solution**:
```bash
# Check Alloy is running
docker ps | grep alloy

# Check Alloy logs
docker logs alloy

# Test OTLP endpoint
curl http://localhost:4318/v1/traces

# Verify OTLP_EXPORTER_OTLP_ENDPOINT
echo $OTEL_EXPORTER_OTLP_ENDPOINT  # Should be http://localhost:4317
```

---

### Issue: Metrics not in Prometheus

**Cause**: Metrics not exported or scrape config missing.

**Solution**:
```bash
# Check Prometheus targets
curl http://localhost:9090/api/v1/targets

# Check if metrics are being scraped
curl http://localhost:9090/api/v1/query?query=system_cpu_utilization

# Verify scrape config
cat /home/admin/prometheus/prometheus.yml | grep otel
```

---

### Issue: High trace volume

**Cause**: Sampling not configured, 100% of requests traced.

**Solution**: Configure trace sampling in `otel_setup.py`:
```python
from opentelemetry.sdk.trace.sampling import TraceIdRatioBased

trace_provider = TracerProvider(
    resource=resource,
    sampler=TraceIdRatioBased(0.1)  # Sample 10% of traces
)
```

---

## 📖 Resources

- **OpenTelemetry Python Docs**: https://opentelemetry.io/docs/instrumentation/python/
- **OTLP Specification**: https://opentelemetry.io/docs/specs/otlp/
- **Grafana Tempo Docs**: https://grafana.com/docs/tempo/
- **Prometheus Docs**: https://prometheus.io/docs/

---

## 🎯 Observability Stack Comparison

| Aspect | OpenTelemetry (OTEL) | Langfuse | MLflow |
|--------|---------------------|----------|--------|
| **Focus** | System infrastructure | LLM queries | Experiments |
| **Traces** | HTTP, DB, Redis, CPU | Prompts, completions | N/A |
| **Metrics** | Latency, CPU, RAM | Tokens, cost | Precision, recall |
| **Use Case** | Performance debugging | Production monitoring | A/B testing |
| **Data Store** | Tempo + Prometheus | Langfuse DB | MLflow DB |
| **Dashboards** | Grafana | Langfuse UI | MLflow UI |

**Rule of Thumb**:
- **System slow?** → Check OpenTelemetry (CPU, RAM, I/O)
- **LLM costs high?** → Check Langfuse (tokens, cost per query)
- **Quality drop?** → Check MLflow (RAGAS metrics, A/B tests)

---

## 🛠️ Configuration

### Environment Variables

```bash
# OpenTelemetry
export OTEL_SERVICE_NAME="contextual-rag"
export OTEL_SERVICE_VERSION="2.1.0"
export OTEL_EXPORTER_OTLP_ENDPOINT="http://localhost:4317"
export OTEL_TRACES_EXPORTER="otlp"
export OTEL_METRICS_EXPORTER="otlp"
export OTEL_LOGS_EXPORTER="none"  # Logs via Loki separately

# Sampling (optional - default 100%)
export OTEL_TRACES_SAMPLER="traceidratio"
export OTEL_TRACES_SAMPLER_ARG="0.1"  # 10% sampling
```

### Python Dependencies

```bash
pip install opentelemetry-api \
            opentelemetry-sdk \
            opentelemetry-exporter-otlp-proto-grpc \
            opentelemetry-instrumentation-aiohttp-client \
            opentelemetry-instrumentation-redis \
            opentelemetry-instrumentation-httpx \
            opentelemetry-instrumentation-requests
```

---

## 🚀 Quick Start

```bash
# 1. Ensure Alloy, Tempo, Prometheus running
docker ps | grep -E "alloy|tempo|prometheus"

# 2. Initialize OTEL in your app
cd /home/admin/contextual_rag
source venv/bin/activate

python
>>> from observability.otel_setup import setup_opentelemetry
>>> setup_opentelemetry()
>>> # Your app code...

# 3. Check traces in Grafana
open http://localhost:3000
# Navigate to: Explore → Tempo → Query traces

# 4. Check metrics in Grafana
# Navigate to: Explore → Prometheus → Query metrics
# Example query: system_cpu_utilization{service_name="contextual-rag"}
```

---

**Last Updated**: October 30, 2025
**Maintainer**: Contextual RAG Team

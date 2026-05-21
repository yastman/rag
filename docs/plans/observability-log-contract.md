# Observability Structured Log Contract

This document defines the structured JSON log shape emitted by all platform services,
the PII safety rules, Loki label strategy, and correlation ID propagation.

## Structured Log JSON Shape

Every log line is a single JSON object with the following fields:

### Mandatory Fields (always present)

| Field         | Type   | Description                                |
|---------------|--------|--------------------------------------------|
| `timestamp`   | string | ISO 8601 UTC timestamp (e.g. `2024-01-15T10:30:00.123Z`) |
| `level`       | string | Log level: DEBUG, INFO, WARNING, ERROR, CRITICAL |
| `logger`      | string | Logger name (dot-separated Python path)    |
| `message`     | string | Human-readable log message                 |
| `service`     | string | Service identifier (default: `telegram-bot`) |
| `environment` | string | Deployment environment from `ENV` var (default: `development`) |

### Optional Fields (included when set, never null)

| Field                    | Type   | Description                             |
|--------------------------|--------|-----------------------------------------|
| `module`                 | string | Python module name                      |
| `function`               | string | Function name where log was emitted     |
| `line`                   | int    | Line number in source file              |
| `exception`              | string | Formatted exception traceback           |
| `component`              | string | Logical component (e.g. `retrieval`, `pipeline`) |
| `event`                  | string | Structured event name                   |
| `release`                | string | Application release/version             |
| `trace_id`               | string | Distributed trace ID                    |
| `langfuse_trace_id`      | string | Langfuse trace ID for LLM observability |
| `request_id`             | string | Per-request unique identifier           |
| `telegram_user_id_hash`  | string | SHA-256 hash of Telegram user ID        |
| `chat_id_hash`           | string | SHA-256 hash of Telegram chat ID        |
| `tenant_id`              | string | Multi-tenant identifier (future use)    |
| `bot_instance_id`        | string | Bot instance identifier (future use)    |
| `deployment_id`          | string | Deployment identifier (future use)      |
| `route`                  | string | Handler/route that processed the request|
| `pipeline_mode`          | string | Pipeline mode (e.g. `direct`, `rewrite`)|
| `llm_model`              | string | LLM model used for generation           |
| `dependency_status`      | string | Status of external dependency           |
| `error_type`             | string | Categorized error type                  |
| `latency_ms`             | float  | Request/operation latency in ms         |
| `cache_hit`              | bool   | Whether a cache hit occurred            |

## PII Safety Rules

**Never log the following raw fields:**

- `user_id` (use `telegram_user_id_hash` instead)
- `query` / `raw_query` / `text` / `answer_text`
- `phone`
- `email`
- `token`
- `password`
- `secret`

These fields are blocked at the formatter level and will not appear in JSON output
regardless of what is set on the log record.

Safe alternatives:
- Use hashed identifiers (`telegram_user_id_hash`, `chat_id_hash`)
- Log operational metrics (`latency_ms`, `cache_hit`, `pipeline_mode`)
- Log event names without content (`event: "query_processed"`)

## Loki Label Strategy

To avoid high-cardinality label explosion in Grafana Loki:

**Use as Loki labels (low cardinality):**
- `service` - one of a fixed set of service names
- `environment` - development, staging, production

**Keep in JSON payload only (high cardinality):**
- `trace_id`, `request_id`, `langfuse_trace_id`
- `telegram_user_id_hash`, `chat_id_hash`
- `tenant_id`, `bot_instance_id`, `deployment_id`
- `route`, `pipeline_mode`, `llm_model`
- All other optional fields

Promtail/Alloy should extract `service` and `environment` from JSON
and use them as stream labels. Everything else remains searchable
via Loki's JSON filter expressions (e.g. `| json | trace_id="abc"`).

## Correlation ID Propagation

Three correlation IDs enable end-to-end request tracing:

1. **`trace_id`** - Distributed trace ID (shared across services via headers)
2. **`langfuse_trace_id`** - Langfuse-specific trace for LLM call lineage
3. **`request_id`** - Per-request ID generated at the entry point

These are propagated via:
- `ContextVar` in `src/observability/log_context.py`
- `ObservabilityLogFilter` attached to loggers
- Sentry context via `set_sentry_context()`

### Usage Pattern

```python
from src.observability.log_context import set_log_context, clear_log_context

# At request entry point
set_log_context(
    trace_id=generate_trace_id(),
    request_id=generate_request_id(),
    langfuse_trace_id=langfuse_trace.id,
)

# ... all subsequent logs automatically include these fields ...

# At request exit
clear_log_context()
```

## Multi-Tenant Fields (Future Use)

The following fields are reserved for future multi-tenant deployments:

- `tenant_id` - Identifies the tenant/organization
- `bot_instance_id` - Identifies a specific bot instance within a tenant
- `deployment_id` - Identifies the deployment (e.g. canary vs stable)

These fields are supported in the log contract today but are not actively
populated until multi-tenancy is implemented.

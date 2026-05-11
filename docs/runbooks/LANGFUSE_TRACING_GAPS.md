# Runbook: Langfuse Tracing Gaps

- **Owner:** Observability / On-call
- **Last verified:** 2026-05-07
- **Verification command:** `make validate-traces-fast`

Use this runbook when traces are missing from Langfuse or observability is broken.

## Symptoms

- Queries not appearing in Langfuse UI
- Incomplete traces (missing spans)
- `make validate-traces-fast` failing
- Missing scores in Langfuse
- Traces show `LLM failed: Connection error` despite healthy Langfuse ingestion
- Repeated traceback spam with `HTTPConnectionPool(host='localhost', port=3001)` when running bot natively and local Langfuse is down

Expected local behavior after #1446: one warning from `telegram_bot.observability` that the configured endpoint is unreachable, then tracing export is disabled for that process.

## Quick Validation Focus

When traces appear missing, validate **app pipeline coverage** first:

- Required direct trace families: **`rag-api-query`**, **`voice-session`**, **`ingestion-cli-run`**
- Required Telegram families under `telegram-message` observations: **`telegram-rag-query`**, **`telegram-rag-supervisor`**
- Required sanitized root fields on `telegram-message.input`: **`content_type`**, **`query_preview`**, **`query_hash`**, **`query_len`**, **`route`**
- Forbidden raw root fields on `telegram-message.input`: **`user`**, **`chat`**, **`message`**, **`event_from_user`**, **`event_chat`**, **`raw_update`**
- Expected LiteLLM callback noise: **`litellm-acompletion`** (flat, proxy-generated, no session context)

If direct families and nested Telegram families are present and root input is sanitized, flat `litellm-acompletion` traces do **not** indicate a defect.

## Diagnosis

### 1. Check Langfuse Connectivity

```bash
# Ping Langfuse
curl -s ${LANGFUSE_HOST}/api/public/health | jq

# Should return {"status": "ok"}
```

If `LANGFUSE_HOST` points to local Langfuse (for example `http://localhost:3001`) and health check fails, either:
- start the local ML/Langfuse stack (`make docker-ml-up`), or
- disable Langfuse tracing for native local run (`unset LANGFUSE_HOST` or `LANGFUSE_TRACING_ENABLED=false`).

Langfuse is part of the `ml` profile with ClickHouse, MinIO, and
`redis-langfuse`. The `obs` profile (`make docker-obs-up` or
`make monitoring-up`) is for Loki, Promtail, and Alertmanager; it does not
start Langfuse.

### 2. Verify Environment Variables (Presence Only)

```bash
# Check that required variables are present (do not print values)
for v in LANGFUSE_PUBLIC_KEY LANGFUSE_SECRET_KEY LANGFUSE_HOST; do
  grep -q "^${v}=" .env && echo "${v}: present" || echo "${v}: MISSING"
done

# Required:
# LANGFUSE_PUBLIC_KEY
# LANGFUSE_SECRET_KEY
# LANGFUSE_HOST (should be full URL, not just hostname)
```

### 3. Latest Trace API Fast Path

```bash
# List the most recent traces with full inline fields
langfuse api traces list --limit 20 --order-by timestamp.desc --fields core,io,scores,observations,metrics --json

# Filter to a specific required trace family
langfuse api traces list --name rag-api-query --limit 5 --order-by timestamp.desc --fields core,io,scores,observations,metrics --json
langfuse api traces list --name voice-session --limit 5 --order-by timestamp.desc --fields core,io,scores,observations,metrics --json
langfuse api traces list --name ingestion-cli-run --limit 5 --order-by timestamp.desc --fields core,io,scores,observations,metrics --json

# Get a specific trace with inline observations and scores
langfuse api traces get <trace-id> --fields core,io,scores,observations,metrics --json

# List scores for a trace
langfuse api scores list --trace-id <trace-id> --json

# List observations for a trace
langfuse api observations list --trace-id <trace-id> --fields core,basic,io,metadata,usage,metrics --json
```

**Validation focus:** Check missing/stale `rag-api-query`, `voice-session`, `ingestion-cli-run`, then inspect recent `telegram-message` traces for nested `telegram-rag-query`/`telegram-rag-supervisor` observations plus sanitized root fields. Proxy-generated `litellm-acompletion` traces are expected flat noise and should not be treated as app coverage.

### 4. Trace Interpretation Matrix

| Trace Name | Expected Structure | Common Gaps |
|---|---|---|
| `telegram-message` | Deeply structured (25–35 obs, depth 8, 30+ scores) with sanitized root input (`content_type`, `query_preview`, `query_hash`, `query_len`, `route`) | Missing when bot observability client fails to initialize or middleware is skipped; contract fails if raw `user/chat/message` payloads appear |
| `litellm-acompletion` | Flat (1 GENERATION, depth 0, 0 scores) | **Proxy-generated**, not app-instrumented; inherently flat and lacks session context. See [LiteLLM Failure Runbook](LITEllm_FAILURE.md) |
| `rag-api-query` | Structured SPANs + GENERATION | Often missing if RAG API is not called or `@observe` decorator is bypassed |
| `core-pipeline-query-embedding` | SPAN (`as_type="embedding"`, capture disabled) | Missing or orphaned when the embedding call runs inside `run_in_executor` without preserving `contextvars` |
| `voice-session` | Structured (capture disabled) | Missing when voice/LiveKit is off by default or voice agent did not start |
| `ingestion-cli-run` | Structured (capture disabled) | Becomes stale when unified ingestion CLI has not run recently; check `make ingest-unified-status` |
| `openai-contextualize` | SPAN with nested GENERATION (auto-traced via `langfuse.openai` drop-in) | Missing if `OpenAIContextualizer` uses plain `openai` clients; inner completions would become orphan `litellm-acompletion` traces |

**Key distinction:** `litellm-acompletion` traces are created by the LiteLLM proxy's built-in Langfuse callback (`success_callback: ["langfuse"]`), not by the application's `@observe` decorators. They will never contain child spans, scores, or session attribution.

### 5. Check Observability Module

```python
# Test Langfuse client
from telegram_bot.observability import get_client

lf = get_client()
print(f"Langfuse initialized: {lf is not None}")
print(f"Current trace: {lf.get_current_trace_id()}")
```

### 6. Run Trace Validation

```bash
make validate-traces-fast
```

This checks required direct families plus Telegram nested-family/root-context contract. Validation should focus on missing or outdated:
- `rag-api-query`
- `voice-session`
- `ingestion-cli-run`
- `telegram-rag-query` and `telegram-rag-supervisor` under `telegram-message` observations
- sanitized `telegram-message.input` fields (`content_type`, `query_preview`, `query_hash`, `query_len`, `route`)

If these are present and fresh, flat `litellm-acompletion` traces are expected proxy-generated noise and do not indicate a defect.

## Common Issues

### "Public key not valid" Error

**Cause:** Invalid or expired Langfuse API keys.

**Fix:**
1. Get new keys from Langfuse dashboard
2. Update `.env` with the new keys (do not commit the file):
   ```
   LANGFUSE_PUBLIC_KEY=<your-public-key>
   LANGFUSE_SECRET_KEY=<your-secret-key>
   ```
3. Restart bot

### Prisma `P1000 Authentication failed against database server` During `make validate-traces-fast`

**Cause:** `validate-traces-fast` fell back to `tests/fixtures/compose.ci.env` (no `.env` present), while an existing local Postgres volume (`dev_postgres_data`) was initialized with a password that does not match the fallback `POSTGRES_PASSWORD`.

**Fix:**
1. Create/update `.env` with the `POSTGRES_PASSWORD` used when the volume was initialized.
2. Or delete the stale local volume and let Compose reinitialize it:
   ```bash
   docker volume rm dev_postgres_data
   ```
3. Re-run `make validate-traces-fast`.

`validate-traces-fast` includes a preflight guard that allows the known-safe fallback (`POSTGRES_PASSWORD=postgres`) with existing `dev_postgres_data`, and fails early when fallback password and existing volume credentials can mismatch.

### Trace Family Missing

**Cause:** Span not properly decorated with `@observe`.

**Fix:** Ensure all RAG operations use `@observe` decorator:

```python
from telegram_bot.observability import observe

@observe(name="my-operation")
async def my_operation():
    ...
```

### Scores Not Written

**Cause:** `write_langfuse_scores()` not called after pipeline execution.

**Fix:** Ensure scoring is called:

```python
from telegram_bot.scoring import write_langfuse_scores

result = await graph.ainvoke(state)
write_langfuse_scores(lf, result, trace_id=trace_id)
```

### Embedding Span Missing or Orphaned (`core-pipeline-query-embedding`)

**Cause:** The core RAG pipeline runs query embedding inside a thread-pool via `run_in_executor`. Langfuse spans rely on `contextvars` for parent-trace linkage; standard `run_in_executor` drops that context, so the span becomes orphaned or invisible.

**Fix:** Wrap the observed call with `contextvars.copy_context()` and `Context.run()`:

```python
import contextvars

loop = asyncio.get_event_loop()
ctx = contextvars.copy_context()
query_embedding = await loop.run_in_executor(
    None, lambda: ctx.run(self._encode_query, query)
)
```

Where `_encode_query` is decorated as:

```python
@observe(
    name="core-pipeline-query-embedding",
    as_type="embedding",
    capture_input=False,
    capture_output=False,
)
def _encode_query(self, query: str):
    ...
```

**Prevention:** All embedding spans (including `bge-m3-*`, `search-engine-*`, and pipeline spans) must keep `capture_input=False` and `capture_output=False` to avoid leaking raw vectors or query text into Langfuse.

### Flat `litellm-acompletion` Traces Everywhere

**Cause:** LiteLLM proxy is logging every LLM call as a standalone trace via its native Langfuse callback. This is expected behavior, but it produces flat traces with no pipeline context.

**Fix (informational):**
- Do not chase missing spans inside `litellm-acompletion` — it will never have them.
- If you need structured LLM spans, look for `generate-answer` or `service-generate-response` inside `telegram-message` traces instead.
- If the noise is excessive, consider disabling the LiteLLM callback in `docker/litellm/config.yaml` and relying on app-native `@observe` decorators alone (requires product decision).

## Remediation

> **Caution:** Mutating commands below. Run only after confirming the diagnosis above.

### Restart Observability

```bash
docker compose restart bot
```

### Clear Langfuse Cache

If keys were rotated:

```bash
# In bot container
redis-cli DEL langfuse:prompt_cache
```

### Enable Debug Logging

Add to `.env` (do not commit):

```bash
LOG_LEVEL=DEBUG
LOG_observability=DEBUG
```

Then restart the bot:

```bash
docker compose restart bot
```

## Prevention

- Regular `make validate-traces-fast` runs
- Monitor Langfuse ingestion rate
- Alert on trace family gaps
- Distinguish proxy-generated `litellm-acompletion` traces from app-instrumented `telegram-message` traces when triaging gaps

## See Also

- [Docker Services Reference](../../DOCKER.md)
- [Local Development Guide](../LOCAL-DEVELOPMENT.md)
- [LiteLLM Failure Runbook](LITEllm_FAILURE.md)

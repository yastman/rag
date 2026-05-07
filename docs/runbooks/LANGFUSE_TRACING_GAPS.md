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

## Diagnosis

### 1. Check Langfuse Connectivity

```bash
# Ping Langfuse
curl -s ${LANGFUSE_HOST}/api/public/health | jq

# Should return {"status": "ok"}
```

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
# List the most recent trace of each family
langfuse api traces list --limit 20 --order-by timestamp.desc

# Get a specific trace with inline observations and scores
langfuse api traces get <trace-id> --fields core,io,scores,observations,metrics --json
```

### 4. Trace Interpretation Matrix

| Trace Name | Expected Structure | Common Gaps |
|---|---|---|
| `telegram-message` | Deeply structured (25–35 obs, depth 8, 30+ scores) | Missing when bot observability client fails to initialize or middleware is skipped |
| `litellm-acompletion` | Flat (1 GENERATION, depth 0, 0 scores) | **Proxy-generated**, not app-instrumented; inherently flat and lacks session context. See [LiteLLM Failure Runbook](LITEllm_FAILURE.md) |
| `rag-api-query` | Structured SPANs + GENERATION | Often missing if RAG API is not called or `@observe` decorator is bypassed |
| `voice-session` | Structured (capture disabled) | Missing when voice/LiveKit is off by default or voice agent did not start |
| `ingestion-cli-run` | Structured (capture disabled) | Becomes stale when unified ingestion CLI has not run recently; check `make ingest-unified-status` |

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

This checks that required trace families exist:
- `rag-api-query`
- `voice-session`
- `ingestion-cli-run`

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

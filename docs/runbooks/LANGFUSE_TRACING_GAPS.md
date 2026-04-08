# Runbook: Langfuse Tracing Gaps

Use this runbook when traces are missing from Langfuse or observability is broken.

## Symptoms

- Queries not appearing in Langfuse UI
- Incomplete traces (missing spans)
- `make validate-traces-fast` failing
- Missing scores in Langfuse

## Diagnosis

### 1. Check Langfuse Connectivity

```bash
# Ping Langfuse
curl -s ${LANGFUSE_HOST}/api/public/health | jq

# Should return {"status": "ok"}
```

### 2. Verify Environment Variables

```bash
# Check Langfuse config
grep -E "LANGFUSE|LITELLM" .env

# Required:
# LANGFUSE_PUBLIC_KEY
# LANGFUSE_SECRET_KEY
# LANGFUSE_HOST (should be full URL, not just hostname)
```

### 3. Check Observability Module

```python
# Test Langfuse client
from telegram_bot.observability import get_client

lf = get_client()
print(f"Langfuse initialized: {lf is not None}")
print(f"Current trace: {lf.get_current_trace_id()}")
```

### 4. Run Trace Validation

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
2. Update `.env`:
   ```
   LANGFUSE_PUBLIC_KEY=pk_live_xxx
   LANGFUSE_SECRET_KEY=sk_live_xxx
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

## Remediation

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

```bash
# Add to .env
LOG_LEVEL=DEBUG
LOG_observability=DEBUG
```

## Prevention

- Regular `make validate-traces-fast` runs
- Monitor Langfuse ingestion rate
- Alert on trace family gaps

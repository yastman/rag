***REMOVED*** Runbook: Langfuse Tracing Gaps

Use this runbook when traces are missing from Langfuse or observability is broken.

***REMOVED******REMOVED*** Symptoms

- Queries not appearing in Langfuse UI
- Incomplete traces (missing spans)
- `make validate-traces-fast` failing
- Missing scores in Langfuse

***REMOVED******REMOVED*** Diagnosis

***REMOVED******REMOVED******REMOVED*** 1. Check Langfuse Connectivity

```bash
***REMOVED*** Ping Langfuse
curl -s ${LANGFUSE_HOST}/api/public/health | jq

***REMOVED*** Should return {"status": "ok"}
```

***REMOVED******REMOVED******REMOVED*** 2. Verify Environment Variables

```bash
***REMOVED*** Check Langfuse config
grep -E "LANGFUSE|LITELLM" .env

***REMOVED*** Required:
***REMOVED*** LANGFUSE_PUBLIC_KEY
***REMOVED*** LANGFUSE_SECRET_KEY
***REMOVED*** LANGFUSE_HOST (should be full URL, not just hostname)
```

***REMOVED******REMOVED******REMOVED*** 3. Check Observability Module

```python
***REMOVED*** Test Langfuse client
from telegram_bot.observability import get_client

lf = get_client()
print(f"Langfuse initialized: {lf is not None}")
print(f"Current trace: {lf.get_current_trace_id()}")
```

***REMOVED******REMOVED******REMOVED*** 4. Run Trace Validation

```bash
make validate-traces-fast
```

This checks that required trace families exist:
- `rag-api-query`
- `voice-session`
- `ingestion-cli-run`

***REMOVED******REMOVED*** Common Issues

***REMOVED******REMOVED******REMOVED*** "Public key not valid" Error

**Cause:** Invalid or expired Langfuse API keys.

**Fix:**
1. Get new keys from Langfuse dashboard
2. Update `.env`:
   ```
   LANGFUSE_PUBLIC_KEY=pk_live_xxx
   LANGFUSE_SECRET_KEY=sk_live_xxx
   ```
3. Restart bot

***REMOVED******REMOVED******REMOVED*** Trace Family Missing

**Cause:** Span not properly decorated with `@observe`.

**Fix:** Ensure all RAG operations use `@observe` decorator:

```python
from telegram_bot.observability import observe

@observe(name="my-operation")
async def my_operation():
    ...
```

***REMOVED******REMOVED******REMOVED*** Scores Not Written

**Cause:** `write_langfuse_scores()` not called after pipeline execution.

**Fix:** Ensure scoring is called:

```python
from telegram_bot.scoring import write_langfuse_scores

result = await graph.ainvoke(state)
write_langfuse_scores(lf, result, trace_id=trace_id)
```

***REMOVED******REMOVED*** Remediation

***REMOVED******REMOVED******REMOVED*** Restart Observability

```bash
docker compose restart bot
```

***REMOVED******REMOVED******REMOVED*** Clear Langfuse Cache

If keys were rotated:

```bash
***REMOVED*** In bot container
redis-cli DEL langfuse:prompt_cache
```

***REMOVED******REMOVED******REMOVED*** Enable Debug Logging

```bash
***REMOVED*** Add to .env
LOG_LEVEL=DEBUG
LOG_observability=DEBUG
```

***REMOVED******REMOVED*** Prevention

- Regular `make validate-traces-fast` runs
- Monitor Langfuse ingestion rate
- Alert on trace family gaps

***REMOVED*** Runbook: LiteLLM Failure and Fallback Behavior

Use this runbook when LiteLLM provider has outages or LLM calls are failing.

***REMOVED******REMOVED*** Symptoms

- `LLM_TIMEOUT` errors in logs
- `Model not found` (404) errors
- Extremely high latency on all LLM calls
- No responses from bot despite successful retrieval

***REMOVED******REMOVED*** Diagnosis

***REMOVED******REMOVED******REMOVED*** 1. Check LiteLLM Logs

```bash
***REMOVED*** Check if LiteLLM container is running
docker compose ps litellm

***REMOVED*** View LiteLLM logs
docker compose logs litellm --tail=100
```

***REMOVED******REMOVED******REMOVED*** 2. Test LiteLLM Connectivity

```bash
***REMOVED*** Health check
curl http://localhost:4000/health

***REMOVED*** Or your configured LiteLLM URL
curl ${LITELLM_URL}/health
```

***REMOVED******REMOVED******REMOVED*** 3. Check Model Availability

```bash
***REMOVED*** List available models via LiteLLM proxy
curl http://localhost:4000/v1/models
```

***REMOVED******REMOVED******REMOVED*** 4. Check Bot Logs for LLM Errors

```bash
docker compose logs bot 2>&1 | grep -i "llm\|openai\|timeout" | tail -50
```

***REMOVED******REMOVED*** Common Error Patterns

***REMOVED******REMOVED******REMOVED*** "Model gpt-4o-mini not found" (404)

**Cause:** `LLM_BASE_URL` points directly to Cerebras instead of LiteLLM proxy.

**Fix:**
```bash
***REMOVED*** Check LITELLM configuration
grep -E "LLM_BASE_URL|LITELLM" .env

***REMOVED*** Should be:
***REMOVED*** LLM_BASE_URL=http://litellm:4000
***REMOVED*** Not pointing directly to cerebras
```

***REMOVED******REMOVED******REMOVED*** Timeout Errors

**Cause:** LiteLLM proxy can't reach upstream LLM provider.

**Fix:**
1. Check upstream provider status
2. Increase timeout in LiteLLM config
3. Enable fallback models

***REMOVED******REMOVED*** Fallback Behavior

The bot has graceful degradation for LLM failures:

1. **Streaming fallback** — If streaming fails, falls back to non-streaming
2. **Safe fallback response** — If LLM completely unavailable, returns pre-defined safe response
3. **Cache fallback** — If LLM is slow, cached responses may be served

***REMOVED******REMOVED*** Remediation

***REMOVED******REMOVED******REMOVED*** Restart LiteLLM

```bash
docker compose restart litellm
```

***REMOVED******REMOVED******REMOVED*** Switch LLM Provider

If using multiple providers:

1. Update `LLM_BASE_URL` to new provider
2. Restart bot:
   ```bash
   docker compose restart bot
   ```

***REMOVED******REMOVED******REMOVED*** Configure Fallback Models

In `compose.yml` or `.env`:

```bash
LITELLM_MODEL=azure/gpt-4o-mini
LITELLM_FALLBACK_MODELS=gpt-4o,gpt-4o-mini
```

***REMOVED******REMOVED*** Impact on RAG Quality

When LLM fallback occurs:
- Responses may be less contextual
- No streaming (slower perceived response)
- Safe fallback responses are generic

***REMOVED******REMOVED*** Prevention

- Monitor LiteLLM uptime
- Set up alerts for LLM timeout rates
- Regular health checks: `curl ${LLM_BASE_URL}/health`

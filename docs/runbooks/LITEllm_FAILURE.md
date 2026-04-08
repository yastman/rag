# Runbook: LiteLLM Failure and Fallback Behavior

Use this runbook when LiteLLM provider has outages or LLM calls are failing.

## Symptoms

- `LLM_TIMEOUT` errors in logs
- `Model not found` (404) errors
- Extremely high latency on all LLM calls
- No responses from bot despite successful retrieval

## Diagnosis

### 1. Check LiteLLM Logs

```bash
# Check if LiteLLM container is running
docker compose ps litellm

# View LiteLLM logs
docker compose logs litellm --tail=100
```

### 2. Test LiteLLM Connectivity

```bash
# Health check
curl http://localhost:4000/health

# Or your configured LiteLLM URL
curl ${LITELLM_URL}/health
```

### 3. Check Model Availability

```bash
# List available models via LiteLLM proxy
curl http://localhost:4000/v1/models
```

### 4. Check Bot Logs for LLM Errors

```bash
docker compose logs bot 2>&1 | grep -i "llm\|openai\|timeout" | tail -50
```

## Common Error Patterns

### "Model gpt-4o-mini not found" (404)

**Cause:** `LLM_BASE_URL` points directly to Cerebras instead of LiteLLM proxy.

**Fix:**
```bash
# Check LITELLM configuration
grep -E "LLM_BASE_URL|LITELLM" .env

# Should be:
# LLM_BASE_URL=http://litellm:4000
# Not pointing directly to cerebras
```

### Timeout Errors

**Cause:** LiteLLM proxy can't reach upstream LLM provider.

**Fix:**
1. Check upstream provider status
2. Increase timeout in LiteLLM config
3. Enable fallback models

## Fallback Behavior

The bot has graceful degradation for LLM failures:

1. **Streaming fallback** — If streaming fails, falls back to non-streaming
2. **Safe fallback response** — If LLM completely unavailable, returns pre-defined safe response
3. **Cache fallback** — If LLM is slow, cached responses may be served

## Remediation

### Restart LiteLLM

```bash
docker compose restart litellm
```

### Switch LLM Provider

If using multiple providers:

1. Update `LLM_BASE_URL` to new provider
2. Restart bot:
   ```bash
   docker compose restart bot
   ```

### Configure Fallback Models

In `compose.yml` or `.env`:

```bash
LITELLM_MODEL=azure/gpt-4o-mini
LITELLM_FALLBACK_MODELS=gpt-4o,gpt-4o-mini
```

## Impact on RAG Quality

When LLM fallback occurs:
- Responses may be less contextual
- No streaming (slower perceived response)
- Safe fallback responses are generic

## Prevention

- Monitor LiteLLM uptime
- Set up alerts for LLM timeout rates
- Regular health checks: `curl ${LLM_BASE_URL}/health`

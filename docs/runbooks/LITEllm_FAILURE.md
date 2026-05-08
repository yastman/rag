# Runbook: LiteLLM Failure and Fallback Behavior

- **Owner:** LLM Proxy / On-call
- **Last verified:** 2026-05-07
- **Verification command:** `curl -s http://localhost:4000/health`

Use this runbook when LiteLLM provider has outages or LLM calls are failing.

## Symptoms

- `LLM_TIMEOUT` errors in logs
- `Model not found` (404) errors
- Extremely high latency on all LLM calls
- No responses from bot despite successful retrieval
- Traces show `LLM failed: Connection error` while Langfuse ingestion appears healthy
- LiteLLM container exits with code `137` (`OOMKilled`)

## Diagnosis

### Verify Current Primary / Fallback Routing (read-only)

Before restarting or editing config, confirm the active routing from the repo config files:

```bash
# Primary model for the gpt-4o-mini group (read-only)
grep -A8 'model_name: gpt-4o-mini' docker/litellm/config.yaml

# Fallback chain
grep -A5 'fallbacks:' docker/litellm/config.yaml

# Kubernetes equivalent
grep -A8 'model_name: gpt-4o-mini' k8s/base/configmaps/litellm-config.yaml
grep -A5 'fallbacks:' k8s/base/configmaps/litellm-config.yaml
```

Expected state (do **not** change without product decision):

| Alias | Maps to | Role |
|---|---|---|
| `gpt-4o-mini` | `cerebras/zai-glm-4.7` (GLM 4.7) | **Primary** — low TTFT, reasoning disabled |
| `gpt-4o-mini-cerebras-oss` | `cerebras/gpt-oss-120b` | Fallback 1 — reasoning, slower TTFT |
| `gpt-4o-mini-fallback` | `groq/llama-3.1-70b-versatile` | Fallback 2 — fast, free tier |
| `gpt-4o-mini-openai` | `openai/gpt-4o-mini` | Fallback 3 — reliable |

- **Do not switch the primary back to a 120B model.** The `gpt-oss-120b` alias is reserved for benchmarking and fallback.
- The bot sends requests to alias `gpt-4o-mini` (see `telegram_bot/graph/config.py`). `telegram_bot/config.py` sets a native default of `zai-glm-4.7` when running without the proxy.

### 1. Check LiteLLM Container State

```bash
# Check if LiteLLM container is running
docker compose ps litellm

# View bounded LiteLLM logs
docker compose logs litellm --tail=100
```

### 2. Test LiteLLM Connectivity

```bash
# Health check
curl -s http://localhost:4000/health | jq

# Or your configured LiteLLM URL
curl -s ${LITELLM_URL}/health | jq
```

### 3. Check Model Availability

```bash
# List available models via LiteLLM proxy
curl -s http://localhost:4000/v1/models | jq
```

### 4. Check Bot Logs for LLM Errors

```bash
docker compose logs bot 2>&1 | grep -i "llm\|openai\|timeout" | tail -50
```

### 5. OOM / Exit 137 Diagnosis

If the LiteLLM container is restarting or missing:

```bash
# Inspect exit status and OOM flag
docker inspect <litellm-container> --format '
  Name={{.Name}}
  OOMKilled={{.State.OOMKilled}}
  ExitCode={{.State.ExitCode}}
  Status={{.State.Status}}
'

# Bounded recent logs around the crash
docker compose logs litellm --tail=200 | grep -i "killed\|oom\|memory\|137"
```

**Interpretation:**
- `OOMKilled=true` or `ExitCode=137` → LiteLLM was killed by the kernel due to memory exhaustion.
- `Status=restarting` with `OOMKilled=false` → Likely a configuration or upstream provider error; inspect logs for `ZodError`, `P1000`, or connection refused messages.
- If health endpoint returns `200` but models list is empty → LiteLLM is alive but cannot reach upstream providers.

### 6. Verify Environment Variables (Presence Only)

```bash
# Check that required variables are present (do not print values)
for v in LLM_BASE_URL LITELLM_URL LITELLM_MASTER_KEY; do
  grep -q "^${v}=" .env && echo "${v}: present" || echo "${v}: MISSING"
done

# Should be:
# LLM_BASE_URL=http://litellm:4000
# Not pointing directly to an upstream provider
```

### 7. Distinguish Langfuse Healthy vs LLM Unhealthy

Langfuse ingestion can be **fully healthy** while traces show `LLM failed: Connection error`.

**Why:** Langfuse traces capture the *attempt* to call the LLM. If LiteLLM or the upstream provider is unreachable, the trace still ingests, but the LLM span records a connection failure. The ingestion pipeline itself is independent of the LLM proxy's availability.

**Fast path to confirm:**
1. Check Langfuse health: `curl -s ${LANGFUSE_HOST}/api/public/health` → expect `{"status": "ok"}`
2. Check LiteLLM health: `curl -s http://localhost:4000/health` → expect `true` or a healthy body
3. If Langfuse is OK but LiteLLM health fails → root cause is LiteLLM or upstream provider, not Langfuse

## Common Error Patterns

### "Model gpt-4o-mini not found" (404)

**Cause:** `LLM_BASE_URL` points directly to Cerebras instead of LiteLLM proxy.

**Fix:**
```bash
# Check LITELLM configuration (presence only)
grep -q "^LLM_BASE_URL=" .env && echo "LLM_BASE_URL: present" || echo "LLM_BASE_URL: MISSING"
grep -q "^LITELLM" .env && echo "LITELLM vars: present" || echo "LITELLM vars: MISSING"

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

> **Caution:** Mutating commands below. Run only after confirming the diagnosis above.

### Restart LiteLLM

```bash
docker compose restart litellm
```

### Increase LiteLLM Memory Limit

If OOM is confirmed, raise the memory limit in `compose.yml` or `compose.override.yml` and recreate:

```bash
docker compose up -d --force-recreate litellm
```

### Switch LLM Provider

If using multiple providers:

1. Update `LLM_BASE_URL` to new provider in `.env` (do not commit)
2. Restart bot:
   ```bash
   docker compose restart bot
   ```

### Configure Fallback Models

> **Caution:** Do not switch the primary model back to a 120B model (e.g., `cerebras/gpt-oss-120b`). GLM 4.7 (`cerebras/zai-glm-4.7`) remains the primary for low TTFT. Changing the primary requires a product decision.

The canonical routing is defined in `docker/litellm/config.yaml` (Docker) and `k8s/base/configmaps/litellm-config.yaml` (K8s). Verify before editing:

```bash
grep -A8 'model_name: gpt-4o-mini' docker/litellm/config.yaml
grep -A5 'fallbacks:' docker/litellm/config.yaml
```

If you must adjust fallback ordering, edit the config file and restart:

```bash
docker compose restart litellm
```

## Impact on RAG Quality

When LLM fallback occurs:
- Responses may be less contextual
- No streaming (slower perceived response)
- Safe fallback responses are generic

## Prevention

- Monitor LiteLLM uptime
- Set up alerts for LLM timeout rates
- Regular health checks: `curl -s ${LLM_BASE_URL}/health`
- Watch for `OOMKilled` in container state after deploys or traffic spikes

## See Also

- [Langfuse Tracing Gaps](LANGFUSE_TRACING_GAPS.md)
- [Docker Services Reference](../../DOCKER.md)
- [Local Development Guide](../LOCAL-DEVELOPMENT.md)

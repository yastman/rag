# Runbook: LightRAG Failure

- **Owner:** Graph RAG / On-call
- **Last verified:** 2026-05-15
- **Verification command:** `curl -s http://localhost:9621/health`

Use this runbook when LightRAG graph retrieval is unavailable or producing errors.

## Symptoms

- `LightRAGDown` alert fires (no logs from `dev-lightrag` for 10+ minutes)
- `LightRAGError` alert fires (repeated errors/exceptions/tracebacks in container logs)
- `LightRAGAPIError` alert fires (OpenAI or upstream API errors, rate limiting)
- Graph-augmented retrieval returns empty results while vector search still works
- Bot responses lack relationship or entity context that graph retrieval normally provides
- Container `dev-lightrag` is missing from `docker compose ps` output or shows `Exited`

## Diagnosis

### 1. Check Container State

```bash
# Is the container running?
docker compose ps lightrag

# Recent logs (bounded)
docker compose logs lightrag --tail=100
```

### 2. Health Check

```bash
# Default health endpoint
curl -s http://localhost:9621/health | jq

# Or using the configured URL
curl -s ${LIGHTRAG_URL:-http://localhost:9621}/health | jq
```

**Interpretation:**
- `200` response with healthy body: LightRAG is alive and serving requests.
- Connection refused: container is down or not listening on port 9621.
- `5xx` response: LightRAG is running but unhealthy (check logs for root cause).

### 3. Check for API/Provider Errors

The `LightRAGAPIError` alert triggers on OpenAI API errors or rate limiting:

```bash
# Look for API-related errors
docker compose logs lightrag --tail=200 | grep -iE "openai.*error|api.*error|rate.*limit"

# Check for authentication failures
docker compose logs lightrag --tail=200 | grep -iE "auth|401|403|invalid.*key"
```

**Common API error patterns:**
- `openai.RateLimitError` or `429` responses: upstream rate limiting
- `openai.AuthenticationError` or `401`: invalid or expired API key
- `openai.APIConnectionError`: cannot reach LLM provider (check LiteLLM proxy)

### 4. Check for General Errors

The `LightRAGError` alert triggers on repeated errors, exceptions, or tracebacks:

```bash
# Count error frequency
docker compose logs lightrag --tail=500 | grep -ciE "error|exception|failed|traceback"

# View recent stack traces
docker compose logs lightrag --tail=500 | grep -A5 "Traceback"
```

### 5. Inspect Container Exit State

If the container has exited:

```bash
docker inspect dev-lightrag --format '
  Name={{.Name}}
  OOMKilled={{.State.OOMKilled}}
  ExitCode={{.State.ExitCode}}
  Status={{.State.Status}}
  Error={{.State.Error}}
'
```

**Interpretation:**
- `OOMKilled=true` or `ExitCode=137`: killed by the kernel due to memory exhaustion.
- `ExitCode=1`: application error on startup (check logs for missing config or failed connections).
- `Status=restarting`: crash loop, likely a configuration or dependency issue.

### 6. Verify Environment Variables (Presence Only)

```bash
# Check that required LLM variables are present (do not print values)
for v in OPENAI_API_KEY LIGHTRAG_URL; do
  grep -q "^${v}=" .env && echo "${v}: present" || echo "${v}: MISSING"
done
```

### 7. Check Upstream Dependencies

LightRAG depends on an LLM provider (via OpenAI-compatible API) for graph construction and queries:

```bash
# If using LiteLLM as the LLM proxy
curl -s http://localhost:4000/health | jq

# Check network connectivity from the container
docker compose exec lightrag curl -s http://litellm:4000/health 2>/dev/null || echo "Cannot reach LiteLLM from LightRAG"
```

## Remediation

> **Caution:** Mutating commands below. Run only after confirming the diagnosis above.

### Restart LightRAG

```bash
docker compose restart lightrag
```

Wait 30 seconds and verify:

```bash
curl -s http://localhost:9621/health | jq
```

### Recreate Container (Stale State or OOM)

If the container is in a crash loop or was OOM-killed:

```bash
docker compose up -d --force-recreate lightrag
```

### Fix API Key Issues

If the diagnosis shows authentication failures:

1. Verify the API key is set in `.env` (do not print it):
   ```bash
   grep -q "^OPENAI_API_KEY=" .env && echo "Key present" || echo "Key MISSING"
   ```
2. If the key is expired or invalid, update it in `.env` (do not commit secrets).
3. Restart the container:
   ```bash
   docker compose restart lightrag
   ```

### Handle Rate Limiting

If `LightRAGAPIError` is caused by rate limits:

1. Check the rate of graph queries in logs.
2. Consider reducing query frequency or switching to a higher-tier API plan.
3. If LiteLLM proxy is configured, verify fallback models are available:
   ```bash
   curl -s http://localhost:4000/v1/models | jq
   ```

### Increase Memory Limit (OOM)

If OOM is confirmed, increase the memory limit in the relevant compose file and recreate:

```bash
docker compose up -d --force-recreate lightrag
```

## Impact

When LightRAG is unavailable:
- Graph-based retrieval (entity relationships, knowledge graph traversal) is offline
- The system may fall back to vector-only search, losing relationship context
- Queries that rely on multi-hop reasoning over entities will have degraded quality

## Prevention

- Monitor container uptime via the `LightRAGDown` alert (3-minute window)
- Set up log-based alerting for repeated errors (`LightRAGError`, `LightRAGAPIError`)
- Regular health checks: `curl -s ${LIGHTRAG_URL:-http://localhost:9621}/health`
- Monitor API key expiration and rate limit headroom
- Watch for OOM events after deploying new graph data or increasing query load

## See Also

- [LiteLLM Failure Runbook](LITEllm_FAILURE.md)
- [Coverage Matrix](COVERAGE_MATRIX.md)
- [Docker Services Reference](../../DOCKER.md)
- [Local Development Guide](../LOCAL-DEVELOPMENT.md)

# Runbook: Langfuse Tracing Gaps

- **Owner:** Observability / On-call
- **Last verified:** 2026-05-12
- **Verification command:** make e2e-core-live

Use this runbook when traces are missing from Langfuse or observability is broken.

## Symptoms

- Queries not appearing in Langfuse UI
- Incomplete traces (missing spans)
- make e2e-core-live failing
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

### Cache-smoke behavior check

For cache regression checks:

1. Cold query should emit BGE-M3 encode, Qdrant, and LLM spans.
2. Immediate repeat of the same query should be a semantic cache hit path only and must not add fresh `bge-m3-encode-*`, Qdrant, or LLM spans.
3. The semantic-hit replay should not emit new `results_count=0` / `no_results=1` scoring artifacts.

### BGE-M3 hybrid trace check

For BGE-M3 hybrid retrieval regressions, verify the Langfuse trace through the
Langfuse API/CLI, not only by querying ClickHouse directly. The same trace must
contain:

- a workflow/root span such as `validation-query`, `rag-pipeline`, or `telegram-rag-query`
- `bge-m3-encode-*` client span
- matching `bge-m3-service-encode-*` service span
- `qdrant-hybrid-search-rrf` or `qdrant-hybrid-search-rrf-colbert`

Generate or select a fresh trace, then run:

```bash
TRACE_ID=<trace-id>
LF_ENV_FILE="${LF_ENV_FILE:-.env}" ./scripts/lf trace "$TRACE_ID" > /tmp/lf_trace.json
```

Required BGE/Qdrant families:

```bash
jq -e '(.observations | map(.name)) as $n
  | any($n[]; test("^bge-m3-encode-"))
  and any($n[]; test("^bge-m3-service-encode-"))
  and any($n[]; test("^qdrant-hybrid-search-rrf"))
' /tmp/lf_trace.json
```

BGE service spans must include curated model/runtime metadata and IO counters,
while keeping raw user text out of embedding spans:

```bash
jq -e '.observations
  | map(select(.name | test("^bge-m3-service-encode-"))) as $svc
  | ($svc | length) > 0
  and all($svc[];
    .metadata.model == "BAAI/bge-m3"
    and .metadata.runtime == "onnx-int8"
    and ((.metadata.encode_type // "") | length > 0)
    and ((.input.texts_count // 0) > 0)
    and ((.output.processing_time // 0) > 0)
  )
' /tmp/lf_trace.json
```

The service span must be nested under its client span in the same trace:

```bash
jq -e '.observations as $obs
  | ($obs | map(select(.id != null) | {key:.id, value:.name}) | from_entries) as $idx
  | all($obs[] | select(.name | test("^bge-m3-service-"));
      (.parentObservationId // "") != ""
      and (($idx[.parentObservationId] // "") | test("^bge-m3-(encode|rerank)"))
    )
' /tmp/lf_trace.json
```

## Diagnosis

### 1. Check Langfuse Connectivity

```bash
# Ping Langfuse
curl -s ${LANGFUSE_HOST}/api/public/health | jq

# Should return {"status": "ok"}
```

If `LANGFUSE_HOST` points to local Langfuse (for example `http://localhost:3001`) and health check fails, either:
- **Langfuse ML stack is archived (ARCH-08)**; disable tracing locally with:
- disable Langfuse tracing for native local run (`unset LANGFUSE_HOST` or `LANGFUSE_TRACING_ENABLED=false`).

Langfuse and the `ml` profile (ClickHouse, MinIO, redis-langfuse) are archived (ARCH-08). For local tracing, see `archive/ml/`.

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

# Get a specific trace with inline observations and scores (primary full-trace path)
langfuse api traces get <trace-id> --fields core,io,scores,observations,metrics --json

# List scores for a trace
langfuse api scores list --trace-id <trace-id> --json

# List observations for a trace
# In some local deployments this endpoint returns 404; use `traces get` as the primary full-tree command.
langfuse api observations list --trace-id <trace-id> --fields core,basic,io,metadata,usage,metrics --json
```

If `observations list` returns 404 in your deployment, continue with `traces get` and scores queries instead of treating `observations list` as a hard requirement.

**Validation focus:** Check missing/stale `rag-api-query`, `voice-session`, `ingestion-cli-run`, then inspect recent `telegram-message` traces for nested `telegram-rag-query`/`telegram-rag-supervisor` observations plus sanitized root fields. Use `traces get` for full trace trees. Proxy-generated `litellm-acompletion` traces are expected flat noise and should not be treated as app coverage.

### 4. Trace Interpretation Matrix

| Trace Name | Expected Structure | Common Gaps |
|---|---|---|
| `telegram-message` | Deeply structured (25–35 obs, depth 8, 30+ scores) with sanitized root input (`content_type`, `query_preview`, `query_hash`, `query_len`, `route`) | Missing when bot observability client fails to initialize or middleware is skipped; contract fails if raw `user/chat/message` payloads appear |
| `telegram-rag-supervisor` / `telegram-rag-query` | Nested under `telegram-message`; one per text-message turn | Missing when middleware is skipped; if appearing as a top-level trace, see #2157 / PR #2158 |
| `tool-rag-search` → `rag-pipeline` | Tool span wrapping the pipeline; **no** `langfuse_trace_id` forwarded into the pipeline (PR #2158) | If `rag-pipeline` becomes top-level, regression of #2157 — verify PR #2158 is merged |
| `rag-core-*` (5 helpers: `build-context`, `rewrite-query`, `perform-rerank`, `compute-query-embedding`, `check-semantic-cache`) | Nested under `rag-pipeline`; curated metadata only (PII-safe) | Missing if `telegram_bot/services/rag_core.py` decorators stripped — see PR #2163 |
| `litellm-acompletion` | Flat (1 GENERATION, depth 0, 0 scores) | **Proxy-generated**, not app-instrumented; inherently flat and lacks session context. See [LiteLLM Failure Runbook](LITEllm_FAILURE.md) |
| `rag-api-query` | Structured SPANs + GENERATION | Often missing if RAG API is not called or `@observe` decorator is bypassed |
| `core-pipeline-query-embedding` | SPAN (`as_type="embedding"`, capture disabled) | Missing or orphaned when the embedding call runs inside `run_in_executor` without preserving `contextvars` (see "Embedding Span Missing or Orphaned" below; PR #2167 closes the last `RAGPipeline.search` gap) |
| `voice-session` | Top-level SPAN per LiveKit call; opens via `start_as_current_observation` (PR #2165) | Missing when voice/LiveKit is off by default, the worker process did not call `_setup_langfuse`, or the entrypoint did not open the parent context — see PR #2165 |
| `voice-tool-search-knowledge-base` | Nested under `voice-session`; decorator stack `@function_tool() / @observe` (PR #2165) | If the tool span is missing while `voice-session` is present, the inner `@observe` was dropped during a LiveKit upgrade — re-stack decorators per PR #2165 |
| `ingestion-cli-run` | Structured (capture disabled) | Becomes stale when unified ingestion CLI has not run recently; check `make ingest-unified-status` |
| `openai-contextualize` | SPAN with nested GENERATION (auto-traced via `langfuse.openai` drop-in) | Missing if `OpenAIContextualizer` uses plain `openai` clients; inner completions would become orphan `litellm-acompletion` traces |

**Key distinction:** `litellm-acompletion` traces are created by LiteLLM SDK callbacks, not by the application's `@observe` decorators. They will never contain child spans, scores, or session attribution.

> **Full census.** The matrix above is intentionally a curated subset of
> the high-value families. The complete static census of every
> `@observe(name=...)` declaration that ships with the codebase
> (~190 named spans across 11 surface areas) is recorded in
> [`docs/observability/TRACE_COVERAGE_AUDIT_2168.md`](../observability/TRACE_COVERAGE_AUDIT_2168.md)
> and re-computable from `git grep '@observe(\s*name='`. When extending
> the matrix, prefer adding rows for families that have observed runtime
> failure modes; the audit document is the source of truth for "what
> exists in code" while this matrix is the source of truth for "what
> operators need to know to triage gaps".

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
make e2e-core-live
```

This checks required direct families plus Telegram nested-family/root-context contract. Validation should focus on missing or outdated:
- `rag-api-query`
- `voice-session`
- `ingestion-cli-run`
- `telegram-rag-query` and `telegram-rag-supervisor` under `telegram-message` observations
- sanitized `telegram-message.input` fields (`content_type`, `query_preview`, `query_hash`, `query_len`, `route`)

If these are present and fresh, flat `litellm-acompletion` traces are expected proxy-generated noise and do not indicate a defect.

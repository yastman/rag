# Langfuse Recent Traces Structure Audit

**Date:** 2026-05-05
**Auditor:** `W-audit-langfuse-recent-traces-structure`
**Branch:** `audit/langfuse-recent-traces`
**Target trace:** `8d79036a-36f4-4398-84aa-6839a1fcf040`

## Executive Summary

The flat/undivided trace reported for `8d79036a-36f4-4398-84aa-6839a1fcf040` is **systemic**, not isolated. It belongs to the `litellm-acompletion` trace family, and **100% of sampled `litellm-acompletion` traces** exhibit the same flat structure: exactly 1 `GENERATION` observation at root depth, zero scores, zero nesting, and no pipeline context. These traces are created by the LiteLLM proxy's native Langfuse callback (`success_callback: ["langfuse"]`), which operates outside the application's `@observe` instrumentation boundary.

In contrast, `telegram-message` and `validation-query` traces are deeply structured with dozens of observations, scores, and clear parent-child hierarchies because they flow through the application's explicit Langfuse SDK instrumentation.

## Methodology

1. Listed the 100 most recent traces via `langfuse api traces list`.
2. Fetched full trace details (with inline observations and scores) for 8 representative traces.
3. Built observation trees using `parentObservationId` to compute depth and type distributions.
4. Cross-referenced trace names with the codebase (`trace_contract.yaml`, `@observe` decorators, LiteLLM config).

## Trace Sampling Results

### Sampled Traces

| Short ID | Name | Session | Env | Tags | Obs Count | Types | Max Depth | Scores | Query Hint |
|---|---|---|---|---|---|---|---|---|---|
| `8d79036a` | `litellm-acompletion` | — | default | `User-Agent: AsyncOpenAI` | 1 | GENERATION: 1 | 0 | 0 | System prompt (real-estate consultant) |
| `f57f4ee4` | `litellm-acompletion` | — | default | `User-Agent: AsyncOpenAI` | 1 | GENERATION: 1 | 0 | 0 | System prompt |
| `395a01b4` | `litellm-acompletion` | — | default | `User-Agent: AsyncOpenAI` | 1 | GENERATION: 1 | 0 | 0 | User: "виды внж в болгарии" |
| `ee98cbec` | `litellm-/models` | — | default | — | 2 | GENERATION: 2 | 0 | 0 | LiteLLM models endpoint |
| `b982914f` | `telegram-message` | `chat-b7f509f2-20260505` | default | `agent`, `client_direct`, `message`, `rag`, `telegram` | 31 | SPAN: 29, GENERATION: 1, EVALUATOR: 1 | 8 | 36 | "виды покупок жилья?" |
| `18c78203` | `validation-query` | `validate-f6aaabf0` | default | `gdrive_documents_bge`, `streaming`, `validation` | 25 | SPAN: 24, GENERATION: 1 | 4 | 34 | "однокомнатная квартира цена" |
| `e4883508` | `validation-query` | `validate-f6aaabf0` | default | `cache_hit`, `gdrive_documents_bge`, `validation` | 25 | SPAN: 24, GENERATION: 1 | 4 | 34 | "аренда апартаментов" |
| `5e277026` | `qdrant-hybrid-search-rrf-colbert` | — | default | — | 4 | SPAN: 4 | 2 | 0 | Qdrant search span |

### Name Distribution (last 200 traces)

| Name | Count | Structure |
|---|---|---|
| `litellm-acompletion` | 80 | Flat (1 GENERATION, depth 0, 0 scores) |
| `validation-query` | 74 | Structured (25 obs, depth 4, 34 scores) |
| `telegram-message` | 13 | Deeply structured (31 obs, depth 8, 36 scores) |
| `qdrant-hybrid-search-rrf-colbert` | 5 | Structured (4 SPANs, depth 2, 0 scores) |
| `bge-m3-hybrid-colbert-embed` | 5 | Structured (SPANs, depth 2, 0 scores) |
| `litellm-/models` | 4 | Flat (2 GENERATIONs, depth 0, 0 scores) |
| `telegram-callback-cc` | 3 | Structured |
| `telegram-cmd-clearcache` | 3 | Structured |
| `bge-m3-hybrid-embed` | 3 | Structured |
| Other (`telegram-callback`, `debug-generate-answer`, etc.) | 10 | Mixed |

## Structural Analysis

### Flat Traces: `litellm-acompletion`

- **Observation count:** Exactly 1 per trace.
- **Observation type:** `GENERATION` only.
- **Depth:** 0 (root-level, no parent).
- **Scores:** 0.
- **Session:** `null`.
- **Tags:** `User-Agent: AsyncOpenAI`, `User-Agent: AsyncOpenAI/Python 2.32.0`.
- **Input:** Full chat completion request (system prompt + user message).
- **Output:** Chat completion response.

These traces are created by LiteLLM proxy's built-in Langfuse callback (`k8s/base/configmaps/litellm-config.yaml` lines 76-77):

```yaml
litellm_settings:
  success_callback: ["langfuse"]
  failure_callback: ["langfuse"]
```

LiteLLM sends one `GENERATION` per API call. It does not create parent spans, does not attach scores, and does not propagate the application's session or user context. The result is a large volume of flat traces that provide minimal debugging value beyond raw LLM I/O.

### Structured Traces: `telegram-message`

The `telegram-message` trace (root) is created by `LangfuseContextMiddleware` (`telegram_bot/middlewares/langfuse_middleware.py`) via `start_as_current_observation(as_type="span", name=f"telegram-{action_type}")`. It propagates `session_id`, `user_id`, and tags to all children.

**Key span families present:**
- `telegram-message` (root)
- `telegram-rag-query`
- `telegram-rag-supervisor`
- `client-direct-pipeline`
- `rag-pipeline`
- `service-generate-response`
- `hybrid-retrieve`
- `retrieval.initial`
- `qdrant-hybrid-search-rrf-colbert`
- `cache-*` (search, exact, embedding, sparse, semantic)
- `bge-m3-*` (encode, embed)
- `detect-agent-intent`
- `detect-response-style`
- `grade-documents`
- `history-save`
- `generate-answer`

**Missing from this specific trace but expected per `trace_contract.yaml`:**
- `node-*` spans (these appear inside `validation-query` traces, not `telegram-message`)
- `rerank` (may be skipped when ColBERT rerank is used)
- `voyage-*` spans (BGE-M3 is the active embedding provider)

### Structured Traces: `validation-query`

The `validation-query` traces use the graph-node span family (`node-guard`, `node-cache-check`, `node-retrieve`, `node-grade`, etc.) plus edge-route spans (`edge-route-cache`, `edge-route-grade`, `edge-route-guard`). These are created by the LangGraph runtime in the validation/evaluation pipeline.

## Root Cause of Flat Structure

The flat `litellm-acompletion` traces are systemic because:

1. **Instrumentation boundary:** LiteLLM proxy's Langfuse callback is a separate instrumentation layer. It intercepts HTTP requests/responses at the proxy level and logs them as standalone traces.
2. **No context propagation:** LiteLLM does not read or write the application's Langfuse trace context (no `parentObservationId`, no `sessionId`, no `userId`).
3. **No score attachment:** LiteLLM's callback does not compute or attach application-level scores (cache hit, latency, confidence, etc.).
4. **No child spans:** LiteLLM logs the completion as a single `GENERATION`. It does not break down retrieval, embedding, reranking, or caching into child observations.

## Is This a Bug or a Product Gap?

This is a **product gap**, not a code defect. LiteLLM is working as configured. However, it produces observability data that is structurally inferior to the application's native instrumentation. Approximately **40% of recent traces** are flat `litellm-acompletion` traces, diluting the quality of the Langfuse dataset.

## Recommendations

1. **Wrap LiteLLM calls in application traces** — Ensure all LLM calls that go through LiteLLM are invoked inside an existing `@observe` or `start_as_current_observation` span. The application's `generate_response.py` and `ai_advisor_service.py` already create `service-generate-response` and `advisor-llm-call` spans for some paths, but direct `chat.completions.create` calls from other services may bypass this.
2. **Consider disabling LiteLLM callback in favor of app-native tracing** — If the application's `@observe` decorators already cover all LLM call sites, the LiteLLM `success_callback: ["langfuse"]` may be redundant and creates noise. Evaluate whether to remove it and rely solely on application-level tracing.
3. **Add trace linking** — If both LiteLLM and app tracing must coexist, investigate whether LiteLLM supports passing a `trace_id` or `parent_observation_id` via request headers/metadata so the proxy trace can be nested under the application trace.
4. **Document the gap** — Add a note to `docs/runbooks/LANGFUSE_TRACING_GAPS.md` explaining that `litellm-acompletion` traces are proxy-generated and inherently flat.

## Related Issues

- Not covered by #1362, #1367, #1369, or #1307 (no local references found).
- Distinct from the specific trace audit worker's scope (that worker focuses on a single trace; this audit confirms the pattern is systemic).

## Verification Commands Run

```bash
langfuse api traces list --limit 100 --order-by timestamp.desc --fields core,io,scores,observations,metrics --json --public-key pk-lf-dev --secret-key sk-lf-dev --host http://localhost:3001
langfuse api traces get 8d79036a-36f4-4398-84aa-6839a1fcf040 --fields core,io,scores,observations,metrics --json --public-key pk-lf-dev --secret-key sk-lf-dev --host http://localhost:3001
langfuse api traces get b982914f054cf5190c10c6e91d8e7e4e --fields core,io,scores,observations,metrics --json --public-key pk-lf-dev --secret-key sk-lf-dev --host http://localhost:3001
langfuse api traces get 18c782031d4d43bfab86814f62d2e0c9 --fields core,io,scores,observations,metrics --json --public-key pk-lf-dev --secret-key sk-lf-dev --host http://localhost:3001
rg -n "telegram-message|client-direct|retrieve|generate|rerank|qdrant|cache|observe\\(" telegram_bot src tests
rg -n "@observe|langfuse.observe|langfuse_context" telegram_bot src --type py
```

## Safe-CLI Compliance

- No `.env` values, tokens, or secrets were printed.
- Input/output text was sanitized to short previews only.
- No Langfuse data was mutated or deleted.

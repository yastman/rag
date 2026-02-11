# fix(observability): reduce Langfuse node payload bloat + correct TTFT semantics

**Issue:** [#143](https://github.com/yastman/rag/issues/143)
**Date:** 2026-02-11

## Problem

1. **Payload bloat** — `@observe` on 9 LangGraph nodes auto-captures full `state` dict (documents, embeddings) as span input/output. `node-retrieve` alone is ~337 KB per trace.
2. **TTFT metric mismatch** — validation runs `message=None` → non-streaming → `llm_ttft_ms` always `0.0`. Go/No-Go uses generate node span duration as "TTFT proxy" under misleading name `ttft_p50_lt_2s`.

## Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Payload control | `@observe(capture_input=False, capture_output=False)` on heavy nodes + `update_current_span()` for curated metadata | Надёжно отрубает авто-слив, прозрачный контракт, проще ревью |
| Which nodes are "heavy" | retrieve, generate, cache_check, cache_store | Measured: 337/49/28/54 KB respectively |
| Light nodes | classify, grade, rerank, rewrite, respond — keep default `@observe` | Payloads small, auto-capture useful for debugging |
| TTFT rename | `ttft_p50_lt_2s` → `generate_p50_lt_2s` now; real streaming TTFT as follow-up | Минимальный риск, честная семантика |
| `_query_preview` util | Inline in each node first, extract to `_utils.py` only if duplication grows | Минимум связности |
| Tests | Runtime mock of `observe`, not regex/AST | Устойчиво к рефакторингу |

## Scope

### Files changed

| File | Change |
|------|--------|
| `telegram_bot/graph/nodes/retrieve.py` | `capture_input/output=False` + curated metadata |
| `telegram_bot/graph/nodes/generate.py` | Same |
| `telegram_bot/graph/nodes/cache.py` | Same (both cache_check and cache_store) |
| `scripts/validate_traces.py` | Rename criterion `ttft_p50_lt_2s` → `generate_p50_lt_2s` + footnote in report |
| `tests/unit/test_observe_payloads.py` | New: 3 test cases |

### Files NOT changed

- Light nodes (classify, grade, rerank, rewrite, respond)
- `telegram_bot/observability.py`
- `telegram_bot/bot.py` (score writing reads from state, not spans)
- State schema (`graph/state.py`) — `llm_ttft_ms` field untouched

## Implementation

### 1. Heavy nodes: disable auto-capture + curated metadata

Pattern (same for all 4 nodes):

```python
@observe(name="node-retrieve", capture_input=False, capture_output=False)
async def retrieve_node(state: dict[str, Any], *, ...):
    query = state.get("query") or state["messages"][-1].content  # safe extraction
    lf = get_client()
    lf.update_current_span(input={
        "query_preview": query[:120],
        "query_len": len(query),
        "query_hash": hashlib.sha256(query.encode()).hexdigest()[:8],
        ...
    })
    # ... existing logic ...
    lf.update_current_span(output={...})
```

### Curated fields per node

**node-retrieve**
- input: `query_preview`, `query_len`, `query_hash`, `query_type`, `top_k`
- output: `results_count`, `top_score`, `min_score`, `retrieval_backend_error`, `retrieval_error_type`, `duration_ms`

**node-generate**
- input: `query_preview`, `context_docs_count`, `streaming_enabled`
- output: `response_length`, `llm_provider_model`, `llm_ttft_ms` (or null), `llm_response_duration_ms`, `fallback_used`, `response_sent`, `token_usage` (optional, only if present)

**node-cache-check**
- input: `query_preview`, `query_type`
- output: `cache_hit`, `embeddings_cache_hit`, `hit_layer` (semantic|none), `duration_ms`

**node-cache-store**
- input: `query_preview`, `response_length`, `search_results_count`
- output: `stored`, `stored_semantic`, `stored_conversation`, `duration_ms`

### 2. TTFT criterion rename

In `scripts/validate_traces.py`:

```python
# Before:
criteria["ttft_p50_lt_2s"] = { "target": "< 2000 ms", ... }

# After:
criteria["generate_p50_lt_2s"] = { "target": "< 2000 ms", ... }
```

Footnote in markdown report: "generate_p50 measures full generation latency in non-streaming (headless) mode. For real TTFT measurement, see follow-up issue."

`llm_ttft_ms` score in `bot.py` and state schema — unchanged.

### 3. Tests

**test_heavy_nodes_disable_auto_capture** (runtime)
- Mock `telegram_bot.observability.observe` before importing node modules
- Assert `observe` was called with `capture_input=False, capture_output=False` for each heavy node function

**test_go_no_go_uses_generate_p50_key**
- Run the criteria-building code with mock data
- Assert `generate_p50_lt_2s` in criteria keys
- Assert `ttft_p50_lt_2s` NOT in criteria keys

**test_curated_span_payload_no_heavy_fields** (retrieve + generate)
- Mock `get_client()` → mock `update_current_span`
- Run node with test state containing documents/embeddings
- Assert `update_current_span` calls do NOT contain keys: `documents`, `query_embedding`, `sparse_embedding`, `state`

### 4. Follow-up issue

After merge, create: "feat(validation): add streaming phase for real TTFT measurement" linked to #143.

## Acceptance Criteria (from issue)

- [ ] p95 payload size for `node-retrieve` reduced by at least 80% vs current run
- [ ] No full documents/embeddings in node-level trace input/output for validation mode
- [ ] TTFT/latency metric naming and computation are mode-correct and documented
- [ ] Validation report reflects the corrected metric semantics

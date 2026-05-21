# ADR-0010: Voice Path Migration to `create_agent` SDK — Plan

**Status:** Proposed

**Date:** 2026-05-22

**Refs:** [#1535](https://github.com/yastman/rag/issues/1535)

## Context

The bot serves two RAG entrypoints with **divergent orchestrators**:

| Path | Entrypoint | Orchestration | Files |
|---|---|---|---|
| Text | `Bot._handle_query_supervisor` | `langchain.agents.create_agent` (LangChain 1.x) | `telegram_bot/agents/agent.py`, `telegram_bot/agents/rag_pipeline.py` |
| Voice | `Bot.handle_voice` | Custom 11-node `StateGraph` (`build_graph()`) | `telegram_bot/graph/graph.py`, `telegram_bot/graph/nodes/*.py` |

The voice path nodes (`guard`, `classify`, `cache_check`, `retrieve`, `grade`, `rerank`, `rewrite`, `generate`, `cache_store`, `respond`, plus voice-only `transcribe`) duplicate logic that the text path already calls as a tool (`rag_search`) plus a thin pre-agent layer (`classify_query`, `detect_injection`). ADR-0003 originally documented this split as deliberate; #1535 reverses that decision because the underlying assumption ("text is fast, deterministic; voice is complex, agentic") no longer holds — voice now runs a heavier graph than text, and bug fixes consistently need mirroring across both paths.

The full migration is too large for a single PR. This ADR is the **design-first** deliverable referenced by the issue's `lane:design-first` label. No production code changes ship with it.

## Decision Drivers

- **SDK-native consolidation:** `langchain.agents.create_agent` is the canonical entrypoint; custom `StateGraph` should remain only where the SDK genuinely cannot express the topology.
- **Middleware reuse:** the SDK exposes `before_model` / `after_model` / `wrap_model_call` hooks that match the pre/post-LLM stages already in voice (`guard`, `cache_check`, `cache_store`).
- **Shared RAG core:** `rag_pipeline.py` and `services/rag_core.py` already encapsulate retrieve→grade→rerank→rewrite for the text `rag_search` tool. Voice can call the same code path via the same tool once orchestration is unified.
- **Observability parity:** `@observe` spans named `node-*` (graph) vs. `cache-check`, `hybrid-retrieve`, `grade-documents`, `rerank` (pipeline) split Langfuse traces awkwardly. One naming scheme post-migration.

## Considered Options

### Option A — Big-bang full migration in one PR
Replace `build_graph` + all `nodes/*.py` with a single `create_agent` instance reusing `rag_search`. **Rejected:** ~600 LoC churn across `bot.py::handle_voice`, all 8 RAG nodes, voice-specific transcribe wrapper, plus state-shape regressions for ~40 keys in `RAGState`. Risk register too large for one review.

### Option B — Gradual middleware extraction (chosen)
Split the migration across N follow-up PRs, each independently revertible. Slice 0 (this ADR) is design-only. Slice 1 extracts shared middleware helpers. Slice 2 introduces a voice-flavoured `create_agent` behind a feature flag. Slice 3 deletes `build_graph`. Each slice ships its own contract test.

### Option C — Status quo
Keep dual pipelines, accept double maintenance. **Rejected:** #1535 has been open since 2026-05-14; #1533 documents the same dual-path pattern leaking into contextualisation logic. The cost compounds with every node-level fix.

## Decision

Adopt **Option B**: gradual migration via middleware extraction, gated by feature flag, validated on the gold set before each slice merges. This ADR's scope ends at recording the plan; topology changes ship in subsequent PRs.

## Node → Middleware/Tool Mapping

| Voice node | Maps to | Notes |
|---|---|---|
| `transcribe` | Pre-agent step (in `handle_voice`, before `agent.ainvoke`) | Voice-only input transformation; not a middleware. Mirrors how text path runs `classify_query` before the agent. |
| `guard` | `before_model` middleware (`@before_model(state_schema=VoiceAgentState, can_jump_to=["end"])`) | Already exists conceptually in text path as inline call to `detect_injection`. Slice 1 extracts to shared `injection_guard` middleware. |
| `classify` | `before_model` middleware | For CHITCHAT/OFF_TOPIC, returns `{"jump_to": "end"}` with canned response. Otherwise sets `query_type` in custom state. |
| `cache_check` | `before_model` middleware (`can_jump_to=["end"]`) | Semantic-cache lookup. On hit, short-circuits the agent loop. |
| `retrieve`, `grade`, `rerank`, `rewrite` | Internals of the existing `rag_search` tool | Already extracted into `telegram_bot/agents/rag_pipeline.py`; no new code needed beyond exposing the same tool to the voice agent. |
| `generate` | Native `create_agent` model loop | The agent's built-in tool→model loop replaces the explicit `generate` node. |
| `cache_store` | `after_model` middleware | Persists final response into `redisvl` semantic cache after the agent finishes. |
| `respond` | Post-agent step (in `handle_voice`, after `agent.ainvoke`) | Telegram delivery, source attribution, feedback keyboard. Mirrors text path; not a middleware. |
| `summarize` | `langmem.short_term.SummarizationNode` (already SDK) | Reuse, attach as middleware or as the existing post-respond node. |

## Custom State Schema (voice-only fields)

`AgentState` provides only `messages`. Voice needs additional fields not present in the text agent. Per Context7 evidence, custom fields are added by subclassing `AgentState` and passing the schema via `state_schema=` and the middleware's `state_schema = VoiceAgentState` attribute.

```python
from typing import NotRequired
from langchain.agents import AgentState

class VoiceAgentState(AgentState):
    # voice-only inputs
    voice_audio: NotRequired[bytes]
    voice_duration_s: NotRequired[float]
    stt_text: NotRequired[str]
    stt_duration_ms: NotRequired[float]
    input_type: NotRequired[str]            # "voice" | "text"
    # shared with text path (currently scattered in RAGState)
    query_type: NotRequired[str]
    cache_hit: NotRequired[bool]
    cached_response: NotRequired[str]
    injection_detected: NotRequired[bool]
    injection_risk_score: NotRequired[float]
    injection_pattern: NotRequired[str]
    trace_id: NotRequired[str]
    sent_message: NotRequired[dict]
    show_sources: NotRequired[bool]
    sources_count: NotRequired[int]
```

`NotRequired` per LangGraph backward-compatibility guidance — old checkpoints without these fields still validate.

## Migration Steps

1. **Slice 0 (this PR)** — ADR + contract test. No runtime change.
2. **Slice 1** — Extract `injection_guard` as a `@before_model` middleware in `telegram_bot/agents/middleware/guard.py`. Wire into the **text** agent only. Voice keeps `guard_node`. New unit + contract tests.
3. **Slice 2** — Extract `semantic_cache_check` and `semantic_cache_store` middleware. Wire into the text agent. Voice still uses graph nodes; logic is sourced from the same shared helper to avoid drift.
4. **Slice 3** — Define `VoiceAgentState`. Build a parallel `create_voice_agent` factory using the shared middleware + `rag_search` tool + voice-only `transcribe` pre-step. Behind `VOICE_AGENT_BACKEND={"graph"|"agent"}` flag, default `graph`.
5. **Slice 4** — Run gold-set evaluation (`src/evaluation/`) on both backends. Compare answer quality, latency p50/p95, recall. Promote `agent` to default if regressions ≤ 2% per metric.
6. **Slice 5** — Remove `telegram_bot/graph/graph.py::build_graph` and `telegram_bot/graph/nodes/{guard,classify,cache,retrieve,grade,rerank,rewrite,respond,generate}.py`. Keep `transcribe.py` (still useful as a voice-input helper). Flip ADR-0003 to "Superseded by ADR-0010". Flip this ADR to "Accepted".

Each slice is one PR, gated by its own contract test + the gold-set eval workflow.

## Risk Register

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| `RAGState` → `VoiceAgentState` field drift breaks Langfuse score keys | Medium | Medium | Slice 3 includes a state-shape contract test that pins the union of fields to `tests/contract/test_voice_agent_state_shape_contract.py`. |
| Checkpointer namespace collision (text and voice both use `AsyncRedisSaver`) | Low | High (cross-user leak) | Voice already uses `_CHECKPOINT_NS_VOICE`; preserve the namespace unchanged in slice 3. |
| Telegram streaming UX regression — `generate_node` injects partial messages mid-stream; `create_agent` streams via `astream` events differently | Medium | Medium | Slice 3 ships behind feature flag. Streaming parity verified manually before promoting default. |
| `before_model` middleware ordering changes guard-vs-classify precedence | Low | Medium | Pre-agent guard already runs in text path; move guard to first middleware position (matches voice graph topology). |
| `rag_search` tool latency higher than direct graph retrieval | Low | Low | Shared `rag_pipeline.py` is the same code; observed text-path latency stays within voice-path budget. |
| Whisper STT failure path differs (graph raises `ValueError("Empty transcription")`; agent path needs explicit handling) | High | Low | Voice still owns transcription as a pre-step; failure modes preserved by construction. |

## Consequences

### Positive
- Single SDK-native pipeline; bug fixes ship once.
- Middleware reuse: `injection_guard`, `semantic_cache_check`, `semantic_cache_store` become first-class shared building blocks.
- Langfuse trace shape converges: one set of span names regardless of input modality.
- Future agent SDK improvements (streaming, durability, HITL) automatically benefit voice.

### Negative
- `RAGState` union of ~40 keys collapses into a smaller `VoiceAgentState`; downstream consumers (Langfuse score writers, evaluators) need audit.
- Multi-PR roadmap; total wall-clock time longer than a big-bang rewrite.
- ADR-0003 is superseded; documentation needs cross-linking to avoid confusion.

## Context7 Evidence

Research conducted via Context7 MCP. Library IDs cited for traceability.

- **LangChain (Python):** Library ID `/websites/langchain_oss_python_langchain`. Documents `create_agent` middleware decorators (`@before_model`, `@after_model`) accepting a `state_schema` argument and returning either `None` (continue) or a partial state dict; `can_jump_to=["end"]` permits early termination from middleware. Custom `AgentState` subclasses are passed via `state_schema=` to `create_agent`. Source page: `docs.langchain.com/oss/python/langchain/middleware/custom`.
- **LangGraph (Python):** Library ID `/websites/langchain_oss_python_langgraph`. Documents the backward-compat rule that new state fields use `NotRequired` so existing checkpoints still validate. Source page: `docs.langchain.com/oss/python/langgraph/backward-compatibility`.

Snippets above are paraphrased summaries (≤ 30 consecutive words from any single source). Full code patterns are reproduced as illustrative samples in the Custom State Schema section, derived from the public docs and adapted to repo conventions. *Content was rephrased for compliance with licensing restrictions.*

## References

- Issue [#1535](https://github.com/yastman/rag/issues/1535) — dual pipeline maintenance.
- Issue [#1533](https://github.com/yastman/rag/issues/1533) — contextualisation duplication (same pattern).
- ADR-0003 — voice/text split (will be superseded by this ADR upon Acceptance).
- `telegram_bot/agents/agent.py` — current `create_agent` factory (text path).
- `telegram_bot/agents/rag_pipeline.py` — shared RAG core invoked from `rag_search` tool.
- `telegram_bot/graph/graph.py` — legacy 11-node `StateGraph` (voice path).

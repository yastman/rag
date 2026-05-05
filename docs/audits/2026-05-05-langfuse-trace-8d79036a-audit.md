# Langfuse Trace Audit — 8d79036a-36f4-4398-84aa-6839a1fcf040

**Date:** 2026-05-05
**Worker:** W-audit-trace-8d79036a-langfuse-cli
**Branch:** audit/trace-8d79036a
**Trace ID:** `8d79036a-36f4-4398-84aa-6839a1fcf040`
**User Query:** «виды внж в болгарии»

---

## 1. CLI Commands Run

```bash
langfuse --env .env.example api traces get 8d79036a-36f4-4398-84aa-6839a1fcf040 \
  --fields core,io,scores,observations,metrics --json

langfuse --env .env.example api observations list \
  --trace-id 8d79036a-36f4-4398-84aa-6839a1fcf040 \
  --fields core,basic,time,io,metadata,model,usage,prompt,metrics --limit 1000 --json

langfuse --env .env.example api scores list \
  --trace-id 8d79036a-36f4-4398-84aa-6839a1fcf040 --json
```

**Authentication:** used `.env.example` dev defaults (`pk-lf-dev` / `sk-lf-dev`) against the local Langfuse instance. No secrets printed.

**Observation list result:** v2 API returned `404 LangfuseNotFoundError` (v2 beta only on Cloud). Observations were extracted from the `traces get` embedded payload.

**Scores result:** `200 OK`, body `{"data":[]}` — no scores attached.

---

## 2. Sanitized Trace Summary

| Field | Value |
|-------|-------|
| `id` | `8d79036a-36f4-4398-84aa-6839a1fcf040` |
| `name` | `litellm-acompletion` |
| `timestamp` | `2026-05-05T16:42:47.290Z` |
| `environment` | `default` |
| `tags` | `User-Agent: AsyncOpenAI`, `User-Agent: AsyncOpenAI/Python 2.32.0` |
| `userId` | `null` |
| `sessionId` | `null` |
| `input` | System prompt + RAG context (`[Объект 1] … Виды ВНЖ …`) + user message «Виды внж в Болгарии?» |
| `output` | Assistant answer about ВНЖ types (2 blocks, ~150 tokens) |
| `latency` | `1.046` s |
| `totalCost` | `$0.0029725` |
| `observations` | **1** |
| `scores` | **0** |

The input clearly shows a **full RAG context block** was assembled before the LLM call (retrieved document with relevance score 7.22), proving the upstream retrieve/grade/rerank pipeline executed. None of those stages appear in the trace.

---

## 3. Observation Tree

```
8d79036a-36f4-4398-84aa-6839a1fcf040 (TRACE)
└── time-16-42-46-196837_chatcmpl-f362fcff-aa13-4bba-9ba5-01525f6d54ad (GENERATION)
    name:        litellm-acompletion
    type:        GENERATION
    parentId:    null
    startTime:   2026-05-05T16:42:46.196Z
    endTime:     2026-05-05T16:42:47.242Z
    model:       cerebras/zai-glm-4.7
    usage:       input=1227, output=77, total=1304
    metadata:    LiteLLM proxy fields (model_group=gpt-4o-mini, deployment=cerebras/zai-glm-4.7,
                 litellm_api_version=1.81.14, user_api_key_hash, request_route=/v1/chat/completions,
                 cache_hit=false, etc.)
```

**Shape diagnosis:**
- **Root-only / flat:** the single observation has `parentObservationId: null` and is directly attached to the trace root.
- **No spans:** zero `SPAN` observations.
- **No generations other than LiteLLM's:** the application-level `generate-answer` generation is absent.
- **No scores:** zero `SCORE` objects.
- **No user/session attribution:** `userId` and `sessionId` are null, preventing per-user cost attribution.

---

## 4. Expected vs Actual

### 4.1 What the repo promises (post-recent-merge)

Per `telegram_bot/middlewares/langfuse_middleware.py:65-75`, every Telegram update should open a root span:

```python
lf.start_as_current_observation(
    as_type="span",
    name=f"telegram-{action_type}",
    ...
)
```

Per the graph nodes and pipeline, the following observations **should** be nested under that root for a RAG query:

| Expected Observation | Type | Source File | Line | Condition for this query |
|----------------------|------|-------------|------|--------------------------|
| `telegram-message` | SPAN | `middlewares/langfuse_middleware.py` | 65 | Always (Telegram text) |
| `client-direct-pipeline` | SPAN | `pipelines/client.py` | 186 | Always (client path) |
| `classify-query` | SPAN | `graph/nodes/classify.py` | 248 | Always |
| `node-classify` | SPAN | `graph/nodes/classify.py` | 275 | LangGraph node |
| `node-guard` | SPAN | `graph/nodes/guard.py` | 143 | If content_filter_enabled |
| `node-cache-check` | SPAN | `graph/nodes/cache.py` | 47 | Always |
| `node-retrieve` | SPAN | `graph/nodes/retrieve.py` | 59 | Always (RAG-eligible) |
| `node-grade` | SPAN | `graph/nodes/grade.py` | 19 | Always |
| `node-rerank` | SPAN | `graph/nodes/rerank.py` | 26 | If reranker configured |
| `node-generate` | SPAN | `graph/nodes/generate.py` | 333 | If cache miss |
| `generate-answer` | GENERATION | `services/generate_response.py` | 352 | LLM call |
| `node-respond` | SPAN | `graph/nodes/respond.py` | 51 | Always |
| `voyage-embed-query` | GENERATION | `services/voyage.py` | 147 | Embedding call |
| `voyage-rerank` | GENERATION | `services/voyage.py` | 200 | Rerank call |
| `qdrant-search` updates | SPAN metadata | `services/qdrant.py` | 116+ | Search calls |
| Scores (query_type, latency, cache, results, generation, …) | SCORE | `scoring.py` | 46+ | Post-pipeline |

### 4.2 What actually appeared

| Actual Observation | Type | Count |
|--------------------|------|-------|
| `litellm-acompletion` | GENERATION | 1 |

**Missing count:** 15+ expected observations (spans/generations/scores) are absent from this trace.

---

## 5. Suspected Root Cause

This trace is **created by the LiteLLM proxy**, not by the bot's application-level Langfuse client.

Evidence:
1. **Trace name** is `litellm-acompletion` — LiteLLM's hard-coded callback name.
2. **Metadata** contains LiteLLM-specific fields: `litellm_api_version`, `model_group`, `deployment`, `user_api_key_hash`, `request_route=/v1/chat/completions`.
3. **Tags** are `User-Agent: AsyncOpenAI` — LiteLLM proxy auto-tags, not the bot middleware tags (`telegram`, `message`).
4. **`userId` / `sessionId` null** — LiteLLM has no access to Telegram user/session context.
5. **No `parentObservationId`** — LiteLLM callback always creates a root-level generation; it does not inherit the bot's active observation context.

The bot uses `langfuse.openai.AsyncOpenAI` (`telegram_bot/graph/config.py:150`) pointing at the LiteLLM proxy (`http://litellm:4000`). When `chat.completions.create()` is called, two things happen in parallel:
- The **bot's Langfuse-wrapped client** tries to create a `generate-answer` generation under the active bot trace.
- The **LiteLLM proxy** receives the HTTP request and, via its own `success_callback: ["langfuse"]` (`docker/litellm/config.yaml:79`), creates a **separate** trace (`litellm-acompletion`) with its own generation.

Because the proxy-side trace has no access to the bot's trace context, it is **orphaned and flat**. The user sees this proxy trace in the UI because it is the only one named after the LLM call.

Issue **#1362** already tracks the orphaned-trace problem exactly: `langfuse.openai.AsyncOpenAI` creates a separate root trace instead of nesting under `telegram-message`.

---

## 6. Files / Functions to Inspect / Fix

| File | Lines | What to check |
|------|-------|---------------|
| `docker/litellm/config.yaml` | 78–86 | `success_callback: ["langfuse"]` — decide whether LiteLLM should log to Langfuse at all, or whether the bot should be the sole trace owner. |
| `telegram_bot/graph/config.py` | 148–157 | `create_llm()` returns `langfuse.openai.AsyncOpenAI`. Verify that `name="generate-answer"` is actually accepted and that the generation nests under the current trace. |
| `telegram_bot/services/generate_response.py` | 300–318 | `_chat_create_with_optional_name()` — if the client rejects `name`, the generation loses its custom name and may fall back to `litellm-acompletion`. |
| `telegram_bot/middlewares/langfuse_middleware.py` | 40–76 | Confirm `start_as_current_observation` successfully creates the root `telegram-message` trace and that `propagate_attributes` carries context through async boundaries. |
| `telegram_bot/observability.py` | 477–494 | `traced_pipeline()` / `propagate_attributes()` — verify trace context survives across `await` boundaries into graph nodes. |
| `telegram_bot/graph/nodes/generate.py` | 333 | `node-generate` `@observe` — ensure it wraps the LLM call so that `generate-answer` is a child of `node-generate`. |
| `telegram_bot/scoring.py` | 46–90 | `write_langfuse_scores()` — scores are written to the bot trace; they will never appear on the LiteLLM trace. |

---

## 7. Issues Linked / Created

### Existing issues (linked, not duplicated)

- **#1362** — `observability: langfuse.openai AsyncOpenAI creates orphaned traces — LLM cost lost`
  Covers the root cause: LiteLLM proxy and bot create separate traces. The `litellm-acompletion` trace is the orphan described in #1362.

- **#1367** — `observability: blind spots — 7 modules with zero Langfuse coverage`
  Covers missing instrumentation in retrieval/reranker/embedding services. While the graph nodes (`node-retrieve`, `node-rerank`) are decorated, the underlying `services/voyage.py`, `src/retrieval/reranker.py`, and `services/qdrant.py` spans may not always surface if the root trace is missing or if propagation fails.

- **#1307** — `observability: bring up local Langfuse and verify bot trace coverage`
  Covers the broader verification effort. This audit provides concrete evidence that trace coverage is broken for the text-RAG path.

### No new issue created

All observed gaps (orphaned flat trace, missing stage separation, absent scores) are already represented by #1362, #1367, and #1307. Creating a duplicate would fragment tracking.

---

## 8. Recommendations

1. **Prioritize #1362.** The orphaned trace is the most user-visible symptom. Options:
   - Disable LiteLLM's Langfuse callback (`success_callback: []`) and let the bot own 100 % of tracing.
   - Or propagate the bot's `trace_id` into LiteLLM request metadata so LiteLLM nests its generation under the bot trace.
2. **Verify bot trace creation.** In the recent 100 traces (2026-05-05 17:02 window) no `telegram-message` or `client-direct-pipeline` traces were found. Confirm whether the bot trace is being created but flushed asynchronously, or whether `get_client()` returns `None` in the runtime that served this request.
3. **Validate scores pipeline.** Once the root trace is restored, confirm `write_langfuse_scores()` executes post-pipeline and attaches the expected 15+ score dimensions.
4. **Re-audit after fix.** Re-run this CLI ladder against a fresh request once #1362 is resolved to confirm the observation tree contains all expected spans.

---

*End of audit report.*

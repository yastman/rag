# RAG Latency Phase 2: Streaming, Token Cap, Early Termination, Parallel Re-embed

**Date:** 2026-02-10
**Status:** Revised (v2)

## Goal
Reduce end-user perceived latency and p90 E2E latency for the Telegram RAG path with low-risk changes.

## Why this revision
The previous draft had a few mismatches with current code:
- `max_rewrite_attempts` exists in config but routing still uses hardcoded `< 2`.
- Early-termination logic in `edges.py` should not read env directly.
- Streaming support exists in `telegram_bot/services/llm.py` but is not used by the LangGraph path.

This revision prioritizes production impact and keeps changes testable.

---

## Baseline (current implementation)
- Graph path: `classify -> cache_check -> retrieve -> grade -> rerank/rewrite/generate`.
- `route_grade` currently always sends relevant docs to `rerank`.
- `generate_node` is non-streaming and uses `config.llm_max_tokens`.
- Dense embedding is usually computed in `cache_check`; re-embed path occurs after rewrite (`query_embedding=None`).

---

## Scope (Phase 2)
1. Add configurable `generate_max_tokens` cap for answer generation.
2. Add early termination: skip rerank when confidence is high.
3. Parallelize dense+sparse only in rewrite re-embed path.
4. Integrate streaming delivery in Telegram path.
5. Use `max_rewrite_attempts` from config (remove hardcoded routing limit).

Out of scope:
- KV-cache precompute / model-weight optimizations.
- Retrieval-generation overlap (PipeRAG-style server-side parallel decoding).

---

## Task 1: Generate Token Cap (`generate_max_tokens`)

### Files
- Modify: `telegram_bot/graph/config.py`
- Modify: `telegram_bot/graph/nodes/generate.py`
- Modify: `docker-compose.dev.yml`
- Test: `tests/unit/graph/test_config.py`
- Test: `tests/unit/graph/test_generate_node.py`

### Changes
- Add `generate_max_tokens: int = 2048` in `GraphConfig`.
- Load from env: `GENERATE_MAX_TOKENS` (default `2048`).
- In `generate_node`, switch `max_tokens=config.llm_max_tokens` to `max_tokens=config.generate_max_tokens`.

### Acceptance
- Unit tests verify default and env override.
- Unit test verifies LLM call receives `generate_max_tokens`.

---

## Task 2: Early Termination (Skip Rerank on High Confidence)

### Files
- Modify: `telegram_bot/graph/config.py`
- Modify: `telegram_bot/graph/state.py`
- Modify: `telegram_bot/graph/nodes/grade.py`
- Modify: `telegram_bot/graph/edges.py`
- Test: `tests/unit/graph/test_edges.py`
- Test: `tests/unit/graph/test_state.py`
- Test: `tests/unit/graph/test_agentic_nodes.py`

### Changes
- Add config: `skip_rerank_threshold: float = 0.85` (+ env `SKIP_RERANK_THRESHOLD`).
- Add state fields:
  - `grade_confidence: float`
  - `skip_rerank: bool`
- In `grade_node`:
  - set `grade_confidence = top_score`
  - set `skip_rerank = documents_relevant and top_score >= skip_rerank_threshold`
- In `route_grade`:
  - if `skip_rerank` -> `generate`
  - else if relevant -> `rerank`
  - else rewrite/generate as before

### Acceptance
- New test: relevant + high confidence routes to `generate`.
- Existing relevant test still routes to `rerank` when confidence below threshold.

---

## Task 3: Parallel Dense+Sparse in Rewrite Re-embed Path

### Files
- Modify: `telegram_bot/graph/nodes/retrieve.py`
- Test: `tests/unit/graph/test_retrieve_node.py`

### Implementation constraints
- Parallelization is only for branch where:
  - `state["query_embedding"] is None`
  - and dense embedding cache miss
- Use `asyncio.gather()` to compute dense and sparse concurrently.
- Keep existing behavior for non-rewrite path.

### Changes
- Initialize `sparse_vector = None` at function start.
- On rewrite re-embed cache miss, gather:
  - dense embed + store
  - sparse fetch-or-compute + store
- Keep search cache check right after dense is ready.

### Acceptance
- Unit test validates both embed calls happen in same branch.
- Existing retrieve tests remain green.

---

## Task 4: Streaming in Telegram Graph Path (highest user impact)

### Files
- Modify: `telegram_bot/bot.py`
- Modify: `telegram_bot/graph/nodes/generate.py` (or add dedicated stream node)
- Optional: `telegram_bot/graph/state.py` (for partial text fields)
- Test: `tests/unit/test_bot_handlers.py` (or bot-level unit tests)
- Test: `tests/unit/graph/test_generate_node.py` (if stream-aware)

### Design (recommended)
- Keep retrieval/grading/routing unchanged.
- Stream only generation output to Telegram as partial updates.
- Use one of:
  - `graph.astream(..., stream_mode="messages")`, or
  - OpenAI `.chat.completions.stream(...)` within generate flow.
- Telegram delivery pattern:
  - send initial placeholder message,
  - edit message in chunks (throttled, e.g. every 150-250ms),
  - finalize once complete.

### Safety/UX constraints
- If streaming fails, fall back to current non-streaming send.
- Preserve Langfuse and latency metrics on completion path.

### Acceptance
- User sees first tokens before full completion.
- No regression in final message content and cache-store behavior.

---

## Task 5: Use Configured Rewrite Cap (`max_rewrite_attempts`)

### Files
- Modify: `telegram_bot/graph/edges.py`
- Optional: `telegram_bot/graph/state.py` (if cap passed via state)
- Test: `tests/unit/graph/test_edges.py`
- Test: `tests/unit/graph/test_config.py`

### Changes
- Remove hardcoded `rewrite_count < 2` from routing.
- Read cap from state (preferred), where state is initialized from `GraphConfig.max_rewrite_attempts`.
- Keep `rewrite_effective` guard.

### Acceptance
- Changing `MAX_REWRITE_ATTEMPTS` changes routing behavior without code edits.

---

## Suggested execution order
1. Task 1 (`generate_max_tokens`) - low risk, quick win.
2. Task 2 (early termination) - direct p90 gain.
3. Task 5 (config-driven rewrite cap) - correctness/config hygiene.
4. Task 3 (parallel re-embed) - moderate gain on rewrite branch.
5. Task 4 (streaming) - highest UX gain, integrate carefully.

---

## Verification
Run after each task and at the end:

```bash
uv run pytest tests/unit/graph/ -v --timeout=30
uv run pytest tests/unit/test_bot_handlers.py -v || true
uv run ruff check telegram_bot/ --fix
uv run ruff format telegram_bot/
uv run mypy telegram_bot/ --ignore-missing-imports
```

If any test group is flaky in current branch, document known failures and attach task-specific test evidence.

---

## Rollback plan
- Each task is independently revertible by file scope.
- If streaming rollout causes Telegram regressions, disable via feature flag and keep other latency improvements.

---

## Expected impact (pragmatic)
- `generate_max_tokens` cap: lower tail latency on long answers.
- Early termination skip-rerank: saves rerank latency for high-confidence queries.
- Parallel re-embed: saves latency only on rewrite branch.
- Streaming: strongest perceived-latency improvement for users.

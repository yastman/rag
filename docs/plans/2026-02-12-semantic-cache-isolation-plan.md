# Semantic Cache Isolation — SDK-First Implementation Plan

**Date:** 2026-02-12
**Issues:** #163 (primary), #157 (live validation), #152 (future memory stack)

## 1. Problem Statement

We need strict separation between:

- **Conversation memory** (LangGraph checkpointer, thread context)
- **Semantic cache** (document-answer acceleration)

Current risk:

1. Semantic cache may return contextual/personal answers (e.g. "Как меня зовут?")
2. Cache hit path bypasses generation/history path
3. Legacy Redis LIST conversation path adds confusion (write-only in runtime flow)

## 2. Target Behavior

1. Semantic cache is used only for document-oriented intents:
   - `FAQ`
   - `ENTITY`
   - `STRUCTURED`
2. `GENERAL` and other context-sensitive intents do not read/write semantic cache.
3. Semantic cache entries are isolated at least by `user_id` (and optionally `checkpoint_ns`).
4. Conversation memory remains checkpointer-owned (`thread_id`, `checkpoint_ns`).

## 3. SDK Decisions (Context7-based)

### RedisVL SemanticCache

Use SDK-native filtering:

- add `user_id` to `filterable_fields`
- store with `filters={"user_id": ..., "query_type": ..., "language": ...}`
- check with combined `Tag` filter (`user_id` + `language` + optional `query_type`)

### LangGraph Redis Checkpointer

Keep memory flow on checkpointer:

- invoke with `configurable.thread_id` + `configurable.checkpoint_ns`
- clear with SDK delete API (`adelete_thread` / project wrapper)

No custom memory store should compete with this flow.

## 4. Implementation Plan

### Task A: Add semantic cache allowlist guard

**Files:**
- `telegram_bot/graph/nodes/cache.py`
- `tests/unit/graph/test_cache_nodes.py`

Changes:

- introduce single allowlist constant: `{"FAQ", "ENTITY", "STRUCTURED"}`
- in `cache_check_node`: skip `check_semantic` for non-allowlisted types
- in `cache_store_node`: skip `store_semantic` for non-allowlisted types

Tests:

- add failing test: `GENERAL` does not call `check_semantic`
- add failing test: `GENERAL` does not call `store_semantic`
- keep positive test for allowlisted type (`FAQ`) to avoid regression

### Task B: Add per-user isolation to semantic cache (SDK filters)

**Files:**
- `telegram_bot/integrations/cache.py`
- `telegram_bot/graph/nodes/cache.py`
- `tests/unit/integrations/test_cache_layers.py`
- `tests/unit/graph/test_cache_nodes.py`

Changes:

- `SemanticCache(filterable_fields=...)` add `user_id` tag
- extend cache methods to accept `user_id`:
  - `check_semantic(..., user_id: int, ...)`
  - `store_semantic(..., user_id: int, ...)`
- store filters with `user_id`
- build combined Tag filter on check (`user_id` + `language`, optionally `query_type`)
- pass `state["user_id"]` from graph nodes into cache calls

Tests:

- unit test: same prompt from different `user_id` does not cross-hit
- unit test: same `user_id` can hit

### Task C: Integration path validation

**Files:**
- `tests/integration/test_graph_paths.py`

Tests:

- `GENERAL` query bypasses semantic cache even when mock cache has a candidate hit
- allowlisted query still uses semantic cache as expected

### Task D: Legacy Redis LIST cleanup in runtime path

**Files:**
- `telegram_bot/graph/nodes/cache.py`
- `tests/unit/graph/test_cache_nodes.py`

Changes:

- remove `store_conversation_batch(...)` call from active graph path
- keep memory source single: checkpointer

Note:

- full deletion of LIST methods from `CacheLayerManager` can be separate cleanup PR if we want lower-risk rollout

## 5. Verification Commands

```bash
uv run pytest tests/unit/graph/test_cache_nodes.py -v
uv run pytest tests/unit/integrations/test_cache_layers.py -v
uv run pytest tests/integration/test_graph_paths.py -v
make check
```

If running wider validation:

```bash
uv run pytest tests/unit/ -v --timeout=30
```

## 6. Acceptance Criteria

- `GENERAL` never reads semantic cache
- `GENERAL` never writes semantic cache
- semantic cache hit is isolated by `user_id`
- allowlisted types (`FAQ/ENTITY/STRUCTURED`) still benefit from cache
- active graph path no longer writes legacy Redis LIST conversation entries
- no regressions in listed unit/integration tests

## 7. Rollout / Risk

- Roll out in two commits:
  1. allowlist + tests
  2. per-user filter isolation + tests
- If needed, rollback by reverting commit 2 only (keep allowlist safety)

## 8. Context7 SDK References

- RedisVL SemanticCache filters and `Tag` usage:
  https://github.com/redis/redis-vl-python/blob/main/docs/user_guide/03_llmcache.ipynb
- LangGraph Redis AsyncRedisSaver usage (`thread_id`, `checkpoint_ns`, `adelete_thread`):
  https://github.com/redis-developer/langgraph-redis/blob/main/README.md

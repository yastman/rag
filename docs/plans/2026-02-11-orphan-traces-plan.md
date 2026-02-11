# Orphan Traces Cleanup + propagate_attributes — Implementation Plan

**Goal:** Reduce orphan trace rate from 82% (41/50) to <10% by wrapping all entry points in `propagate_attributes` and adding missing `@observe` span.

**Issue:** https://github.com/yastman/rag/issues/123

**Milestone:** Stream-C: Observability

---

## Current State

| Entry Point | File:Line | Has @observe root? | Has propagate_attributes? | Orphan? |
|-------------|-----------|---------------------|---------------------------|---------|
| Telegram bot | `bot.py:229` | YES (`telegram-rag-query`) | YES (line 246) | NO |
| validate_traces | `scripts/validate_traces.py:238` | YES (`validation-query`) | YES (line 232) | NO |
| Smoke test: classify_to_respond | `tests/smoke/test_langgraph_smoke.py:126` | NO | NO | YES |
| Integration: 6 test methods | `tests/integration/test_graph_paths.py:177,228,273,350,399,449` | NO | NO | YES x6 |
| store_conversation_batch | `telegram_bot/integrations/cache.py:390` | NO @observe | N/A | Missing span |

## Root Cause Analysis

Langfuse SDK v3 uses Python `contextvars` for trace nesting. When `@observe`-decorated functions (all 9 graph nodes, 8 cache methods, embeddings, qdrant, reranker = 35 spans total) run inside a parent `@observe` context, they create child observations. When called WITHOUT parent context, each creates a **separate root trace** with `session=None, userId=None`.

### Why 82% orphan?

1. **Smoke tests** call `graph.ainvoke()` at `test_langgraph_smoke.py:126` without any `propagate_attributes` — every `@observe` node creates a separate trace
2. **Integration tests** call `graph.ainvoke()` at 6 locations in `test_graph_paths.py` without `propagate_attributes` — same problem
3. **Historical traces** from `validate_traces.py` before `propagate_attributes` was added (already fixed)
4. **`store_conversation_batch`** at `cache.py:390` lacks `@observe` — invisible span, not an orphan but a gap
5. **Tests with `.env` loaded** — if `LANGFUSE_SECRET_KEY` is set in `.env`, `@observe` is REAL (not no-op) during tests, producing real orphan traces in Langfuse

### Trace count per orphan source

| Source | @observe calls per run | Orphan traces created |
|--------|------------------------|-----------------------|
| Smoke test (1 ainvoke) | ~9 nodes + cache + services | ~15-20 |
| Integration tests (6 ainvokes) | ~9 nodes x 6 | ~30-54 |
| Historical validation runs | unknown | ~10+ |

---

## Step 1: Add @observe to store_conversation_batch

**File:** `telegram_bot/integrations/cache.py:390`
**Time:** 2 min

Add `@observe` decorator to `store_conversation_batch` method. Currently line 390:

    async def store_conversation_batch(self, user_id: int, messages: list[tuple[str, str]]) -> None:

Change to:

    @observe(name="cache-conversation-batch-store")
    async def store_conversation_batch(self, user_id: int, messages: list[tuple[str, str]]) -> None:

Import `observe` is already present in `cache.py` (verify with grep).

**Verify:** `uv run pytest tests/unit/integrations/test_cache_layers.py -v` — all pass (no-op when LANGFUSE disabled)

---

## Step 2: Add traced_pipeline helper to observability.py

**File:** `telegram_bot/observability.py` (after line 137)
**Time:** 5 min

### 2a. Write failing test

Create `tests/unit/test_observability.py` (or add to existing) with:

    from telegram_bot.observability import traced_pipeline

    def test_traced_pipeline_is_context_manager():
        with traced_pipeline(session_id="test-123", user_id="user-1"):
            pass  # should not raise

    def test_traced_pipeline_accepts_tags():
        with traced_pipeline(session_id="s", user_id="u", tags=["a", "b"]):
            pass

Run: `uv run pytest tests/unit/test_observability.py::test_traced_pipeline_is_context_manager -v`
Expected: FAIL (ImportError: cannot import name 'traced_pipeline')

### 2b. Implement traced_pipeline

В `telegram_bot/observability.py`, после строки 137 (конец if/else блока), добавить:

    def traced_pipeline(
        *,
        session_id: str,
        user_id: str,
        tags: list[str] | None = None,
    ):
        """Context manager for pipeline-level trace propagation.

        Wraps propagate_attributes with sensible defaults.
        Use at any entry point that invokes @observe-decorated functions.
        """
        return propagate_attributes(
            session_id=session_id,
            user_id=user_id,
            tags=tags or [],
        )

Эта функция работает и с реальным Langfuse (propagate_attributes от SDK), и с disabled (no-op contextmanager).

Run: `uv run pytest tests/unit/test_observability.py -v` — all pass

---

## Step 3: Wrap smoke test in traced_pipeline

**File:** `tests/smoke/test_langgraph_smoke.py:126`
**Time:** 3 min

Добавить import в начало файла:

    from telegram_bot.observability import traced_pipeline

Обернуть `graph.ainvoke` в `test_full_graph_classify_to_respond` (строка ~122-131):

    # Before (line 122-126):
    with patch(
        "telegram_bot.graph.nodes.generate._get_config",
        return_value=mock_gc,
    ):
        result = await graph.ainvoke(state)

    # After:
    with traced_pipeline(session_id="smoke-test-20260209", user_id="smoke"):
        with patch(
            "telegram_bot.graph.nodes.generate._get_config",
            return_value=mock_gc,
        ):
            result = await graph.ainvoke(state)

Run: `uv run pytest tests/smoke/test_langgraph_smoke.py -v` — all pass

---

## Step 4: Wrap integration tests in traced_pipeline

**File:** `tests/integration/test_graph_paths.py` — 6 call sites at lines 177, 228, 273, 350, 399, 449
**Time:** 5 min

Добавить import:

    from telegram_bot.observability import traced_pipeline

Для КАЖДОГО из 6 тестов, обернуть `graph.ainvoke`:

    # Line 177 (test_path_chitchat_early_exit):
    with traced_pipeline(session_id="test-chitchat", user_id="integration"):
        result = await graph.ainvoke(state)

    # Line 228 (test_path_cache_hit):
    with traced_pipeline(session_id="test-cache-hit", user_id="integration"):
        result = await graph.ainvoke(state)

    # Line 273 (test_path_happy_retrieve_rerank_generate):
    with traced_pipeline(session_id="test-happy-path", user_id="integration"):
        result = await graph.ainvoke(state)

    # Line 350 (test_path_rewrite_loop_then_success):
    with traced_pipeline(session_id="test-rewrite-loop", user_id="integration"):
        result = await graph.ainvoke(state)

    # Line 399 (test_path_rewrite_exhausted_fallback):
    with traced_pipeline(session_id="test-rewrite-exhausted", user_id="integration"):
        result = await graph.ainvoke(state)

    # Line 449 (test_path_rewrite_ineffective_fallback):
    with traced_pipeline(session_id="test-rewrite-ineffective", user_id="integration"):
        result = await graph.ainvoke(state)

Run: `uv run pytest tests/integration/test_graph_paths.py -v` — all 6 pass

---

## Step 5: Update observability docs

**File:** `.claude/rules/observability.md`
**Time:** 3 min

Добавить секцию "Entry Point Pattern" после "### Root Trace" table:

    ### Entry Point Pattern (Orphan Prevention)

    All entry points that invoke @observe-decorated code MUST use traced_pipeline or propagate_attributes.
    Without this, each @observe call creates a separate root trace (session=None, userId=None).

    Rule: traced_pipeline → @observe(root) → nested @observe(children)

    | Entry Point | File | session_id format |
    |-------------|------|-------------------|
    | Telegram bot | bot.py:handle_query | chat-{hash}-{YYYYMMDD} |
    | Validation | scripts/validate_traces.py | validate-{run_id[:8]} |
    | Smoke tests | tests/smoke/test_langgraph_smoke.py | smoke-test-{YYYYMMDD} |
    | Integration | tests/integration/test_graph_paths.py | test-{path-name} |

    Usage:
        from telegram_bot.observability import traced_pipeline
        with traced_pipeline(session_id="...", user_id="..."):
            result = await graph.ainvoke(state)

Добавить `store_conversation_batch` в таблицу "Cache (8 methods)" → сделать "Cache (9 methods)":

    | store_conversation_batch | cache-conversation-batch-store |

---

## Step 6: Verify orphan rate < 10%

**Time:** 5 min

1. Run: `make validate-traces-fast`
2. В Langfuse UI (http://localhost:3001):
   - Traces → filter by recent `validate-*` session
   - Verify: все node spans вложены в root trace `validation-query`
   - Verify: session_id и userId заполнены
   - Count orphans: traces без parent с session=None
3. Если orphan rate < 10% → close issue #123

---

## Test Strategy

| Check | Command | Expected |
|-------|---------|----------|
| Unit tests pass | `uv run pytest tests/unit/ -n auto` | All green |
| Smoke tests pass | `uv run pytest tests/smoke/test_langgraph_smoke.py -v` | All green |
| Integration tests pass | `uv run pytest tests/integration/test_graph_paths.py -v` | All green |
| Orphan traces reduced | Langfuse UI check after validate-traces-fast | <10% orphan |
| Lint clean | `make check` | No errors |

## Acceptance Criteria

- [ ] `store_conversation_batch` has `@observe(name="cache-conversation-batch-store")`
- [ ] `traced_pipeline` helper exists in `observability.py`
- [ ] Smoke tests wrapped in `traced_pipeline`
- [ ] Integration tests (6) wrapped in `traced_pipeline`
- [ ] Orphan trace rate < 10%
- [ ] session_id and userId present on all new traces
- [ ] All existing tests pass

## Effort Estimate

**Size:** S (Small)
**Time:** ~25 min total (5 tasks + verification)
**Risk:** Low — no behavioral changes, only observability metadata propagation

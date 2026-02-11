# Orphan Traces Cleanup — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Reduce orphan trace rate from 82% to < 10% by ensuring all `@observe`-decorated entry points propagate session/user context, and add missing `@observe` span to `store_conversation_batch`.

**Architecture:** Langfuse SDK v3 uses Python `contextvars` for trace nesting. When `@observe` is called inside another `@observe` context, it creates a child observation. `propagate_attributes()` sets session_id, user_id, tags on the current trace context. Orphans happen when `@observe`-decorated functions run **outside** any parent context — each creates a separate root trace with `session=None, userId=None`.

**Tech Stack:** Langfuse Python SDK v3, `@observe` decorator, `propagate_attributes()` context manager.

**Issue:** [#123](https://github.com/yastman/rag/issues/123) — fix(observability): clean up orphan traces + add propagate_attributes to smoke tests

---

## Root Cause Analysis

### Current Trace Flow (Production — CORRECT)

```
bot.py:handle_query  @observe("telegram-rag-query")   ← ROOT TRACE
  └─ propagate_attributes(session_id, user_id, tags)   ← session/user set
      └─ graph.ainvoke(state)
          ├─ classify_node     @observe("node-classify")      ← CHILD ✓
          ├─ cache_check_node  @observe("node-cache-check")   ← CHILD ✓
          ├─ retrieve_node     @observe("node-retrieve")      ← CHILD ✓
          └─ ...9 nodes total                                  ← CHILD ✓
```

### Orphan Sources

| Source | File | Problem | Traces/run |
|--------|------|---------|------------|
| ~~validate_traces.py~~ | `scripts/validate_traces.py` | **Already fixed** — has `propagate_attributes` | 0 |
| `bot.py` | `telegram_bot/bot.py` | **Already correct** | 0 |
| Missing span | `telegram_bot/integrations/cache.py:390` | `store_conversation_batch` lacks `@observe` | N/A |

### Why 82% Orphans?

Аудит обнаружил 41/50 orphan traces. Основные источники:
1. **Исторические traces** от `validate_traces.py` ДО добавления `propagate_attributes`
2. **Потенциальная утечка контекста** при async-выполнении в LangGraph (нуждается в проверке)
3. **Тесты с Langfuse enabled** — conftest.py НЕ unset'ит `LANGFUSE_SECRET_KEY`, поэтому если `.env` содержит ключ, `@observe` будет реальным (не no-op)

### Callsites с `@observe` (35 total)

| Category | Count | Files |
|----------|-------|-------|
| Root trace | 1 | `bot.py:229` (`telegram-rag-query`) |
| Graph nodes | 8 | `graph/nodes/*.py` (`node-*`) |
| Cache methods | 8 | `integrations/cache.py` (`cache-*`) |
| Embedding methods | 5 | `integrations/embeddings.py` (`bge-m3-*`) |
| Qdrant methods | 3 | `services/qdrant.py` (`qdrant-*`) |
| ColBERT reranker | 1 | `services/colbert_reranker.py` (`colbert-rerank`) |
| Voyage methods | 5 | `services/voyage.py` (`voyage-*`) |
| LLM calls | 4 | Auto-traced via `langfuse.openai.AsyncOpenAI` |
| **MISSING** | 1 | `cache.py:390` `store_conversation_batch` |

---

## Task 1: Add `@observe` to `store_conversation_batch`

**Files:**
- Modify: `telegram_bot/integrations/cache.py:390`
- Test: `tests/unit/graph/test_cache_nodes.py`

**Step 1: Add the decorator**

В `telegram_bot/integrations/cache.py`, добавить `@observe` к `store_conversation_batch`:

```python
@observe(name="cache-conversation-batch-store")
async def store_conversation_batch(self, user_id: int, messages: list[tuple[str, str]]) -> None:
```

**Step 2: Run existing tests to verify no regression**

Run: `uv run pytest tests/unit/graph/test_cache_nodes.py tests/unit/integrations/test_cache_layers.py -v`
Expected: All tests PASS (no change in behavior — @observe is no-op in tests since LANGFUSE_SECRET_KEY not set)

**Step 3: Commit**

```bash
git add telegram_bot/integrations/cache.py
git commit -m "feat(observability): add @observe to store_conversation_batch (#123)"
```

---

## Task 2: Add `traced_pipeline` helper to `observability.py`

**Files:**
- Modify: `telegram_bot/observability.py`
- Test: `tests/unit/test_observability.py`

**Step 1: Write the failing test**

В `tests/unit/test_observability.py` добавить тест:

```python
class TestTracedPipeline:
    def test_traced_pipeline_returns_context_manager(self):
        """traced_pipeline should be usable as a context manager."""
        from telegram_bot.observability import traced_pipeline

        # With Langfuse disabled, should be a no-op context manager
        with traced_pipeline(session_id="test-123", user_id="user-1"):
            pass  # No error

    def test_traced_pipeline_accepts_tags(self):
        """traced_pipeline should accept optional tags."""
        from telegram_bot.observability import traced_pipeline

        with traced_pipeline(
            session_id="test-456",
            user_id="user-2",
            tags=["validation", "cold"],
        ):
            pass
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_observability.py::TestTracedPipeline -v`
Expected: FAIL — `ImportError: cannot import name 'traced_pipeline'`

**Step 3: Implement `traced_pipeline`**

В `telegram_bot/observability.py`, после блока `if LANGFUSE_ENABLED: ... else: ...`, добавить:

```python
def traced_pipeline(
    *,
    session_id: str,
    user_id: str,
    tags: list[str] | None = None,
):
    """Context manager for pipeline-level trace propagation.

    Wraps propagate_attributes with sensible defaults.
    Use at any entry point that invokes @observe-decorated functions.

    Usage:
        with traced_pipeline(session_id="validate-abc", user_id="system"):
            result = await graph.ainvoke(state)
    """
    return propagate_attributes(
        session_id=session_id,
        user_id=user_id,
        tags=tags or [],
    )
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/test_observability.py -v`
Expected: All tests PASS

**Step 5: Commit**

```bash
git add telegram_bot/observability.py tests/unit/test_observability.py
git commit -m "feat(observability): add traced_pipeline helper for entry points (#123)"
```

---

## Task 3: Add `traced_pipeline` to smoke/integration tests

**Files:**
- Modify: `tests/smoke/test_langgraph_smoke.py`
- Modify: `tests/integration/test_graph_paths.py`

**Step 1: Wrap smoke test in `traced_pipeline`**

В `tests/smoke/test_langgraph_smoke.py`, `test_full_graph_classify_to_respond`:

```python
from telegram_bot.observability import traced_pipeline

@pytest.mark.smoke
async def test_full_graph_classify_to_respond():
    """E2E: mock services, full graph pipeline from classify to respond."""
    # ... existing mock setup ...

    with traced_pipeline(session_id="smoke-test-20260209", user_id="smoke"):
        with patch(
            "telegram_bot.graph.nodes.generate._get_config",
            return_value=mock_gc,
        ):
            result = await graph.ainvoke(state)

    assert "response" in result
    assert result["response"]
```

**Step 2: Wrap integration tests in `traced_pipeline`**

В `tests/integration/test_graph_paths.py`, обновить `_patch_graph_configs` для включения `traced_pipeline`:

```python
from telegram_bot.observability import traced_pipeline

# В каждом тесте, обернуть graph.ainvoke:
with traced_pipeline(session_id="test-path1", user_id="integration"):
    with _patch_graph_configs(mock_gc):
        result = await graph.ainvoke(state)
```

Обновить ВСЕ 6 тестов: `test_path_chitchat_early_exit`, `test_path_cache_hit`, `test_path_happy_retrieve_rerank_generate`, `test_path_rewrite_loop_then_success`, `test_path_rewrite_exhausted_fallback`, `test_path_rewrite_ineffective_fallback`.

**Step 3: Run tests to verify no regression**

Run: `uv run pytest tests/smoke/test_langgraph_smoke.py tests/integration/test_graph_paths.py -v`
Expected: All tests PASS

**Step 4: Commit**

```bash
git add tests/smoke/test_langgraph_smoke.py tests/integration/test_graph_paths.py
git commit -m "fix(observability): wrap smoke/integration tests in traced_pipeline (#123)"
```

---

## Task 4: Update observability rules documentation

**Files:**
- Modify: `.claude/rules/observability.md`

**Step 1: Add `traced_pipeline` section**

В `.claude/rules/observability.md`, в секцию "Instrumented Services", добавить:

```markdown
### Entry Point Pattern

All entry points that invoke @observe-decorated code MUST use `traced_pipeline`:

| Entry Point | File | session_id format |
|-------------|------|-------------------|
| Telegram bot | `bot.py:handle_query` | `chat-{hash}-{YYYYMMDD}` |
| Validation | `scripts/validate_traces.py` | `validate-{run_id[:8]}` |
| Smoke tests | `tests/smoke/test_langgraph_smoke.py` | `smoke-test-{YYYYMMDD}` |
| Integration tests | `tests/integration/test_graph_paths.py` | `test-path{N}` |

```python
from telegram_bot.observability import traced_pipeline

with traced_pipeline(session_id="...", user_id="..."):
    result = await graph.ainvoke(state)
```
```

**Step 2: Update orphan trace count**

Добавить в `.claude/rules/observability.md`:

```markdown
### Orphan Trace Prevention

All `@observe`-decorated functions MUST be called within a `traced_pipeline` or `propagate_attributes` context.
Without this, each @observe call creates a separate root trace with session=None, userId=None.

Rule: `traced_pipeline` → `@observe(root)` → nested `@observe(children)`.
```

**Step 3: Commit**

```bash
git add .claude/rules/observability.md
git commit -m "docs(observability): add traced_pipeline entry point pattern (#123)"
```

---

## Task 5: Verify orphan rate < 10%

**Files:**
- Read: `scripts/validate_traces.py` (уже корректен)

**Step 1: Run validation and check traces**

```bash
make validate-traces-fast
```

**Step 2: Check Langfuse for orphan traces**

В Langfuse UI (http://localhost:3001):
1. Traces → filter by recent `validate-*` session
2. Verify: все node spans вложены в root trace `validation-query`
3. Verify: session_id и userId заполнены
4. Count orphans: traces без parent observation с session=None

**Step 3: Document results in issue #123**

Если orphan rate < 10%, закрыть issue с результатами.

---

## Summary

| Task | Scope | Estimated |
|------|-------|-----------|
| 1. Add @observe to store_conversation_batch | 1 line + test | 2 min |
| 2. Add traced_pipeline helper | ~15 LOC + tests | 5 min |
| 3. Wrap smoke/integration tests | 7 call sites | 5 min |
| 4. Update observability docs | documentation | 3 min |
| 5. Verify orphan rate | manual check | 5 min |

**Total: 5 tasks, ~20 min**

**Dependencies:** None — tasks are sequential but each is independently committable.

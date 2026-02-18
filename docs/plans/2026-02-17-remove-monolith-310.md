# Remove Monolith Query Path — Supervisor Only (#310)

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Remove the legacy monolith query path (`_handle_query_legacy`) and make the supervisor graph the only runtime for text queries.

**Architecture:** The supervisor path is already the default (`use_supervisor=True`). The legacy monolith path is dead code behind a deprecated flag. We remove it entirely: delete the legacy method, remove the `use_supervisor` config field, clean up backward-compat aliases, update tests and docs.

**Tech Stack:** Python 3.12, LangGraph, aiogram, Langfuse, Pydantic Settings

---

## WIP State (commit c828a0a)

Already completed:
- `telegram_bot/scoring.py` — extracted `write_langfuse_scores()` and `compute_checkpointer_overhead_proxy_ms()`
- `telegram_bot/config.py` — `use_supervisor` default changed to `True`
- `telegram_bot/bot.py` — legacy path moved to `_handle_query_legacy()` with deprecation warning
- `telegram_bot/agents/rag_agent.py` — imports updated to `telegram_bot.scoring` (unstaged)
- `tests/unit/test_bot_handlers.py` — removed unused `_supervisor_test_context` helper (unstaged)

## Remaining Tasks

### Task 1: Remove legacy path from bot.py

**Files:**
- Modify: `telegram_bot/bot.py:43-45` (remove backward-compat aliases)
- Modify: `telegram_bot/bot.py:506-529` (simplify handle_query — remove legacy branch)
- Delete: `telegram_bot/bot.py:531-648` (delete `_handle_query_legacy` method entirely)

**Step 1: Remove backward-compat aliases (bot.py:43-45)**

Delete these lines:
```python
# Aliases for backward compatibility — canonical implementations in scoring.py (#310)
_compute_checkpointer_overhead_proxy_ms = compute_checkpointer_overhead_proxy_ms
_write_langfuse_scores = write_langfuse_scores
```

**Step 2: Simplify handle_query — remove legacy branch (bot.py:506-529)**

Replace:
```python
    @observe(name="telegram-rag-query")
    async def handle_query(self, message: Message):
        """Handle user query via supervisor graph (#310: supervisor-only)."""
        pipeline_start = time.perf_counter()
        # Early typing ACK — user sees "typing..." immediately
        assert message.bot is not None
        assert message.from_user is not None
        bot = message.bot
        await bot.send_chat_action(chat_id=message.chat.id, action="typing")

        # --- Legacy monolith path (deprecated, removed in next release) ---
        if not self.config.use_supervisor:
            import warnings

            warnings.warn(
                "USE_SUPERVISOR=false is deprecated and will be removed. "
                "The monolith query path is no longer maintained (#310).",
                DeprecationWarning,
                stacklevel=1,
            )
            await self._handle_query_legacy(message, pipeline_start)
            return

        await self._handle_query_supervisor(message, pipeline_start)
```

With:
```python
    @observe(name="telegram-rag-query")
    async def handle_query(self, message: Message):
        """Handle user query via supervisor graph (#310: supervisor-only)."""
        pipeline_start = time.perf_counter()
        assert message.bot is not None
        assert message.from_user is not None
        bot = message.bot
        await bot.send_chat_action(chat_id=message.chat.id, action="typing")

        await self._handle_query_supervisor(message, pipeline_start)
```

**Step 3: Delete `_handle_query_legacy` method entirely (bot.py:531-648)**

Remove the entire method from `async def _handle_query_legacy` through the end of its body (before `_handle_query_supervisor`).

**Step 4: Remove unused imports from bot.py**

After removing legacy path, these imports in bot.py are no longer needed:
- `from .graph.graph import build_graph` (line 23) — only used in legacy + voice; voice still uses it ⚠️
- `from .graph.state import make_initial_state` (line 24) — only used in legacy + voice; voice still uses it ⚠️

CHECK: `build_graph` and `make_initial_state` are still used in `handle_voice`. Do NOT remove them.

Remove only:
- `import random` (line 8) — was only used in legacy path's judge sampling; supervisor path passes config to rag_agent tool
- `import warnings` (no longer needed — was inline import in legacy branch, not top-level)

Actually `random` is not imported at top level (it's not in the imports). And `warnings` was an inline import inside the if-branch. So **no imports to remove**.

**Step 5: Run tests**

Run: `cd /home/user/projects/rag-fresh-wt-310 && uv run pytest tests/unit/test_bot_handlers.py -x -v`
Expected: Some tests FAIL because they reference `_write_langfuse_scores` alias

---

### Task 2: Remove `use_supervisor` config field

**Files:**
- Modify: `telegram_bot/config.py:298-302`

**Step 1: Remove the field**

Delete:
```python
    # Supervisor architecture (#240, #310 — default since v3.3)
    use_supervisor: bool = Field(
        default=True,
        validation_alias=AliasChoices("use_supervisor", "USE_SUPERVISOR"),
    )
```

Keep `supervisor_model` — it's still used for the supervisor LLM routing model.

**Step 2: Remove `self.config.use_supervisor` reference in bot.py**

Already done in Task 1 (the legacy branch is deleted).

**Step 3: Remove `use_supervisor=True` from test fixtures**

File: `tests/unit/agents/test_supervisor_observability.py:14,26`
- Remove `use_supervisor=True` from `supervisor_config` fixture (field no longer exists)

File: `tests/unit/test_bot_handlers.py` — the `test_handle_query_legacy_path_emits_deprecation_warning` test (line 1307-1345)
- DELETE this entire test — no legacy path to test

---

### Task 3: Update tests that reference removed aliases

**Files:**
- Modify: `tests/unit/test_bot_handlers.py`

**Step 1: Fix voice tests that patch `telegram_bot.bot._write_langfuse_scores`**

These tests patch `telegram_bot.bot._write_langfuse_scores` which no longer exists as an alias.
The voice handler in `bot.py` now calls `_write_langfuse_scores(lf, result)` — wait, no.

Check: bot.py handle_voice (line 913) still calls `_write_langfuse_scores(lf, result)`. After Task 1 removes the alias, this will break.

**Fix:** Update `handle_voice` to use `write_langfuse_scores` directly (since it's already imported from scoring.py).

Update in `bot.py`:
- Line 577: `_compute_checkpointer_overhead_proxy_ms(result, ainvoke_wall_ms)` → already an alias, replace with `compute_checkpointer_overhead_proxy_ms(result, ainvoke_wall_ms)` — WAIT, line 577 is in the legacy method which we deleted. But line 835-836 in handle_voice uses the same alias.

In `handle_voice` (line 835-836):
```python
result["checkpointer_overhead_proxy_ms"] = (
    _compute_checkpointer_overhead_proxy_ms(result, ainvoke_wall_ms)
)
```
→ Replace with:
```python
result["checkpointer_overhead_proxy_ms"] = (
    compute_checkpointer_overhead_proxy_ms(result, ainvoke_wall_ms)
)
```

In `handle_voice` (line 913):
```python
_write_langfuse_scores(lf, result)
```
→ Replace with:
```python
write_langfuse_scores(lf, result)
```

**Step 2: Update test patches**

In `test_bot_handlers.py`, update all patches from:
- `telegram_bot.bot._write_langfuse_scores` → `telegram_bot.bot.write_langfuse_scores`

Files to update (search for `_write_langfuse_scores` in tests):
- `TestHistorySaveOnResponse.test_handle_voice_saves_history` (line 419)
- `TestCheckpointNamespace.test_handle_voice_passes_voice_checkpoint_ns` (line 725)
- `TestHandleVoiceExceptionHandling.test_post_pipeline_error_still_writes_scores` (line 790)
- `TestHandleVoiceExceptionHandling.test_post_pipeline_error_does_not_send_false_error` (line 820)
- `TestHandleVoiceExceptionHandling.test_genuine_pipeline_failure_sends_error` (line 843)
- `TestHandleVoiceExceptionHandling.test_cleanup_error_with_no_result_does_not_send_false_error` (line 875)
- `TestHandleVoiceExceptionHandling.test_scores_written_even_if_trace_update_fails` (line 906)

**Step 3: Update `TestWriteLangfuseScores` class**

Tests in this class import `from telegram_bot.bot import _write_langfuse_scores`.
Update to: `from telegram_bot.scoring import write_langfuse_scores`

Affected tests (lines 1148-1252):
- `test_latency_total_ms_uses_wall_time`
- `test_latency_total_ms_fallback_zero`
- `test_real_scores_from_state`
- `test_write_langfuse_scores_includes_ttft`
- `test_writes_embedding_error_score`

**Step 4: Delete the legacy deprecation test**

Delete `TestSupervisorIntegration.test_handle_query_legacy_path_emits_deprecation_warning` (lines 1307-1345).

**Step 5: Run tests**

Run: `cd /home/user/projects/rag-fresh-wt-310 && uv run pytest tests/unit/test_bot_handlers.py tests/unit/agents/test_supervisor_observability.py -x -v`
Expected: ALL PASS

---

### Task 4: Run full test suite and lint

**Step 1: Run lint**

Run: `cd /home/user/projects/rag-fresh-wt-310 && uv run ruff check . && uv run ruff format --check .`
Expected: PASS (fix any issues)

**Step 2: Run full unit tests**

Run: `cd /home/user/projects/rag-fresh-wt-310 && uv run pytest tests/unit/ -n auto --timeout=30`
Expected: ALL PASS

---

### Task 5: Update documentation

**Files:**
- Modify: `CLAUDE.md:124` — remove `USE_SUPERVISOR=false` from settings line
- Modify: `.claude/rules/features/telegram-bot.md:22-28,118,182-205` — update architecture diagram and config table
- Modify: `.claude/rules/observability.md:87,91` — update span table
- Modify: `docs/PIPELINE_OVERVIEW.md:332` — update feature flag text

**Step 1: CLAUDE.md**

Line 124: Remove `, USE_SUPERVISOR=false` from the settings list. Remove `GUARD_MODE=hard|soft|log` too? No — only remove USE_SUPERVISOR.

**Step 2: .claude/rules/features/telegram-bot.md**

- Line 22-28: Remove dual-path architecture diagram. Make supervisor the only architecture shown:
```
Text:  User Message → ThrottlingMiddleware → ErrorMiddleware
                   → PropertyBot.handle_query()
                   → _handle_query_supervisor()
                   → build_supervisor_graph(supervisor_llm, tools)
                   → Supervisor LLM → tool_choice (rag_search | history_search | direct_response)
                   → tool executes → respond
                   → Langfuse: agent_used + supervisor_latency_ms + supervisor_model scores
```
- Line 118: Remove `use_supervisor` row from config table
- Lines 182-205: Remove "Supervisor Path (USE_SUPERVISOR=true)" heading; make it the default description. Remove feature flag line 205.

**Step 3: .claude/rules/observability.md**

- Line 87: Remove `_handle_query_supervisor` entry (merge into `handle_query` row — it's now the only path)
- Line 91: Remove "When `USE_SUPERVISOR=true`" — it's always this way now

**Step 4: docs/PIPELINE_OVERVIEW.md**

- Line 332: Change `**Feature flag:** USE_SUPERVISOR=true (default: off)` to `**Architecture:** Supervisor-only (since #310). Monolith path removed.`

**Step 5: Run lint on docs (optional)**

Run: `cd /home/user/projects/rag-fresh-wt-310 && uv run ruff check . && uv run ruff format --check .`

---

### Task 6: Final verification and commit

**Step 1: Run full checks**

Run: `cd /home/user/projects/rag-fresh-wt-310 && uv run ruff check . && uv run ruff format --check . && uv run pytest tests/unit/ -n auto --timeout=30`
Expected: ALL PASS

**Step 2: Stage only changed files**

```bash
cd /home/user/projects/rag-fresh-wt-310
git diff --stat  # verify only expected files
git add telegram_bot/bot.py telegram_bot/config.py telegram_bot/scoring.py telegram_bot/agents/rag_agent.py
git add tests/unit/test_bot_handlers.py tests/unit/agents/test_supervisor_observability.py
git add CLAUDE.md .claude/rules/features/telegram-bot.md .claude/rules/observability.md docs/PIPELINE_OVERVIEW.md docs/plans/2026-02-17-remove-monolith-310.md
git diff --cached --stat  # verify ONLY our files
```

**Step 3: Commit**

```bash
git commit -m "feat(arch): remove monolith query path, supervisor-only runtime (#310)"
```

Do NOT push — report to lead first.

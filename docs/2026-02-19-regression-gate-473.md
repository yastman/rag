***REMOVED*** Automated Regression Gate — Issue ***REMOVED***473

***REMOVED******REMOVED*** Execution

- **Date:** 2026-02-19
- **Time:** Executed during chore/regression-gate-473 session
- **Branch:** `chore/regression-gate-473`
- **Context:** Post-rebuild regression gate covering 65 issues closed 2026-02-18/19 (asyncpg fix included)
- **Executor:** Claude Sonnet 4.6 (W-REGRESS worker)

---

***REMOVED******REMOVED*** Section 7: Automated Checks

***REMOVED******REMOVED******REMOVED*** Lint & Format

| Check | Result | Details |
|-------|--------|---------|
| `ruff check .` | ✅ PASS | All checks passed (519 files) |
| `ruff format --check .` | ✅ PASS | 519 files already formatted |

***REMOVED******REMOVED******REMOVED*** Type Checking

| Check | Result | Details |
|-------|--------|---------|
| `mypy telegram_bot/ --ignore-missing-imports` | ⚠️ PRE-EXISTING | 10 errors in 3 files |

**mypy error breakdown (pre-existing, not regressions):**
- `telegram_bot/agents/rag_tool.py:30` — `no-any-return` (1 error)
- `telegram_bot/agents/history_tool.py:101` — `no-any-return` (1 error)
- `telegram_bot/bot.py` — `no-any-return` (2 errors) + `call-overload` for `Langfuse.create_score` (6 errors)

These errors pre-date this regression window and are not introduced by the 65 issues closed 2026-02-18/19.

***REMOVED******REMOVED******REMOVED*** Unit Tests (Parallel — `pytest -n auto`)

| Metric | Value |
|--------|-------|
| **Passed** | 2693 |
| **Failed** | 0 |
| **Skipped** | 19 (optional extras not installed) |
| **Total collected** | 2712 |
| **Duration** | 45.42s |
| **Mode** | `pytest-xdist -n auto` |

**Skip breakdown (all expected — optional extras):**
- `fastapi` (voice extra): 4 skipped
- `pymupdf` (ingest extra): 2 skipped
- `mlflow` (eval extra): 3 skipped
- `ragas` (eval extra): 2 skipped
- `cocoindex` (ingest extra): 4 skipped
- `pandas` (eval extra): 1 skipped
- `opentelemetry-instrumentation`: 1 skipped
- `livekit` (voice extra): 2 skipped

***REMOVED******REMOVED******REMOVED*** Integration Tests (No Docker)

| File | Tests | Result | Duration |
|------|-------|--------|---------|
| `tests/integration/test_graph_paths.py` | 12 | ✅ PASS | 2.62s |

**Test list:**
- `test_path_chitchat_early_exit` ✅
- `test_path_guard_blocked` ✅
- `test_path_cache_hit` ✅
- `test_path_general_bypasses_semantic_cache` ✅
- `test_path_happy_retrieve_rerank_generate` ✅
- `test_path_rewrite_loop_then_success` ✅
- `test_path_rewrite_exhausted_fallback` ✅
- `test_path_rewrite_ineffective_fallback` ✅
- `test_path_rewrite_stopped_by_score_guard` ✅
- `test_path_voice_transcribe_full_rag` ✅
- `TestConversationMemory::test_second_query_sees_first_in_messages` ✅
- `TestConversationMemory::test_summarize_failure_does_not_fail_pipeline` ✅

Note: 12 tests collected (expanded from expected 6 — additional rewrite loop and memory tests added).

---

***REMOVED******REMOVED*** Targeted Regression

***REMOVED******REMOVED******REMOVED*** Bot Core

| Test Group | File | Tests | Result | Duration |
|------------|------|-------|--------|---------|
| Bot Handlers | `test_bot_handlers.py` | 93 | ✅ PASS | — |
| Bot Scores | `test_bot_scores.py` | 33 | ✅ PASS | — |
| Bot Observability | `test_bot_observability.py` | 2 | ✅ PASS | — |
| **Total** | | **128** | **✅ PASS** | **8.49s** |

***REMOVED******REMOVED******REMOVED*** Agents

| Test Group | File | Tests | Result |
|------------|------|-------|--------|
| Agent Factory | `test_agent_factory.py` | 8 | ✅ |
| Agent Integration | `test_bot_agent_integration.py` | 3 | ✅ |
| Context | `test_context.py` | 7 | ✅ |
| CRM Tools | `test_crm_tools.py` | 20 | ✅ |
| History Graph Integration | `test_history_graph_integration.py` | 8 | ✅ |
| History Graph Nodes | `test_history_graph_nodes.py` | 21 | ✅ |
| History Graph State | `test_history_graph_state.py` | 2 | ✅ |
| History Tool | `test_history_tool.py` | 9 | ✅ |
| Lead Score Sync Tool | `test_lead_score_sync_tool.py` | 4 | ✅ |
| Nurturing Analytics Tools | `test_nurturing_analytics_tools.py` | 4 | ✅ |
| Nurturing Observability | `test_nurturing_observability.py` | 2 | ✅ |
| RAG Pipeline | `test_rag_pipeline.py` | 20 | ✅ |
| RAG Tool | `test_rag_tool.py` | 14 | ✅ |
| Streaming | `test_streaming.py` | 4 | ✅ |
| Supervisor Observability | `test_supervisor_observability.py` | 9 | ✅ |
| **Total** | | **147** | **✅ PASS (6.80s)** |

***REMOVED******REMOVED******REMOVED*** Graph (Voice LangGraph)

| Suite | Tests | Result | Duration |
|-------|-------|--------|---------|
| `tests/unit/graph/` (all) | 321 | ✅ PASS | 7.54s |

***REMOVED******REMOVED******REMOVED*** Dependencies

| Check | Result | Details |
|-------|--------|---------|
| `test_telegram_bot_pyproject_deps.py` | ✅ PASS | 1/1 (aiogram-dialog present) |
| `asyncpg` import | ✅ PASS | v0.31.0 |
| `apscheduler` import | ✅ PASS | v3.11.2 |

---

***REMOVED******REMOVED*** Overall Results Matrix

| Section | Check | Status |
|---------|-------|--------|
| 7.1 | Lint (ruff check) | ✅ PASS |
| 7.2 | Format (ruff format) | ✅ PASS |
| 7.3 | Types (mypy) | ⚠️ 10 pre-existing errors |
| 7.4 | Unit Tests (2693 tests, -n auto) | ✅ PASS |
| 7.5 | Integration Tests (12 graph paths) | ✅ PASS |
| T.1 | Bot Handlers (93 tests) | ✅ PASS |
| T.2 | Bot Scores (33 tests) | ✅ PASS |
| T.3 | Bot Observability (2 tests) | ✅ PASS |
| T.4 | Agents (147 tests) | ✅ PASS |
| T.5 | Graph (321 tests) | ✅ PASS |
| T.6 | Dependencies (asyncpg + apscheduler) | ✅ PASS |

**Total tests executed:** 2693 unit + 12 integration = **2705 tests passed, 0 failed**

---

***REMOVED******REMOVED*** Notes

- **Sections 0–6** (interactive Telegram bot smoke testing, Docker services, voice pipeline, CRM flows) are covered by the separate E2E smoke run documented in issue ***REMOVED***472.
- **mypy errors**: 10 pre-existing type errors in `bot.py`, `rag_tool.py`, `history_tool.py`. Not regressions introduced by the 65 issues closed 2026-02-18/19. Tracked separately.
- **Skipped tests**: All 19 skips are expected — optional extras (`voice`, `ingest`, `eval`) not installed in this environment.

---

***REMOVED******REMOVED*** Verdict

```
✅ AUTOMATED REGRESSION PASS

All 2705 tests pass (0 failures, 0 errors).
Lint: clean. Format: clean. Types: 10 pre-existing errors (not regressions).
Post-rebuild image with asyncpg fix verified functional across full test matrix.
```

Refs: ***REMOVED***473

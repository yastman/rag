# Pitfalls Research

**Domain:** Production RAG + CRM Telegram bot — refactoring + feature expansion
**Researched:** 2026-02-19
**Confidence:** HIGH (sourced from active project issues, codebase audit, and verified patterns)

---

## Critical Pitfalls

### Pitfall 1: Guard Bypass Through Input Path Proliferation

**What goes wrong:**
Security checks are added to the original code path but new paths (agent direct responses, tool calls, menu shortcuts) are introduced without wiring guard to them. The project already has this confirmed as issue #439: the text agent path sends raw user input to `agent.ainvoke()` with zero content filtering. Three independent bypass vectors exist simultaneously.

**Why it happens:**
Guard was designed as a LangGraph node in the graph pipeline (voice path). When the text path was migrated to `create_agent` SDK, guard was not propagated to the new entry point. Each new input surface (menu callbacks, HITL resume, `/history` command, new CRM tools) creates another bypass. Developers think about the happy path; security reviewers think about surfaces.

**How to avoid:**
- Add `detect_injection(message.text)` BEFORE `agent.ainvoke()` in `bot.py:_handle_query_supervisor` as a synchronous pre-filter (sub-1ms, no network call).
- Guard must run at the Telegram handler layer, not inside a tool or pipeline node. Every `message.text` path needs a pre-check.
- Add safety instructions to `DEFAULT_SYSTEM_PROMPT` in `agents/agent.py` for defense in depth.
- When adding menu callbacks, treat `callback.data` as user-controlled input: validate callback format strictly and do not pass raw callback text to the LLM.
- When implementing HITL resume (`Command(resume=...)`), validate resume payloads before passing to tool execution.
- Store `original_user_query` in `BotContext` so guard always checks the original text, not the agent-reformulated version.

**Warning signs:**
- Any new `message.answer()` or `agent.ainvoke()` call in a handler that does not have a preceding `detect_injection()` call.
- A new command handler (e.g., `/report`, `/filter`) that extracts arguments from `message.text` and uses them as LLM input without sanitization.
- Agent-reformulated queries reaching guard instead of original user text (issue #430 root cause — agent reformulates before `rag_search`, so guard inside pipeline sees cleaned text).

**Phase to address:**
Phase 1 (pipeline refactor) — guard pre-check must be added to bot.py as part of the text path change. Do not defer to Phase 2 or later.

---

### Pitfall 2: LangGraph HITL Requires a Persistent Checkpointer — MemorySaver Loses State Across Processes

**What goes wrong:**
HITL via `interrupt()` pauses graph execution and serializes state to the checkpointer. If the bot process restarts between the `interrupt()` call and the user's Telegram callback click (which is common — Telegram users take minutes to respond), the state is gone. MemorySaver stores state in Python process memory only. The user clicks "Confirm" and the bot has no state to resume from, causing a `KeyError` or silent failure.

**Why it happens:**
`self._agent_checkpointer = create_fallback_checkpointer()` (bot.py:1144) uses MemorySaver by design because `redisvl` JSON serialization fails for LangChain `Message` objects (issue #420). HITL interrupts require the same checkpointer that holds the interrupted graph state to be available at resume time.

**How to avoid:**
- HITL confirmation callbacks must be handled within the same bot process (single-process deployment, no horizontal scaling for HITL).
- OR: Use a serialization-safe checkpointer (custom Redis checkpointer that serializes Message objects via pickle or msgpack, not redisvl JSON).
- OR: Implement a stateless HITL pattern — store the pending operation parameters in Redis directly (not in graph state) and reconstruct the tool call on confirm, rather than resuming the LangGraph thread.
- The stateless pattern is more robust: on "Confirm" callback, read `{trace_id → {tool_name, args}}` from Redis TTL key, execute the tool directly without graph resumption.
- Set a short TTL (5-10 minutes) on HITL pending state in Redis and show the user a "confirmation expired" message on timeout.

**Warning signs:**
- HITL confirmation appears to work in dev (single process, MemorySaver) but fails silently in production after any deployment or bot restart.
- Users report "operation cancelled" or no response after clicking "Confirm" — graph state was lost.
- `thread_id` used for HITL resume does not match the thread_id of the interrupted run (common if chat_id vs user_id is used inconsistently).

**Phase to address:**
Phase 2 (HITL implementation) — design the persistence strategy before writing `hitl.py`. Do not use MemorySaver for HITL state.

---

### Pitfall 3: Pipeline Refactor (11→6 nodes) Silently Loses Observability and Score Coverage

**What goes wrong:**
The 11-node LangGraph graph has 35 `@observe` spans, 14 RAG-specific Langfuse scores, and latency tracking per stage (`latency_stages` dict). When converting nodes to plain async functions, developers remove the `@observe` decorator or forget to call `write_langfuse_scores()` from the new code path. Langfuse dashboards go dark. Regressions in retrieval quality cannot be detected because scores are missing.

**Why it happens:**
LangGraph nodes are individually wrapped with `@observe(name="node-*")`. When rewriting as `rag_pipeline()` (plain async functions), the `@observe` decorator must be re-applied and the `latency_stages` dict must be populated manually. The `write_langfuse_scores()` call in `rag_tool.py` depends on specific keys in the result dict (`cache_hit`, `rerank_applied`, `grade_confidence`, etc.). If the new pipeline returns a different structure, scores silently write zeros or are skipped.

**How to avoid:**
- Keep the result dict schema identical to the current `RAGState` fields that `write_langfuse_scores()` reads. Do not rename keys.
- Add `@observe(name="node-cache-check")`, `@observe(name="node-retrieve")`, etc. to each new async function — one-for-one replacement.
- Write a test in `tests/unit/agents/test_rag_pipeline.py` that asserts specific keys exist in the returned dict: `cache_hit`, `rerank_applied`, `search_results_count`, `grade_confidence`, `latency_stages`.
- Run `make eval-rag` after the refactor and verify RAGAS faithfulness score is unchanged (>= 0.8 threshold).
- Verify that Langfuse shows 14 scores per trace after refactor, not fewer.

**Warning signs:**
- After refactor, `lf.create_score()` calls in `write_langfuse_scores()` get `None` or `0` values for `cache_hit`, `rerank_applied`, `grade_confidence`.
- `latency_stages` key is missing from pipeline result → `compute_checkpointer_overhead_proxy_ms()` breaks.
- `rag_result_store` side-channel (used by `bot.py` to get `documents` for source attribution) stops being populated.
- RAGAS eval score drops by > 0.1 after refactor.

**Phase to address:**
Phase 1 (pipeline refactor) — build the test for result dict schema BEFORE writing the new pipeline functions, then use it as the acceptance criterion.

---

### Pitfall 4: Semantic Cache Permanently Broken by Agent Query Reformulation

**What goes wrong:**
Issue #430 confirms this: the agent LLM reformulates user queries before calling `rag_search`. The semantic cache key is based on the embedding of the tool-call query string, not the original user message. Every unique agent reformulation produces a cache miss even for identical user questions. Cache hit rate stays near zero for the text path (~80% of traffic).

**Why it happens:**
In the voice path: `query = stt_text → make_initial_state(query=query)` — no reformulation, cache works.
In the text path: `user_message → agent LLM → rag_search(query="reformulated") → make_initial_state(query="reformulated")` — reformulation breaks cache key consistency.

If this is not fixed at the architectural level during the pipeline refactor (Phase 1), adding more features on top of a broken cache means every subsequent phase has incorrect performance data. Cache hit rate metrics will look correct (the metric pipeline works) but will always read 0%, masking that the fix was never applied.

**How to avoid:**
- Store `original_user_query` in `BotContext` at the point where `message.text` is read in `bot.py`.
- In `rag_tool.py`, use `ctx.original_query or query` as the cache key: compute embedding for the original query and check/store cache under that key, even if retrieval uses the reformulated query.
- OR: Instruct the agent in `DEFAULT_SYSTEM_PROMPT` to pass user text verbatim to `rag_search` without reformulation.
- Add an integration test that calls `rag_pipeline()` twice with identical user text (different `BotContext.original_query` vs reformulated) and asserts cache hit on second call.

**Warning signs:**
- `cache_hit` score in Langfuse is always `0` or `false` for text-path traces even with repeated identical questions.
- `embeddings_cache_hit` is `true` (embedding is cached) but `cache_hit` is `false` (semantic cache misses because query text differs).
- Two consecutive identical questions from the same user result in two separate LLM generation calls.

**Phase to address:**
Phase 1 (pipeline refactor) — fix as part of the `rag_pipeline()` design. The new pipeline receives `original_query` as a separate parameter from `query` (agent reformulation).

---

### Pitfall 5: aiogram-dialog Menu Conflicts with Free-Text Handler Registration Order

**What goes wrong:**
aiogram's update dispatcher processes handlers in registration order. `dp.message(F.text)(self.handle_query)` is registered in `_register_handlers()` (bot.py:319), which runs before `aiogram_setup_dialogs(self.dp)` in `start()`. Dialog text handlers registered by `aiogram_setup_dialogs` may not override the free-text handler if registration order is wrong. Result: users who are inside a dialog menu and type free text get routed to the agent instead of the menu handler, or vice versa.

**Why it happens:**
aiogram uses a priority + registration order model. `aiogram-dialog` registers its own middleware and message handlers that intercept updates for active dialog sessions. If `handle_query` is too broadly registered (no `F.text.as_("text") & ...` filter), it catches updates before the dialog can claim them.

**How to avoid:**
- Register `handle_query` AFTER `aiogram_setup_dialogs(self.dp)`, or add a filter that checks for active dialog state before routing to the agent.
- Use aiogram-dialog's `SimpleEventMiddleware` or check `dialog_manager.has_context()` at the top of `handle_query` to delegate to dialog if active.
- Test: simulate a user mid-dialog (active dialog window) sending a free-text message and assert the dialog handler processes it, not the agent.
- Alternatively, make `handle_query` explicitly exit when an active dialog is detected: `if await dialog_manager.has_active_dialog(): return`.

**Warning signs:**
- Users in a menu dialog receive RAG responses to their menu text selections.
- `/start` re-opens a dialog but old dialog state is stacked, leading to unexpected `StartMode` behavior.
- aiogram-dialog raises `NoActiveDialogFound` when the free-text handler intercepts a dialog button callback.
- Test: `dp.message(F.text)` filter matches before `aiogram-dialog` middleware runs — check handler priority in test output.

**Phase to address:**
Phase 1 or the menu skeleton phase — the registration order must be established when `aiogram_setup_dialogs` is first added. The existing `start()` method already calls `aiogram_setup_dialogs` after `_register_handlers`, which is the correct order — but it must be validated with a test case.

---

### Pitfall 6: Kommo OAuth2 Race Condition Under Concurrent Tool Calls

**What goes wrong:**
When a manager asks a question that triggers multiple parallel CRM tool calls (e.g., `crm_get_deal` + `crm_get_contacts` simultaneously from the agent), both tools call `get_valid_token()` at the same time. If the token is about to expire, both calls hit `force_refresh()` concurrently. The first refresh invalidates the refresh_token. The second refresh uses the now-invalidated refresh_token and gets a 401, causing a tool failure.

**Why it happens:**
`KommoTokenStore.force_refresh()` is not protected by a lock. The current implementation (kommo_token_store.py:53-80) does a Redis `hgetall`, HTTP POST, then `hset`. Under concurrent load, two coroutines can both read "token needs refresh", both POST to Kommo, and the second one uses a stale refresh_token that was already consumed by the first.

**How to avoid:**
- Add an `asyncio.Lock` per subdomain in `KommoTokenStore.__init__`: `self._refresh_lock = asyncio.Lock()`.
- In `force_refresh()`: `async with self._refresh_lock: ...` — only one refresh runs at a time.
- Alternatively, use a Redis `SET NX EX` lock (distributed lock) for multi-process deployments, but an asyncio.Lock is sufficient for single-process bot.
- Add a unit test: `asyncio.gather(store.get_valid_token(), store.get_valid_token())` with an expired token and verify `force_refresh` is called exactly once.

**Warning signs:**
- Sporadic 401 errors from Kommo API when multiple CRM tools are called in the same agent turn.
- Langfuse shows CRM tool spans failing with "invalid refresh token" at irregular intervals, correlating with manager queries that invoke 2+ CRM tools.
- The Redis `kommo:tokens:{subdomain}` hash contains a refresh_token that Kommo has already invalidated.

**Phase to address:**
Phase 2 (CRM tool expansion) — fix before adding more parallel CRM tools. The race condition probability increases with each additional simultaneous tool call.

---

### Pitfall 7: APScheduler v3 API Is Not Forward-Compatible with v4

**What goes wrong:**
`NurturingScheduler` uses APScheduler v3 (`BackgroundScheduler`, `add_job()`). APScheduler v4 (currently alpha/pre-release) has a completely different API: `add_job()` → `add_schedule()`, `BackgroundScheduler` → `AsyncScheduler`, `pytz` → `zoneinfo`, and job stores are incompatible. If Renovate bumps APScheduler from 3.x to 4.x without pinning, the scheduler silently breaks at startup.

**Why it happens:**
APScheduler v4.0 is published to PyPI under the `APScheduler` package name but with a different API. The Renovate dashboard (Issue #11) tracks all deps. If no version constraint pins `<4`, a weekly Renovate batch may include this upgrade.

**How to avoid:**
- Pin `apscheduler>=3.10,<4` in `pyproject.toml`.
- Add a comment: `# v4 has breaking API changes — migration requires rewrite of NurturingScheduler`.
- Before migrating to v4: consider replacing APScheduler with `asyncio` + Redis TTL key polling (`asyncio.create_task` + `asyncio.sleep`) for simplicity. The nurturing scheduler runs one batch job at a configurable interval — a plain `asyncio.sleep` loop is sufficient.
- The v4 migration path (official docs confirmed): `BlockingScheduler`/`BackgroundScheduler` → `AsyncScheduler`, `add_job()` → `add_schedule()`, pytz zones → zoneinfo.

**Warning signs:**
- Renovate PR bumps `APScheduler` to `^4.0` — reject immediately.
- `from apscheduler.schedulers.background import BackgroundScheduler` raises `ImportError` after an upgrade.
- `scheduler.add_job(...)` raises `AttributeError` — the v4 API changed to `add_schedule()`.

**Phase to address:**
Any phase that touches `nurturing_scheduler.py` — add the version pin immediately. Backlog item to replace APScheduler with asyncio pattern.

---

## Technical Debt Patterns

| Shortcut | Immediate Benefit | Long-term Cost | When Acceptable |
|----------|-------------------|----------------|-----------------|
| `MemorySaver` for agent checkpointer | Avoids Redis JSON serialization bug (#420) | HITL state lost on restart; no cross-process state | OK until HITL is implemented; must be fixed in Phase 2 |
| Guard runs inside pipeline (voice) but not at handler level (text) | Guard added incrementally | Asymmetric security surface; text path always unguarded | Never — fix in Phase 1 |
| `build_graph()` rebuilt per-request in `rag_tool.py` | Stateless, simple | LangGraph graph compilation overhead on every tool call (~50ms) | Acceptable until profiling shows it in p95 |
| `rag_result_store` side-channel dict for cross-boundary data | Works without refactoring BotContext | Fragile implicit coupling between tool and handler | Replace with explicit `BotContext` field in Phase 1 |
| `detect_injection()` only runs on voice path | Guard was built for voice pipeline | Text path is unguarded (issue #439) | Never acceptable in production |
| `create_bot_agent()` called per-message | Simple, no caching | Agent graph recompiled + tools re-instantiated per message; ~10ms overhead | Acceptable at current scale; cache if > 100 req/s |

---

## Integration Gotchas

| Integration | Common Mistake | Correct Approach |
|-------------|----------------|------------------|
| Kommo OAuth2 | Call `force_refresh()` concurrently from parallel tool calls | Lock `force_refresh()` with `asyncio.Lock` per subdomain |
| Kommo OAuth2 | Use standard OAuth2 flow when long-lived tokens suffice | For single-account integrations, use Kommo long-lived tokens (no refresh needed, 1-5 year TTL) |
| LangGraph `interrupt()` | Assume MemorySaver persists across restarts | Use Redis checkpointer with serialization-safe Message encoding, or stateless HITL via Redis TTL keys |
| LangGraph `interrupt()` | Call `interrupt()` inside a `@tool` without a persistent checkpointer | `interrupt()` requires checkpointer AND the graph must be compiled with it; `create_agent` must receive the same checkpointer |
| aiogram-dialog | Register `F.text` handler before `setup_dialogs()` | Always call `setup_dialogs()` AFTER all message handler registrations, or add dialog-state check at top of free-text handler |
| aiogram-dialog | Use `dp.message(F.text)` without state filter | Add `~StateFilter(default_state)` or explicit dialog-context check to avoid catching dialog text inputs |
| Langfuse scores | Call `write_langfuse_scores(lf, result)` with missing keys in result dict | Validate result dict keys in unit test before writing; use `.get()` with defaults in `write_langfuse_scores` |
| BGE-M3 API | Use `/encode/sparse` expecting `sparse_vecs` key | Returns `lexical_weights` — known project bug, already fixed; document for new contributors |
| Telegram E2E tests | Run bot in polling mode while test also calls `getUpdates` | Telegram only allows one active update consumer; tests must use webhook mode or mock the Telegram API at the HTTP layer |

---

## Performance Traps

| Trap | Symptoms | Prevention | When It Breaks |
|------|----------|------------|----------------|
| `build_graph()` per tool call | p95 latency grows as graph complexity increases (LangGraph compile overhead) | Cache compiled graph in `BotContext` or as a module-level singleton | Noticeable at > 50 req/s |
| `create_bot_agent()` per message | Agent graph recompiled per message; tool list re-instantiated | Cache agent instance keyed by `(model, tool_set_hash, checkpointer_id)` | Noticeable at > 100 req/s |
| MemorySaver grows unbounded | Memory leak: every conversation accumulates in-process; bot restarts to recover | Implement retention (`MAX_REWRITE_ATTEMPTS`, conversation TTL) or switch to Redis checkpointer with TTL | After ~10k conversations |
| Semantic cache never hits (agent reformulation) | Cache hit rate ~0% for text path; embedding costs 3x expected | Fix query key to use `original_user_query`, not reformulated agent query | Immediately — issue #430 |
| HITL `interrupt()` pauses asyncio event loop | All concurrent requests for the same thread block on interrupt | `interrupt()` suspends graph execution but does not block the event loop — it's async-safe in LangGraph | N/A — LangGraph handles correctly, but developer must not use `asyncio.Event.wait()` as HITL bridge |

---

## Security Mistakes

| Mistake | Risk | Prevention |
|---------|------|------------|
| No pre-agent guard on text path (issue #439) | Prompt injection attacks bypass all safety rules; system prompt leakage | Add `detect_injection(message.text)` before `agent.ainvoke()` in `_handle_query_supervisor` |
| Agent system prompt contains zero safety instructions (issue #439, Gap #2) | Agent responds to jailbreak attempts without resistance | Add refusal rules and safety instructions to `DEFAULT_SYSTEM_PROMPT` |
| HITL confirm callback accepts any `trace_id` from `callback.data` | Attacker can forge `hitl:confirm:{any_trace_id}` to approve arbitrary operations | Validate that `trace_id` belongs to the current `user_id` — store `{trace_id → user_id}` in Redis HITL state |
| Guard checks agent-reformulated query, not original user input (issue #430, #439) | Injection patterns in original text are cleaned by agent before guard sees them | Guard must run on original `message.text` before any LLM processing |
| Menu callback `data` not validated against expected format | Malformed `callback.data` crashes handler or causes unexpected routing | Validate `callback.data` with strict regex or Enum; reject unknown patterns with `await callback.answer()` |
| CRM tools enabled for all users when `kommo_enabled=True` (bot.py:694-702) | Client-facing users can invoke CRM write tools | Gate CRM tools on `role == "manager"` check (already implemented) — ensure role resolution is not bypassable via user_service failure fallback |

---

## UX Pitfalls

| Pitfall | User Impact | Better Approach |
|---------|-------------|-----------------|
| HITL confirmation has no timeout | User clicks "Confirm" 10 minutes later; operation is stale but executes | Set 5-minute TTL on HITL pending state; show "confirmation expired, please retry" on timeout |
| HITL confirmation shows raw parameter dict | Manager sees `{"lead_id": 42, "name": "...", "budget": 50000}` — not human-readable | Format preview as natural language: "Update deal #42 (Ivan Petrov) — change budget to 50,000 EUR?" |
| Menu dialog and free-text agent run in parallel | User in menu sends text → agent responds → menu state is orphaned | Detect active dialog before routing to agent; menu dialog should always take priority over free-text |
| Streaming response + HITL interrupt | Stream starts, then agent decides to call write tool → interrupt pauses mid-stream | Disable streaming for tool-heavy (CRM) queries, or flush stream before interrupt |
| Feedback buttons appear on CRM-only responses (non-RAG) | User sees like/dislike buttons after "Deal created" response | Only show feedback buttons when `query_type not in {"CHITCHAT", "OFF_TOPIC"}` AND `rag_search` was called — already partially implemented in bot.py:769 |

---

## "Looks Done But Isn't" Checklist

- [ ] **Pipeline refactor**: `write_langfuse_scores()` is called with a result dict that contains all 14 expected keys — verify with a unit test asserting key presence.
- [ ] **Guard on text path**: `detect_injection(message.text)` is called BEFORE `agent.ainvoke()`, not inside the pipeline — verify with a test that sends injection text via `handle_query` and checks it is blocked.
- [ ] **HITL flow**: Confirmation callback validates `user_id` ownership of `trace_id` before resuming — verify with a test that tries to confirm another user's pending operation.
- [ ] **HITL flow**: State survives a bot restart (or is stateless by design) — verify by simulating restart between interrupt and confirm.
- [ ] **Semantic cache fix**: Two identical user queries in the text path produce a cache hit on the second call — verify with integration test counting `cache_hit` scores in Langfuse or asserting `cache_hit=True` in result.
- [ ] **aiogram-dialog**: User mid-dialog sending free text is routed to dialog handler, not agent — verify with unit test simulating active dialog context.
- [ ] **APScheduler version pin**: `pyproject.toml` has `apscheduler>=3.10,<4` — check before any Renovate batch merge.
- [ ] **Kommo OAuth2 race**: `asyncio.gather(store.get_valid_token(), store.get_valid_token())` with expired token calls `force_refresh` exactly once — verify with concurrent test.
- [ ] **E2E tests**: Bot E2E test does not conflict with polling mode — test runs against mocked Telegram HTTP layer or uses webhook injection.

---

## Recovery Strategies

| Pitfall | Recovery Cost | Recovery Steps |
|---------|---------------|----------------|
| Guard bypass exploited (injection in text path) | HIGH | 1. Deploy `detect_injection` pre-check immediately; 2. Rotate system prompt; 3. Audit Langfuse traces for injection patterns; 4. Add guard to ALL input handlers |
| HITL state lost (MemorySaver + restart) | LOW | Users just need to re-initiate the operation; show friendly "session expired, please try again" message |
| Pipeline refactor breaks Langfuse scores | MEDIUM | 1. Identify missing keys via Langfuse dashboard (score count drops); 2. Add missing key to result dict; 3. Redeploy |
| Kommo token refresh race causes 401 storm | MEDIUM | 1. Add `asyncio.Lock`; 2. Rotate Kommo credentials if refresh_token was permanently invalidated; 3. Re-run `initialize(authorization_code=...)` |
| APScheduler upgraded to v4 accidentally | MEDIUM | Pin version in `pyproject.toml`; revert to v3.x; schedule migration separately |
| Semantic cache never hits | LOW (silent) | Add `original_query` to BotContext and use as cache key; deploy; cache population recovers naturally |
| aiogram-dialog and agent conflict | MEDIUM | Add dialog-state check at top of `handle_query`; test with active dialog sessions |

---

## Pitfall-to-Phase Mapping

| Pitfall | Prevention Phase | Verification |
|---------|------------------|--------------|
| Guard bypass on text path (issue #439) | Phase 1 (pipeline refactor) | Unit test: injection text → `_handle_query_supervisor` → assert response is blocked, `agent.ainvoke` never called |
| Pipeline refactor loses observability | Phase 1 (pipeline refactor) | Test: assert result dict keys; assert 14 Langfuse scores written; RAGAS eval >= 0.8 |
| Semantic cache broken by reformulation (issue #430) | Phase 1 (pipeline refactor) | Integration test: two identical queries → assert `cache_hit=True` on second |
| aiogram-dialog vs agent handler conflict | Phase 1 (menu skeleton, issue #447) | Unit test: active dialog + free-text → dialog handler responds, not agent |
| HITL persistence (MemorySaver) | Phase 2 (HITL implementation, issue #443) | Test: interrupt → simulate restart → confirm → assert stateless recovery OR state survives |
| HITL callback user_id validation | Phase 2 (HITL implementation, issue #443) | Test: forge confirm callback with wrong user_id → assert rejected |
| Kommo OAuth2 race condition | Phase 2 (CRM expansion, issue #443) | Concurrency test: parallel `get_valid_token` with expired token → `force_refresh` called once |
| APScheduler v4 breakage | Any phase touching nurturing | Check: `pyproject.toml` pin exists before any Renovate merge touching scheduler deps |
| E2E test isolation (Telegram polling conflict) | Phase 5 (E2E tests, issue #446) | Verify test uses HTTP mock layer, not live polling; no `getUpdates` conflict |

---

## Sources

- **Issue #439** — Guard bypass audit (3 critical gaps confirmed in production codebase)
- **Issue #430** — Semantic cache broken by agent reformulation (confirmed root cause)
- **Issue #428** — Streaming coordination broken (`response_sent` flag removed in #413)
- **Issue #443** — HITL design spec (Phase 2 plan)
- **Issue #420** — MemorySaver chosen due to redisvl JSON serialization failure (tracked reason)
- **LangGraph docs** — `interrupt()` requires persistent checkpointer, suspends at node level, resumes via `Command(resume=...)`
- **LangGraph GitHub #6241** — `InjectedState` vs `InjectedConfig` tool parameter handling edge cases
- **APScheduler migration docs** — confirmed v3→v4 is a breaking rewrite with no auto-migration
- **Kommo developer docs** — long-lived tokens available for single-account integrations (no refresh needed)
- **OAuth2 race condition (oauth2-proxy #1992, SO discussion)** — confirmed pattern: parallel refresh requests with single-use refresh tokens cause failures; fix is locking
- **aiogram-dialog PyPI v2.4.0** — handler registration order matters; `setup_dialogs()` registers middleware that intercepts updates for active dialog sessions
- **Codebase audit** — `bot.py`, `agents/agent.py`, `graph/graph.py`, `services/kommo_token_store.py`, `agents/rag_tool.py`

---
*Pitfalls research for: Production RAG + CRM Telegram bot (refactoring + feature expansion milestone)*
*Researched: 2026-02-19*

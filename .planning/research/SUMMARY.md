# Project Research Summary

**Project:** Production RAG + CRM Telegram Bot — Milestone Feature Expansion
**Domain:** Real estate assistant bot with hybrid RAG pipeline and CRM integration
**Researched:** 2026-02-19
**Confidence:** HIGH

## Executive Summary

This is a subsequent milestone on a production system that already ships hybrid RAG search (BGE-M3 + RRF + ColBERT), 8 CRM tools against Kommo API, voice STT via Whisper, and Langfuse observability with 35 observations per trace. The milestone targets six open issues: guard coverage gaps (#439), async pipeline simplification (#442), CRM test coverage (#441), menu system expansion (#447), HITL confirmation for write operations (#443), and i18n system prompt support (#444). All research confirms that the existing stack is the correct foundation — the only new dependency is `respx 0.22.0` for CRM test mocking; everything else is already in the codebase.

The recommended approach is a five-phase sequential delivery ordered by dependency graph. Pipeline refactor (#442) is the critical-path blocker because it is where the guard text-path fix (#439), the broken semantic cache (#430), and the new async pipeline function all converge. Guard fix and history sub-graph guard (#432) can run as parallel tracks since they share no code changes. Menu skeleton (#447) can proceed in parallel with the pipeline work because the navigation structure is independent of the pipeline internals. HITL confirmation (#443) unblocks after both menu and pipeline are stable, because it requires both the dialog FSM state machine and the new pipeline's async function surface.

The highest-risk area is HITL state persistence: the current `MemorySaver` checkpointer (chosen because redisvl JSON serialization fails for LangChain Message objects — issue #420) will silently lose HITL confirmation state on any bot restart. The architecture research is unambiguous on this: the correct approach is a stateless HITL pattern where pending CRM actions are stored in Redis TTL keys rather than in LangGraph checkpoint state. This avoids the serialization bug, survives restarts, and matches the existing `feedback.py` keyboard pattern. A second high-risk area is the security gap in #439: three independent bypass vectors exist on the text path in production right now, and the guard fix must ship before or alongside the pipeline refactor, not after it.

---

## Key Findings

### Recommended Stack

The stack is stable. All six issues are solvable without adding frameworks or switching providers. The only tooling addition is `respx 0.22.0` as a dev dependency — it provides route-based `httpx` mocking better suited to class-wrapped clients like `KommoClient` than the existing `patch.object` approach. LangGraph 1.0.3 `interrupt()` + `Command(resume=...)` is the 2025-2026 standard HITL primitive, but its use requires a persistent checkpointer, which creates the MemorySaver trap described above. `aiogram-dialog 2.4.0` (already in stack) is the correct and only abstraction for multi-step menus and HITL sub-dialogs. `fluentogram 1.2.1` (already in stack) handles i18n; no migration to `aiogram-i18n` is warranted since the project already uses Fluent exclusively.

**Core technologies (existing — no changes):**
- `langgraph 1.0.3`: RAG pipeline + HITL interrupt primitive — stable 1.0 API, do not upgrade past `<2.0`
- `aiogram-dialog 2.4.0`: FSM menus, funnel, HITL confirm sub-dialogs — v2.x series is aiogram 3.x compatible
- `fluentogram 1.2.1`: Fluent (.ftl) i18n with type-safe stubs — already wired, no migration needed
- `telethon >=1.42.0`: E2E tests via MTProto StringSession in CI — already in dev deps
- `APScheduler >=3.10,<4`: Nurturing scheduler — must stay pinned below v4 (breaking API rewrite)

**New addition (dev only):**
- `respx 0.22.0`: Route-based httpx mock for KommoClient unit tests — cleaner than `patch.object` on `_client.request`

**What not to use:**
- `llm-guard` DeBERTa on the hot path: 100-200ms CPU latency kills UX; keep opt-in via `GUARD_ML_ENABLED`
- LangGraph `interrupt()` with MemorySaver for HITL: state lost on restart; use stateless Redis TTL pattern
- APScheduler v4: completely different API, would break `NurturingScheduler` silently

### Expected Features

The milestone is defined by the six open issues. Research cross-references them against a feature dependency graph that determines build order.

**Must have (table stakes for this milestone):**
- Guard on text path (#439, P0) — three bypass vectors confirmed in production; security gap ships with every deploy until fixed
- Role-based menu expansion to 9+9 buttons (#447) — skeleton exists with 3 buttons; users expect full navigation
- HITL confirmation for write CRM operations (#443) — standard UX for any bot that modifies CRM data
- BANT funnel wired to RAG and CRM (#447 + existing funnel.py) — funnel steps exist but results window is a placeholder
- i18n system prompt per locale (#444) — dialogs already have i18n getters; LLM still replies in hardcoded RU

**Should have (differentiators this milestone):**
- `mortgage_calculator` tool (#445) — universal real estate feature, pure math, no external API
- Manager daily summary (#445) — LLM-synthesized CRM digest, high manager UX value
- `handoff_to_manager` tool (#445) — safety net when bot cannot help; sends notification to manager
- `SessionSummaryWorker` background job (#445) — auto-summarize idle sessions to Kommo notes
- CRM test coverage (#441) — `respx` fixtures for all 8 tools; currently only partial coverage

**Defer to v1.x (after milestone validation):**
- Property catalog with `rag_search(scope=..., filters=...)` — medium complexity, requires RAG pipeline scope routing
- CRM submenu inline keyboard on deal/contact cards — depends on stable #447 menu
- Follow-up inline buttons in nurturing sequence — depends on NurturingDispatch wiring

**Defer to v2+ (future consideration):**
- Nurturing dispatch from Qdrant preferences — infrastructure exists, dispatch mechanism is HIGH complexity
- Per-locale Langfuse prompt variants with A/B testing
- Voice-triggered menu (low priority; voice already has a clean independent path)

**Anti-features (deliberately not build):**
- Full inline CRM field editor — duplicates Kommo web UI; state explosion; HITL confirm is sufficient
- Real-time manager live chat passthrough — two-way websocket relay is an architecture anti-pattern; use handoff notification
- Multi-step HITL edits — binary confirm/cancel is correct; complex edits belong in Kommo

### Architecture Approach

The existing architecture is the correct one. Three layers interact: the aiogram dispatcher routes to either dialog FSM handlers (when a user has active `StatesGroup` state) or free-text handlers (`handle_query`, `handle_voice`). Free-text handlers call `create_bot_agent` which routes via LLM tool choice to `rag_search`, `history_search`, or CRM `@tool` functions. The RAG pipeline (#442 target) simplifies from an 11-node LangGraph `StateGraph` to a 6-step plain async function for the text path, while the voice path keeps the full LangGraph graph (transcription requires graph state). The critical architectural invariant is that dialogs and the agent are separate state machines — dialog collects structured input and hands off via `dialog_manager.done()` → data persisted → agent reads from BotContext on next free-text turn.

**Major components:**
1. `PropertyBot` (bot.py) — lifecycle, handler registration, service DI; all dialog routers registered before `setup_dialogs(dp)`
2. `create_bot_agent` (agents/agent.py) — LLM routing via tool choice; BotContext DI container passes all services without per-call instantiation
3. `rag_pipeline()` (new, agents/rag_pipeline.py) — 6-step async: guard → cache → retrieve → grade → rerank → generate; replaces `build_graph().ainvoke()` for text path
4. Dialog FSM (dialogs/) — `ClientMenuSG`, `ManagerMenuSG`, `FunnelSG`, `SettingsSG`, `FaqSG`, `HITLConfirmSG` (new)
5. CRM `@tools` (agents/crm_tools.py) — 8 tools + 4 new (#443); HITL via inline keyboard + Redis TTL, not LangGraph interrupt
6. Guard node (graph/nodes/guard.py) — shared implementation called at step 0 of `rag_pipeline()`, at history sub-graph START, and before `agent.ainvoke()` in `bot.py`

**Key patterns:**
- BotContext DI: services populated once per request in `handle_query`, never instantiated inside tools
- HITL: stateless inline keyboard pattern (mirrors `feedback.py`); pending action stored in Redis TTL key; no MemorySaver dependency
- Registration order: dialog routers → `setup_dialogs(dp)` → free-text handler; free-text handler checks for active dialog state before routing to agent
- Observability preservation: `rag_pipeline()` must emit result dict with same key schema as current `RAGState` fields read by `write_langfuse_scores()`

### Critical Pitfalls

1. **Guard bypass on text path (issue #439)** — `detect_injection(message.text)` must be called BEFORE `agent.ainvoke()` in `_handle_query_supervisor`, not inside the pipeline. Guard must also check `original_user_query`, not the agent-reformulated string. Fix in Phase 1 before any other new code ships.

2. **HITL state lost on restart (MemorySaver + issue #420)** — Do not use `interrupt()` with `MemorySaver` for HITL. Use stateless pattern: CRM write tools send inline keyboard, store `{action_id → {tool_name, args, user_id}}` in Redis with 5-minute TTL, callback handler reads Redis and executes directly. Validate `user_id` ownership to prevent HITL forgery attacks.

3. **Pipeline refactor silently drops observability** — `rag_pipeline()` must return a result dict with identical keys to current `RAGState` fields consumed by `write_langfuse_scores()`. Build a unit test asserting key presence (`cache_hit`, `rerank_applied`, `grade_confidence`, `latency_stages`, `search_results_count`) BEFORE writing the new pipeline. Run RAGAS eval after refactor to verify faithfulness >= 0.8.

4. **Semantic cache never hits (issue #430)** — Agent LLM reformulates queries before calling `rag_search`, so the semantic cache key (based on embedding of the tool-call query string) never matches the original question. Fix: store `original_user_query` in `BotContext` at the `message.text` read point in `bot.py`; use it as the cache lookup key in `rag_pipeline()`.

5. **aiogram-dialog vs agent handler conflict** — `dp.message(F.text)(self.handle_query)` must not intercept messages for users with active dialog FSM state. Add `dialog_manager.has_context()` check at the top of `handle_query` or register `handle_query` after `setup_dialogs(dp)`. Test with a user mid-dialog sending free text.

6. **Kommo OAuth2 race condition** — Parallel CRM tool calls trigger concurrent `force_refresh()`, consuming the single-use refresh token twice. Fix: add `asyncio.Lock` per subdomain in `KommoTokenStore.__init__`. Test with `asyncio.gather(store.get_valid_token(), store.get_valid_token())` and expired token — `force_refresh` must be called exactly once.

---

## Implications for Roadmap

Based on the dependency graph from FEATURES.md and the build order from ARCHITECTURE.md, five phases are suggested. Guard fix runs as Phase 0 because it closes a confirmed production security gap and is independent of all other work.

### Phase 0: Guard Fix (Issue #439)
**Rationale:** Three confirmed bypass vectors exist in production right now. This is a security fix, not a feature — it must ship before or concurrently with Phase 1. Independent of all other issues. Two-hour change in `bot.py` + `agents/agent.py`.
**Delivers:** `detect_injection()` before `agent.ainvoke()` on text path; `original_user_query` stored in BotContext; safety instructions in `DEFAULT_SYSTEM_PROMPT`; history sub-graph guard node (#432).
**Addresses:** Guard bypass pitfall, semantic cache reformulation fix (same BotContext field)
**Avoids:** Prompt injection attacks, guard-after-reformulation bypass

### Phase 1: Pipeline Refactor + Test Infrastructure (Issues #442, #441)
**Rationale:** `rag_pipeline()` is the critical-path blocker for HITL, funnel-to-RAG wiring, and E2E tests. CRM test coverage (#441) is best done alongside pipeline work because `respx` fixtures establish the test infrastructure pattern used in all subsequent phases.
**Delivers:** `agents/rag_pipeline.py` (6-step async, guard at step 0); `respx` fixtures for all 8 CRM tools; result dict schema tests; RAGAS eval passing >= 0.8
**Uses:** `respx 0.22.0` (new dev dep), existing LangGraph graph (voice path unchanged)
**Implements:** `rag_pipeline()` async function, result dict with 14 Langfuse score keys preserved
**Avoids:** Observability loss pitfall (#3), semantic cache broken pitfall (#4)

### Phase 2: HITL Confirmation + 4 New CRM Tools (Issues #443, #441 extension)
**Rationale:** HITL must come before menu expansion because manager menu buttons 4 and 6 call write tools that require confirmation. CRM tool additions (`crm_search_leads`, `crm_get_my_leads`, `crm_get_my_tasks`, `crm_update_contact`) are grouped here because they share the HITL pattern and `respx` test infrastructure from Phase 1.
**Delivers:** `hitl_confirm.py` (inline keyboard + Redis TTL pattern); 4 new CRM tools; `HITLConfirmSG` dialog state; HITL callback handler in `bot.py`; HITL forgery protection (user_id validation)
**Uses:** Existing `feedback.py` as model; Redis TTL keys (no MemorySaver HITL)
**Implements:** Stateless HITL pattern; BotContext `bot` field addition; `hitl:ok:{action_id}` / `hitl:cancel:{action_id}` callback data format
**Avoids:** HITL persistence pitfall (#2), Kommo OAuth2 race condition pitfall (#6)

### Phase 3: Menu Expansion + i18n System Prompt (Issues #447, #444)
**Rationale:** Menu expansion requires HITL to be stable (write buttons need HITL tools). i18n system prompt is bundled here because menu button text and LLM system prompt localization are user-visible at the same time — shipping them together avoids a "half-localized" experience.
**Delivers:** `ClientMenuSG` expanded to 9 buttons; `ManagerMenuSG` (new, 9 buttons); per-locale system prompts in Langfuse PM (`supervisor_agent_ru`, `supervisor_agent_uk`, `supervisor_agent_en`); BANT funnel wired to `rag_pipeline()` and `crm_create_lead`; `manager_menu.py` dialog
**Uses:** `aiogram-dialog 2.4.0`, `fluentogram 1.2.1`, existing Langfuse PM integration
**Implements:** Intent-to-agent routing (buttons generate text intents → same `agent.ainvoke()`); dialog-to-agent handoff via `dialog_manager.done()` + BotContext
**Avoids:** Dialog vs agent handler conflict pitfall (#5); dialog state pollution anti-pattern

### Phase 4: Additional Tools + Background Workers (Issue #445)
**Rationale:** Utility tools (mortgage calculator, daily summary, handoff) and background workers (SessionSummaryWorker) complete the feature set. They depend on the stable menu (menu buttons 5, 8) and HITL (daily summary confirmation) from Phase 3.
**Delivers:** `mortgage_calculator` tool (pure math, no external API); `daily_summary` tool (CRM digest via LLM); `handoff_to_manager` tool (Telegram notification); `SessionSummaryWorker` APScheduler job (30-min idle → `crm_add_note`)
**Uses:** APScheduler v3.x (pinned `<4`); existing `NurturingScheduler` as pattern
**Implements:** APScheduler `<4` version pin in `pyproject.toml`; session idle detection logic
**Avoids:** APScheduler v4 breakage pitfall (#7)

### Phase 5: E2E Tests + Epic Close (Issue #446)
**Rationale:** E2E tests validate the full integrated system. Dialog tests (aiogram-dialog `BotClient`), HITL callback simulation, and pipeline integration tests all require stable implementations from Phases 0-4.
**Delivers:** `tests/unit/agents/test_rag_pipeline.py`; extended HITL callback tests; dialog navigation tests; pipeline integration tests with mocked services; E2E menu navigation covering all 9+9 buttons and BANT funnel flow
**Uses:** Existing `pytest-asyncio`, mocked `agent.ainvoke()` pattern from `tests/unit/agents/`; aiogram-dialog `BotClient` test utility
**Avoids:** E2E test isolation pitfall (mocked HTTP layer, not live polling)

### Phase Ordering Rationale

- **Phase 0 before everything:** Three confirmed production security vulnerabilities that can be fixed independently in under a day. No excuse to defer.
- **Phase 1 before Phases 2-5:** `rag_pipeline()` is the call target for funnel RAG integration, the home of the cache key fix, and the surface for most unit tests. Building on top of an unrefactored pipeline adds technical debt to every subsequent phase.
- **Phase 2 before Phase 3:** Menu write buttons require HITL tools. Building menu expansion without working HITL means shipping non-functional buttons.
- **Phase 3 before Phase 4:** Utility tools (Phase 4) attach to menu buttons that Phase 3 creates. SessionSummaryWorker needs a stable agent invocation path.
- **Phase 5 last:** E2E tests validate the full stack. Writing them before the stack is stable produces tests that need constant updates.
- **Parallel tracks within Phase 1:** Guard fix and CRM test coverage do not block each other; they can be worked simultaneously by two developers.

### Research Flags

Phases likely needing deeper research during planning:
- **Phase 2 (HITL):** HITL state design has two viable approaches (stateless Redis TTL vs LangGraph interrupt with custom Redis checkpointer). The stateless approach is recommended but the custom checkpointer path is not fully explored. If issue #420 (redisvl serialization) is resolved, interrupt-based HITL becomes viable. Validate which approach is chosen before writing implementation.
- **Phase 3 (Funnel → CRM wiring):** The BANT funnel completion → `crm_create_lead` → lead scoring flow has not been fully designed. The `funnel.py` results window is a placeholder. This connection needs design decisions: does the funnel call `agent.ainvoke()` with a structured intent, or does it call `rag_pipeline()` + `crm_create_lead` directly?

Phases with standard patterns (skip research-phase):
- **Phase 0 (Guard fix):** Exact code locations and changes are documented in issue #439 and confirmed in PITFALLS.md. No research needed — just implement.
- **Phase 1 (Pipeline refactor):** `rag_pipeline()` function signature and step structure are fully specified in ARCHITECTURE.md. `respx` patterns are verified via Context7. Standard refactoring work.
- **Phase 4 (Tools + workers):** Mortgage calculator is pure math. `SessionSummaryWorker` mirrors existing `NurturingScheduler`. APScheduler v3 patterns are well-documented. No new research needed.
- **Phase 5 (E2E tests):** Mocked aiogram test pattern is already used in `tests/unit/agents/`. aiogram-dialog `BotClient` is documented. Extend existing patterns.

---

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Stack | HIGH | All claims verified via Context7 official docs + PyPI release dates. Only new dep (`respx 0.22.0`) is confirmed stable since Dec 2024. Existing stack is production-tested. |
| Features | HIGH | Issues #439-#447 are the authoritative source; codebase confirms current state of each feature. Competitor analysis is MEDIUM (generic sources) but does not affect core feature decisions. |
| Architecture | HIGH | All architecture claims grounded in actual codebase file reads (bot.py, agent.py, graph.py, dialogs/, etc.) + verified LangGraph and aiogram-dialog official docs. No speculative patterns. |
| Pitfalls | HIGH | Pitfalls 1-4 sourced from confirmed GitHub issues (#439, #430, #420, #428) with root causes in codebase. Pitfalls 5-7 sourced from official library docs and codebase audit. |

**Overall confidence:** HIGH

### Gaps to Address

- **HITL implementation choice:** Whether to use stateless Redis TTL HITL (recommended) or pursue fixing issue #420 to enable LangGraph interrupt-based HITL is a decision that affects Phase 2 complexity. Recommend deciding before Phase 2 planning starts and adding the chosen approach to the phase specification.
- **i18n Langfuse PM prompt slot naming:** Research confirms using `get_prompt("supervisor_agent_ru")` pattern, but actual prompt slot names in Langfuse must be verified against the production Langfuse instance. Affects Phase 3.
- **E2E test scope vs live Telegram API:** Research recommends mocked HTTP layer for E2E (not live `getUpdates`). Whether to add `telethon` StringSession E2E tests against a staging bot is a scope decision for Phase 5. Not blocking but should be decided early to avoid CI setup overhead.
- **APScheduler pin:** Must be confirmed in `pyproject.toml` before any Renovate batch merge that touches scheduler dependencies. Verify pin exists before Phase 4 starts.

---

## Sources

### Primary (HIGH confidence)
- Context7 `/websites/langchain_oss_python_langgraph` — interrupt(), Command(resume=), HITL patterns
- Context7 `/langchain-ai/langgraph` — StateGraph patterns, streaming
- Context7 `/websites/aiogram-dialog_readthedocs_io_en_stable` — Window widgets, FSM routing, setup_dialogs, sub-dialogs
- Context7 `/lundberg/respx` — pytest fixture patterns, async mock
- Context7 `/aiogram/aiogram` — FSMI18nMiddleware, handler registration order
- PyPI `aiogram-dialog 2.4.0` (Jul 2025), `fluentogram 1.2.1` (Jul 2025), `respx 0.22.0` (Dec 2024)
- GitHub issues #439, #430, #420, #428, #443, #447 — confirmed bugs and design specs
- Codebase: `telegram_bot/bot.py`, `agents/agent.py`, `agents/crm_tools.py`, `graph/nodes/guard.py`, `dialogs/`, `services/kommo_token_store.py`

### Secondary (MEDIUM confidence)
- LangGraph HITL production examples (2025 Medium series) — approve/reject pattern
- aiogram_i18n + Fluent production example (Habr) — i18n middleware wiring
- BANT chatbot qualification for real estate (AgentiveAIQ) — funnel feature expectations
- OAuth2 race condition documented patterns (oauth2-proxy #1992, SO) — concurrent refresh lock fix
- APScheduler v3→v4 migration docs — confirmed breaking API rewrite

### Tertiary (LOW confidence)
- Generic property bot designs (n8n RAG templates) — feature landscape baseline only; not used for decisions

---
*Research completed: 2026-02-19*
*Ready for roadmap: yes*

# ADR: Epic #2843 — Strip to 3 Core Surfaces

**Status:** Decided (Epic #2843)
**Date:** 2026-06-19
**Author:** Architecture Team
**Related:** #2043, #2048, #2791 (Voice/Mini App removal), Product Simplification Phase

---

## Problem Statement

The telegram_bot adapter has accumulated 10 active surfaces over ~2 years of development:

1. **Text RAG Chat** (PropertyBot.handle_query)
2. **Voice RAG** (PropertyBot.handle_voice)
3. **Apartment Filter Dialog** (aiogram-dialog, demo flow)
4. **Manager Reply / Forum Topics** (_handle_group_message, forum_bridge)
5. **Menu/Command handlers** (start, help, settings)
6. **Feedback callbacks** (handle_feedback, reason collection)
7. **Cache/Admin callbacks** (handle_clearcache_callback)
8. **Phone FSM** (phone_collector, lead qualification)
9. **Results/Favorites** (handle_results_callback, handle_fav_*)
10. **Deep Link / Mini App** (archived in #2791)

**Maintenance burden:** Each surface carries state machines, handler registration, routing logic, dialog wiring, callbacks, caching strategy, and trace instrumentation. This overhead blocks product simplification and makes refactoring (e.g., #2048 PropertyBot decomposition) slow and risky.

**Simplification goal:** Keep only the highest-ROI surfaces and delete dead code systematically.

---

## Proposed Decision

**Keep 3 core surfaces; delete the rest.**

### ✅ KEEP

#### Surface 1: **Text RAG Chat**
- **Entry:** `PropertyBot.handle_query()` (catch-all message handler)
- **Path:** Message → Supervisor graph (`_handle_query_supervisor`) OR deterministic client pipeline (`run_client_pipeline`)
- **Why:** Highest user value. Main interaction mode. Lowest maintenance cost (deterministic pipeline).
- **Files:**
  - `telegram_bot/bot.py`: handle_query, _handle_query_supervisor
  - `telegram_bot/pipelines/client.py`: run_client_pipeline (deterministic fast-path)
  - `telegram_bot/graph/`: LangGraph compatibility (redundant after simplification)
  - Handler registrations in `_register_handlers()` (lines 637–680)

#### Surface 2: **Apartment Filter Dialog** (text-only + voice input via demo dialog)
- **Entry:** `PropertyBot.handle_menu_button()` → dialog start, voice input in demo.py
- **Path:** Menu → aiogram-dialog flow (CatalogSG, FilterSG) → deterministic apartment extraction
- **Why:** Domain-specific workflow. Compact UI. Voice input from demo dialog (not separate voice handler).
- **Files:**
  - `telegram_bot/dialogs/demo.py`: MessageInput + on_voice_input (replaces handle_demo_search_voice)
  - `telegram_bot/dialogs/filter_dialog.py`: filter panel, Radio/SwitchTo widgets
  - `telegram_bot/dialogs/states.py`: CatalogSG, FilterSG
  - `telegram_bot/handlers/demo_handler.py`: trigger handlers (handle_demo_button, handle_demo_apartments)
  - `telegram_bot/keyboards/demo_keyboard.py`: demo menu inline keyboard

#### Surface 3: **Manager Reply** (forum topics relay)
- **Entry:** `PropertyBot._handle_group_message()` (F.chat.id == managers_group_id, with thread_id)
- **Path:** Group message → forum_bridge.relay_to_topic() OR topic creation via _topic_service
- **Why:** Critical for sales workflow. Enables manager feedback loop without code changes.
- **Files:**
  - `telegram_bot/services/forum_bridge.py`: relay_to_topic, create_topic
  - `telegram_bot/handlers/handoff.py`: handoff state, start_qualification, TopicService
  - Forum topic integration in `_handle_query_supervisor()` (expert_id resolution)

### ❌ DELETE

#### Surface 4: **Standalone Voice RAG**
- **Currently:** `PropertyBot.handle_voice()` registers message handler for F.voice messages
- **Rationale:**
  - Voice via dialog (demo.py MessageInput + Whisper) subsumes this.
  - Standalone voice creates duplicate state machines (RAGState graph).
  - Simplifies pipeline decision tree and handler registration.
- **Files to delete:**
  - `telegram_bot/bot.py`: handle_voice() method (lines ~3155–3384)
  - `telegram_bot/bot.py`: voice handler registration (lines ~650–654)
  - `telegram_bot/bot.py`: _write_voice_error_scores, voice-related observability helpers
  - `telegram_bot/graph/`: entire LangGraph module (compatibility facade, replaced by deterministic pipeline)
  - `telegram_bot/integrations/checkpointer.py`: voice checkpoint namespace logic
  - Test files: `tests/unit/telegram_bot/test_voice_*.py`, `tests/contract/test_voice_*.py`

#### Surface 5: **Command Handlers (start, help, settings)**
- **Currently:** `telegram_bot/handlers/command_handlers.py`, router.message decorators
- **Rationale:**
  - Limited user engagement. Settings forwarded to config, not user-driven.
  - Help/start can be static Telegram bot menu (BotCommand API).
  - Simplifies handler registration and FSM state machine.
- **Files to delete:**
  - `telegram_bot/handlers/command_handlers.py` (entire module)
  - Command handler registration in `_register_handlers()` (lines ~649–655)
  - Related callbacks (handle_start, handle_help, etc.)

#### Surface 6: **Feedback Collection**
- **Currently:** `handle_feedback()`, FeedbackCB, FeedbackReasonCB callbacks
- **Rationale:**
  - Duplicates response quality signals (Langfuse scores already captured).
  - Maintenance burden for UI copy, reason taxonomy, callback routing.
  - Low usage in practice.
- **Files to delete:**
  - `telegram_bot/bot.py`: handle_feedback, handle_feedback_reason methods
  - `telegram_bot/bot.py`: callback registration (lines ~674–676)
  - `telegram_bot/callback_data.py`: FeedbackCB, FeedbackReasonCB classes
  - `telegram_bot/feedback.py`: build_feedback_keyboard, etc.
  - `telegram_bot/_bot_feedback_handlers.py`: extracted module

#### Surface 7: **Cache/Admin Callbacks**
- **Currently:** `handle_clearcache_callback()`, handle_service_callback, handle_cta_callback
- **Rationale:**
  - Cache management should be admin API, not bot UI.
  - Service callbacks (hidden text links, svc: prefix) clutters message routing.
  - CTA callbacks are domain-specific (no standard re-use).
- **Files to delete:**
  - `telegram_bot/bot.py`: handle_clearcache_callback, handle_service_callback, handle_cta_callback
  - Callback registration (lines ~677–678)
  - Related keyboard builders (e.g., admin_keyboard.py references)

#### Surface 8: **Phone FSM**
- **Currently:** `telegram_bot/handlers/phone_collector.py`, create_phone_router()
- **Rationale:**
  - Qualification/lead capture should use apartment filter dialog or manager handoff.
  - Separate FSM duplicates state management.
  - Low adoption; apartment filter is primary apartment capture surface.
- **Files to delete:**
  - `telegram_bot/handlers/phone_collector.py` (entire module)
  - Router registration in `_register_handlers()` (lines ~639–641)
  - Related callback_data, keyboards, services

#### Surface 9: **Results/Favorites**
- **Currently:** handle_results_callback, handle_fav_add/remove/viewing/viewing_all, ResultsCB, FavoriteCB
- **Rationale:**
  - Apartment catalog view is secondary to the filter dialog.
  - Favorites persistence adds storage/sync complexity without clear ROI.
  - Can be replaced by simple message threading in Telegram.
- **Files to delete:**
  - `telegram_bot/bot.py`: all handle_fav_* and handle_results_callback methods
  - Callback registration (lines ~679–687)
  - `telegram_bot/callback_data.py`: ResultsCB, FavoriteCB classes
  - `telegram_bot/dialogs/catalog_transport.py (render_catalog_results_with_keyboard)`: build_results_keyboard, etc.

#### Surface 10: **Deep Link / Mini App** (already archived in #2791)
- **Status:** Already removed from codebase in #2791.
- **Residual cleanup:**
  - Remove `_deeplink_redis`, `_topic_manager` fields if still present in PropertyBot.__init__
  - Remove _handle_deeplink_start, _process_miniapp_start methods
  - Remove deep link references from start handler

---

## Impact Analysis

### Handler Registration Simplification

**Before:** 40+ handler decorators across 10 surfaces
**After:** ~8 handlers (query catch-all, voice from dialog, menu, group message, admin/debug)

### Dialog Router Wiring

**Remove:**
- command_router (command handlers)
- phone_router (phone FSM)
- **Keep:**
- demo_router (apartment filter dialog)

### Files to Delete

**Handlers (280 LOC estimated):**
- `telegram_bot/handlers/command_handlers.py` (~100 LOC)
- `telegram_bot/handlers/phone_collector.py` (~150 LOC)
- `telegram_bot/handlers/demo_handler.py` (partial — keep trigger handlers, delete search logic if moved to dialog)

**Bot.py methods (600+ LOC estimated):**
- handle_voice (~230 LOC)
- handle_feedback, handle_feedback_reason (~50 LOC)
- handle_clearcache_callback, handle_service_callback, handle_cta_callback (~80 LOC)
- handle_results_callback, handle_fav_* methods (~200+ LOC)
- _handle_deeplink_start, _process_miniapp_start (~100+ LOC)

**Keyboards (200+ LOC):**
- feedback_keyboard.py
- results_keyboard.py
- admin_keyboard.py (if only cache buttons)
- command_keyboard.py (if only inline command buttons)

**Callback data classes (100+ LOC):**
- FeedbackCB, FeedbackReasonCB
- ResultsCB, FavoriteCB
- CommandCB variations

**LangGraph module (removed in #2791, verify residual):**
- Ensure `telegram_bot/graph/` is either deleted or declared as compatibility-only facade

**Tests:**
- All test_*_callback.py files (feedback, results, favorites, cache, commands)
- All test_voice_*.py files
- Contract tests for deleted surfaces

### Retained Core Files

**Text RAG Chat:**
- `telegram_bot/pipelines/client.py` (deterministic pipeline) — 650+ LOC
- `telegram_bot/bot.py`: handle_query, _handle_query_supervisor methods
- `src/runtime/pipeline/assistant_pipeline.py`: core routing/classification

**Apartment Filter:**
- `telegram_bot/dialogs/demo.py`: demo flow with voice input
- `telegram_bot/dialogs/filter_dialog.py`: filter panel
- Demo handler triggers

**Manager Reply:**
- `telegram_bot/services/forum_bridge.py`
- `telegram_bot/handlers/handoff.py`
- Topic service integration

---

## Migration Path & Child Issues

### Phase 1: Prep & Artifact Storage (Issue #2848)
- [ ] Audit all deleted surfaces for observability/signal loss
- [ ] Export callback data, keyboard builders as gists/docs for re-use reference
- [ ] Ensure no database/Langfuse dependency on deleted signals (feedback reason, favorites FK, etc.)
- [ ] Update PropertyBot AGENTS.override.md to note deletion

### Phase 2: Voice & Command Handler Removal (Issue #2849)
- [ ] Delete handle_voice() method from PropertyBot
- [ ] Delete command_handlers.py and phone_collector.py
- [ ] Remove handler registration from _register_handlers()
- [ ] Verify voice input via demo.py dialog works end-to-end (test demo flow with voice)
- [ ] Update bot tests to remove voice-specific fixtures

### Phase 3: Callback Cleanup (Issue #2850)
- [ ] Delete callback_data classes (Feedback*, Results*, Favorite*, etc.)
- [ ] Delete keyboard builders
- [ ] Delete handle_* callback methods
- [ ] Remove callback registration from _register_handlers()
- [ ] Update bot tests

### Phase 4: LangGraph Deprecation
- [ ] Verify all text/voice queries use deterministic pipelines or assistant_core_adapter
- [ ] Mark `telegram_bot/graph/` as deprecated in README
- [ ] Plan removal after product simplification E2E is verified

### Phase 5: Test & Verification (Issue #2851)
- [ ] Update PropertyBot initialization tests
- [ ] Run full E2E on 3 kept surfaces (text RAG, apartment filter, manager reply)
- [ ] Verify handler registration order (no missed wire-up)
- [ ] Benchmark: handler table size, message dispatch latency

---

## Decisions Rationale

| Surface | Keep? | Rationale |
|---------|-------|-----------|
| Text RAG Chat | ✅ Yes | Highest user value, clean deterministic pipeline |
| Voice RAG | ❌ No | Replaced by demo dialog voice input; simplifies state |
| Apartment Filter | ✅ Yes | Core domain workflow, compact, well-structured |
| Manager Reply | ✅ Yes | Sales workflow prerequisite; forum topics are clean |
| Commands | ❌ No | Low engagement; bot menu API is cleaner |
| Feedback | ❌ No | Duplicates Langfuse scores; high maintenance/low signal |
| Cache Callbacks | ❌ No | Admin API is cleaner than bot UI |
| Phone FSM | ❌ No | Apartment filter + handoff subsume this |
| Results/Favorites | ❌ No | Secondary to filter; message threading is simpler |
| Mini App | ✅ Archived | Already removed in #2791 |

---

## Success Criteria

- [ ] PropertyBot handler registration under 10 handlers (was 40+)
- [ ] `telegram_bot/handlers/` reduced to 2 files (demo_handler, handoff)
- [ ] `telegram_bot/bot.py` under 3500 LOC (was ~4000+)
- [ ] All 3 kept surfaces E2E tested and passing
- [ ] Delete operations are non-destructive (no production fallout)
- [ ] Zero Langfuse score loss on kept surfaces

---

## Risks & Mitigations

| Risk | Mitigation |
|------|-----------|
| **Voice**: Users lose voice input | Dialog voice input subsumes; test E2E before deletion |
| **Commands**: Users lose /start handler | Telegram BotCommand API handles it cleanly |
| **Favorites**: Data loss if users relied on it | Audit feature usage; migrate persisted data to message threading if needed |
| **Phone FSM**: Leads lost if depended on separate flow | Apartment filter + qualification is primary; validate with sales |
| **Test breakage**: Tests rely on deleted surfaces | Update test fixtures; ensure no mock data leaks |
| **Regression**: Unknown dead code removal | Comprehensive E2E before merge; monitor production for 48h |

---

## References

- **Product Simplification:** `docs/designs/product-simplification-e2e-plan.md`
- **Voice/Mini App Removal:** #2791, `docs/designs/product-simplification-e2e-plan.md`
- **PropertyBot Decomposition:** #2048, #2046, #1265
- **Deterministic Pipeline:** `telegram_bot/pipelines/client.py`, `src/runtime/pipeline/assistant_pipeline.py`
- **Demo Dialog:** `telegram_bot/dialogs/demo.py`, `telegram_bot/dialogs/filter_dialog.py`
- **Manager Handoff:** `telegram_bot/services/forum_bridge.py`, `telegram_bot/handlers/handoff.py`

---

## Approval & Timeline

- **Approved:** Epic #2843 scope decision
- **Target:** Complete by end of Q2 2026
- **Blocking:** Product E2E verification (#2043)
- **Blocked by:** None (parallel with simplification phase)

---

## Child Issues

1. **#2848:** Artifact storage — export callback data/keyboards as reference gists before deletion
2. **#2849:** Delete voice + command handlers, verify demo dialog voice works
3. **#2850:** Delete callback surfaces (feedback, cache, results, favorites)
4. **#2851:** Full E2E test on 3 kept surfaces; handler registration audit
5. **#2852:** LangGraph deprecation plan (mark as compatibility, no current deletion)

---

**END ADR**

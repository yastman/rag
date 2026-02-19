# Roadmap: Contextual RAG Pipeline — Milestone Feature Expansion

## Overview

This milestone delivers six open issues against a production RAG bot: guard coverage
gaps (#439, #432), async pipeline simplification (#442), CRM test coverage (#441),
menu system expansion (#447), HITL confirmation for write operations (#443), and i18n
system prompt support (#444). The critical path runs through the pipeline refactor —
it is where the guard fix, semantic cache fix, and new async surface all converge.
HITL confirmation unblocks menu write buttons. Tools and background workers complete
the feature surface. E2E tests close the epic.

## Phases

- [ ] **Phase 1: Security + Pipeline Foundation** - Guard fixes and pipeline refactor ship together; test infrastructure added
- [ ] **Phase 2: Observability + Test Coverage** - CRM scores, feedback bugs, and CRM tool test coverage
- [ ] **Phase 3: Menu System** - Full client/manager dialog navigation wired to agent
- [ ] **Phase 4: HITL + CRM Extended** - Confirmation flow for write operations and i18n system prompts
- [ ] **Phase 5: New Tools + Background Workers** - Mortgage calculator, daily summary, handoff, session summarizer
- [ ] **Phase 6: E2E Tests + Epic Close** - Full integration tests, cleanup, epic #403 acceptance criteria

## Phase Details

### Phase 1: Security + Pipeline Foundation
**Goal**: Guard vulnerabilities closed in production and pipeline refactored to async tool; no security regressions and no observability loss
**Depends on**: Nothing (first phase)
**Requirements**: SEC-01, SEC-02, SEC-03, SEC-04, PIPE-01, PIPE-02, PIPE-03, PIPE-04, TEST-03, TEST-04
**Success Criteria** (what must be TRUE):
  1. A prompt injection attempt on the text path is blocked before `agent.ainvoke()` executes
  2. A prompt injection attempt on the history sub-graph is blocked at sub-graph entry
  3. CRM tool calls with missing/invalid user_id or lead_id are rejected before hitting the Kommo API
  4. RAG text-path queries return the same answers and Langfuse scores after the pipeline refactor (same inputs, same outputs in regression tests)
  5. Voice path and RAG API continue to use the legacy LangGraph graph without modification
**Plans**: TBD

### Phase 2: Observability + Test Coverage
**Goal**: CRM tool usage is fully observable in Langfuse and all known score/feedback bugs are fixed; CRM tool test coverage is comprehensive
**Depends on**: Phase 1
**Requirements**: OBS-01, OBS-02, OBS-03, TEST-01, TEST-02
**Success Criteria** (what must be TRUE):
  1. Langfuse traces for agent runs show 4 CRM-specific scores (tool_called, tool_success, crm_write_confirmed, crm_error_rate)
  2. `tool_calls_total` score is present and correctly incremented on every agent trace that calls a CRM tool
  3. history_search responses have feedback buttons attached and functional
  4. All 8 CRM tools have unit tests covering happy path and error paths (429, 401, 5xx) using respx fixtures
**Plans**: TBD

### Phase 3: Menu System
**Goal**: Clients and managers can navigate a full-featured Telegram menu that coexists with free-text agent routing
**Depends on**: Phase 1
**Requirements**: MENU-01, MENU-02, MENU-03, MENU-04
**Success Criteria** (what must be TRUE):
  1. Client dialog shows property search, FAQ, and contact options; client can navigate to any option and return to root
  2. Manager dialog shows CRM tools, hot leads, and analytics options; manager can navigate to any option
  3. SwitchTo, Back, and Cancel navigation works for all dialog states via aiogram-dialog
  4. A user mid-dialog sending free text is not intercepted by the agent handler (FSM state separation intact)
**Plans**: TBD

### Phase 4: HITL + CRM Extended + i18n
**Goal**: Managers must confirm destructive CRM actions before they execute; bot responds in the user's detected language; OAuth2 race condition is closed
**Depends on**: Phase 3
**Requirements**: CRM-01, CRM-02, CRM-03, CRM-04, I18N-01, I18N-02, I18N-03
**Success Criteria** (what must be TRUE):
  1. When a CRM write tool (create or update lead) is triggered, the bot sends an inline confirmation keyboard and does not execute until the manager confirms
  2. Pending HITL confirmation survives a bot restart (stored in Redis TTL keys, not LangGraph state)
  3. Concurrent Kommo token refreshes do not consume the single-use refresh token twice (asyncio.Lock applied)
  4. Agent replies in the language of the incoming user message (ru/en/bg) without manual configuration
  5. Menu items expand to 9 client + 9 manager items with localized labels in .ftl files
**Plans**: TBD

### Phase 5: New Tools + Background Workers
**Goal**: Agents can perform mortgage calculations, deliver manager daily summaries, and escalate to human; sessions are automatically summarized to CRM
**Depends on**: Phase 4
**Requirements**: TOOL-01, TOOL-02, TOOL-03, TOOL-04
**Success Criteria** (what must be TRUE):
  1. Agent correctly calculates monthly mortgage payment given price, down payment, rate, and term (pure math, no external API)
  2. Manager can request a daily summary and receive a structured digest of today's leads and pending actions
  3. When the bot cannot help a client, handoff to manager sends a Telegram notification to the configured manager
  4. After 30 minutes of session inactivity, a background worker automatically summarizes the session to a Kommo note
**Plans**: TBD

### Phase 6: E2E Tests + Epic Close
**Goal**: Full bot flow is validated under CI mocks; dead pre-#413 code is removed; all epic #403 acceptance criteria are verified
**Depends on**: Phase 5
**Requirements**: E2E-01, E2E-02, E2E-03, E2E-04
**Success Criteria** (what must be TRUE):
  1. CI runs a full bot flow (message in → agent routing → RAG response or CRM action → reply out) using mocked HTTP and Telegram API without live services
  2. All code paths and files from the pre-#413 architecture (supervisor graph, legacy handlers) are removed and tests still pass
  3. All acceptance criteria listed in epic #403 are verified and the epic is closed
**Plans**: TBD

## Progress

**Execution Order:**
Phases execute in numeric order: 1 → 2 → 3 → 4 → 5 → 6

Note: Phase 2 and Phase 3 have no dependency between them — they can proceed in parallel
if two agents are available.

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Security + Pipeline Foundation | 0/TBD | Not started | - |
| 2. Observability + Test Coverage | 0/TBD | Not started | - |
| 3. Menu System | 0/TBD | Not started | - |
| 4. HITL + CRM Extended + i18n | 0/TBD | Not started | - |
| 5. New Tools + Background Workers | 0/TBD | Not started | - |
| 6. E2E Tests + Epic Close | 0/TBD | Not started | - |

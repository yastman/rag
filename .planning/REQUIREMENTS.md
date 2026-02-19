***REMOVED*** Requirements: Contextual RAG Pipeline

**Defined:** 2026-02-19
**Core Value:** Клиент задаёт вопрос → получает точный ответ из базы знаний с автоматической CRM-воронкой

***REMOVED******REMOVED*** v1 Requirements

***REMOVED******REMOVED******REMOVED*** Security

- [ ] **SEC-01**: Guard node фильтрует toxicity и injection на text path (fix ***REMOVED***439)
- [ ] **SEC-02**: Guard node фильтрует injection на history_search sub-graph (***REMOVED***432)
- [ ] **SEC-03**: CRM tool input validation — проверка user_id, lead_id перед Kommo API calls
- [ ] **SEC-04**: Guard safety instructions в system prompt агента (defense-in-depth)

***REMOVED******REMOVED******REMOVED*** Pipeline

- [ ] **PIPE-01**: RAG pipeline refactored: 11-node graph → 6-step async tool (***REMOVED***442)
- [ ] **PIPE-02**: Existing Langfuse scores preserved after pipeline refactor (no regression)
- [ ] **PIPE-03**: Voice path and RAG API continue using legacy graph (backward compat)
- [ ] **PIPE-04**: Semantic cache uses original user query, not agent-reformulated (***REMOVED***430 fix)

***REMOVED******REMOVED******REMOVED*** Observability

- [ ] **OBS-01**: 4 new CRM-specific Langfuse scores for agent tool usage (***REMOVED***440)
- [ ] **OBS-02**: tool_calls_total score correctly written from agent invocation (***REMOVED***437 fix)
- [ ] **OBS-03**: Feedback buttons attached to history_search responses (***REMOVED***434 fix)

***REMOVED******REMOVED******REMOVED*** Testing

- [ ] **TEST-01**: CRM tools test coverage: all 8 tools + error paths (429, 401, 5xx) (***REMOVED***441)
- [ ] **TEST-02**: respx dev dependency for KommoClient httpx mocking
- [ ] **TEST-03**: Guard node integration tests: text + voice + history all trigger guard
- [ ] **TEST-04**: Pipeline refactor regression tests: same inputs → same outputs

***REMOVED******REMOVED******REMOVED*** Menu

- [ ] **MENU-01**: Menu skeleton: client dialog (property search, FAQ, contact) (***REMOVED***447)
- [ ] **MENU-02**: Menu skeleton: manager dialog (CRM tools, hot leads, analytics) (***REMOVED***447)
- [ ] **MENU-03**: Menu navigation: SwitchTo/Back/Cancel via aiogram-dialog (***REMOVED***447)
- [ ] **MENU-04**: Menu coexists with free-text agent routing (FSM state separation)

***REMOVED******REMOVED******REMOVED*** CRM Extended

- [ ] **CRM-01**: HITL confirmation flow for destructive CRM actions (create/update lead) (***REMOVED***443)
- [ ] **CRM-02**: HITL uses stateless Redis TTL keys (not LangGraph interrupt) (***REMOVED***443)
- [ ] **CRM-03**: Kommo OAuth2 race condition fix (asyncio.Lock in token refresh)
- [ ] **CRM-04**: Extended CRM tools: manager-facing search, bulk ops (***REMOVED***443)

***REMOVED******REMOVED******REMOVED*** i18n

- [ ] **I18N-01**: i18n system prompt: agent responds in user's language (***REMOVED***444)
- [ ] **I18N-02**: Menu expansion: client 9 + manager 9 menu items (***REMOVED***444)
- [ ] **I18N-03**: Fluent .ftl files for ru/en/bg bot UI strings (***REMOVED***444)

***REMOVED******REMOVED******REMOVED*** New Tools

- [ ] **TOOL-01**: Mortgage calculator tool (property-specific) (***REMOVED***445)
- [ ] **TOOL-02**: Daily summary tool (manager: today's leads, actions) (***REMOVED***445)
- [ ] **TOOL-03**: Handoff tool: escalate to human manager (***REMOVED***445)
- [ ] **TOOL-04**: Background workers for scheduled summaries (***REMOVED***445)

***REMOVED******REMOVED******REMOVED*** E2E & Epic

- [ ] **E2E-01**: E2E runtime gate: CI mocks for full bot flow (***REMOVED***406)
- [ ] **E2E-02**: Live Telethon smoke test (optional, nightly) (***REMOVED***406)
- [ ] **E2E-03**: Cleanup: remove dead files from pre-***REMOVED***413 architecture (***REMOVED***438)
- [ ] **E2E-04**: Close epic ***REMOVED***403: all acceptance criteria verified

***REMOVED******REMOVED*** v2 Requirements

***REMOVED******REMOVED******REMOVED*** Enhanced RAG

- **ERAG-01**: Multimodal RAG for images and tables (***REMOVED***379)
- **ERAG-02**: GraphRAG with Neo4j knowledge graph (***REMOVED***377)
- **ERAG-03**: Online LLM-as-a-Judge restored (***REMOVED***427)

***REMOVED******REMOVED******REMOVED*** Security Advanced

- **SECA-01**: Automated red teaming with DeepTeam (***REMOVED***378)
- **SECA-02**: Presidio PII protection integration (***REMOVED***376)
- **SECA-03**: Comprehensive PII masking on Pydantic model fields

***REMOVED******REMOVED******REMOVED*** Infrastructure

- **INFR-01**: APScheduler v3 → v4 migration
- **INFR-02**: MLflow integration with real pipeline metrics
- **INFR-03**: Database pool timeout enforcement
- **INFR-04**: Semantic cache with bounded MemorySaver retention (***REMOVED***424)
- **INFR-05**: Streaming coordination fix (***REMOVED***428)

***REMOVED******REMOVED*** Out of Scope

| Feature | Reason |
|---------|--------|
| Mobile app | Telegram is the interface |
| Real-time live chat passthrough | Architectural mismatch with async bot |
| Full inline CRM editor in Telegram | Too complex for chat UI; use Kommo web |
| Voice + menu simultaneous | aiogram-dialog and voice use different FSM |
| Multi-step HITL edits | Binary confirm/cancel is sufficient; editing in chat UX is poor |
| Caching agent responses | Agent reformulates; cache at pipeline level instead |

***REMOVED******REMOVED*** Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| SEC-01 | Phase 1 | Pending |
| SEC-02 | Phase 1 | Pending |
| SEC-03 | Phase 1 | Pending |
| SEC-04 | Phase 1 | Pending |
| PIPE-01 | Phase 1 | Pending |
| PIPE-02 | Phase 1 | Pending |
| PIPE-03 | Phase 1 | Pending |
| PIPE-04 | Phase 1 | Pending |
| OBS-01 | Phase 2 | Pending |
| OBS-02 | Phase 2 | Pending |
| OBS-03 | Phase 2 | Pending |
| TEST-01 | Phase 2 | Pending |
| TEST-02 | Phase 2 | Pending |
| TEST-03 | Phase 1 | Pending |
| TEST-04 | Phase 1 | Pending |
| MENU-01 | Phase 3 | Pending |
| MENU-02 | Phase 3 | Pending |
| MENU-03 | Phase 3 | Pending |
| MENU-04 | Phase 3 | Pending |
| CRM-01 | Phase 4 | Pending |
| CRM-02 | Phase 4 | Pending |
| CRM-03 | Phase 4 | Pending |
| CRM-04 | Phase 4 | Pending |
| I18N-01 | Phase 4 | Pending |
| I18N-02 | Phase 4 | Pending |
| I18N-03 | Phase 4 | Pending |
| TOOL-01 | Phase 5 | Pending |
| TOOL-02 | Phase 5 | Pending |
| TOOL-03 | Phase 5 | Pending |
| TOOL-04 | Phase 5 | Pending |
| E2E-01 | Phase 6 | Pending |
| E2E-02 | Phase 6 | Pending |
| E2E-03 | Phase 6 | Pending |
| E2E-04 | Phase 6 | Pending |

**Coverage:**
- v1 requirements: 32 total
- Mapped to phases: 32
- Unmapped: 0

---
*Requirements defined: 2026-02-19*
*Last updated: 2026-02-19 — traceability confirmed after roadmap creation*

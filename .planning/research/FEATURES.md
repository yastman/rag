# Feature Research

**Domain:** Production RAG + CRM Telegram Bot (Real Estate Assistant)
**Researched:** 2026-02-19
**Confidence:** HIGH (codebase confirmed) / MEDIUM (ecosystem patterns) / noted per section

---

## Context: What Already Exists

This is a subsequent milestone on a production system. The following are NOT research targets —
they already ship and are stable:

| Already Built | Status |
|---------------|--------|
| 11-node LangGraph RAG pipeline | Production |
| create_agent SDK with tool routing | Production (#413) |
| 8 CRM tools (Kommo API v4) | Production |
| Voice path (Whisper STT + LiveKit) | Production |
| Hybrid search BGE-M3 + RRF + ColBERT | Production |
| 6-tier Redis cache | Production |
| Langfuse observability (35 obs/trace, 25 scores) | Production |
| aiogram-dialog skeleton (states.py, client_menu.py 3-btn, funnel.py 4-step, settings.py lang) | Partial |
| i18n Fluent/gettext via aiogram_i18n (ru/en/uk) | Partial |
| Lead scoring + nurturing scheduler (APScheduler) | Production |
| Hot lead notifier | Production |

Active issues define the next milestone: #447 (menu), #443 (HITL), #444 (i18n), #445 (new tools), #446 (E2E), #439 (guard).

---

## Feature Landscape

### Table Stakes (Users Expect These)

Features that users assume exist in any production CRM+RAG bot. Missing = bot feels broken or unsafe.

| Feature | Why Expected | Complexity | Status | Notes |
|---------|--------------|------------|--------|-------|
| **Role-based menu (client vs manager)** | Every production bot splits UI by role; managers need different actions | MEDIUM | Partial — skeleton exists (3 buttons), needs 9-button expansion per role | aiogram-dialog, role detected by telegram_id in manager_ids config |
| **BANT qualification funnel** | Real estate: every serious bot collects budget/type/timeline before rag_search | MEDIUM | Partial — 4-step funnel exists but doesn't connect to rag_search or crm_create_lead | funnel.py steps exist, results window is a placeholder |
| **HITL confirmation for write CRM ops** | Users (and managers) must confirm before lead/contact is created/modified — standard UX pattern | MEDIUM | Missing — no HITL on any CRM write tool | LangGraph `interrupt()` + `Command(resume=...)` is the correct pattern (HIGH confidence from official LangGraph docs) |
| **i18n system prompt (RU/UK/EN)** | Bot already supports 3 locales in dialogs; system prompt is still RU-only hardcoded | LOW | Missing — `DEFAULT_SYSTEM_PROMPT` in agent.py is hardcoded RU; dialogs have i18n getters | Langfuse PM already has `supervisor_agent` prompt slot; need per-locale variants |
| **Guard on text path** | Voice path is guarded; text path has 3 bypass vectors (issue #439 — HIGH risk classified) | LOW | Missing — critical security gap | Pre-agent `detect_injection(message.text)` call in bot.py before `agent.ainvoke()` |
| **Free text + buttons as unified path** | Users expect seamless switch between typing and tapping buttons | LOW | Architecture defined (#447 plan) — buttons generate text intents → same agent | Intent mapper: `callback_id → text_intent → agent.ainvoke()` |
| **User-facing "my deals" / "my tasks"** | Client: see own applications; Manager: see own pipeline | MEDIUM | Missing — needs `crm_get_my_leads`, `crm_get_my_tasks` tools (#443) | Kommo API: filter by responsible_user_id and contact_id |
| **Mortgage calculator** | Real estate bots universally provide annuity payment calculation | LOW | Missing (#445) | Pure math, no external API needed: `M = P * r(1+r)^n / ((1+r)^n - 1)` |
| **Manager handoff (live agent)** | When bot can't help, escalate to human — standard in CRM bots | MEDIUM | Missing (#445) | Notify manager via Telegram notification; flag conversation for live takeover |
| **Settings: language, notifications** | Users expect to change language and notification preferences | LOW | Partial — settings.py has language switch, notifications stub missing | Language persisted via user_service; notification preferences need a toggle |
| **FAQ / quick answers** | Static knowledge retrieval without full RAG pipeline overhead | LOW | Stub exists (`faq.py` placeholder) — needs integration with `rag_search(scope="faq")` | Can reuse existing rag_search with scope param |

### Differentiators (Competitive Advantage)

Features that set this bot apart. Not universal expectations, but high-value for this use case.

| Feature | Value Proposition | Complexity | Status | Notes |
|---------|-------------------|------------|--------|-------|
| **BANT → auto CRM lead creation** | After funnel completes, auto-create scored lead in Kommo — eliminates manual CRM entry | MEDIUM | Missing — funnel.py results window is placeholder | Funnel data (type, budget, timeline) → `crm_create_lead` + `lead_scoring` → hot/warm/cold classification |
| **Agent reformulation keeps original text for guard** | Guard currently checks reformulated query (gap #4 in #439) — checking original prevents semantic laundering attacks | LOW | Missing | Store `original_user_query` in BotContext; pass to guard before agent |
| **Manager daily summary** | LLM-synthesized daily CRM digest (deals updated today, tasks due, hot leads) | MEDIUM | Missing (#445) | `crm_get_leads(updated_today)` → LLM summarize → send via bot |
| **Session summary → CRM note** | When session idle 30+ min, auto-summarize conversation → add as note to Kommo lead | MEDIUM | Missing (#445) — `SessionSummaryWorker` described in plan | APScheduler job: idle detection → gpt-4o-mini summarize → `crm_add_note` |
| **Property catalog with filters** | `rag_search(scope="objects", filters={category, district, price, rooms})` — structured property browsing | MEDIUM | Missing — `rag_search` currently no `scope` or `filters` params | Requires extending rag_tool.py and RAG pipeline scope routing |
| **Nurturing dispatch with Qdrant preferences** | Send personalized property updates to warm leads based on stored preferences | HIGH | Infrastructure exists (`NurturingService` + `NurturingScheduler`) — dispatch mechanism missing | Connect preferences stored in Qdrant/Redis to nurturing job payload |
| **CRM submenu from agent response** | Inline keyboard attached to CRM results (contact/deal cards) with quick actions | MEDIUM | Missing — defined in #447 plan | `crm_get_deal` / `crm_get_contacts` response → parse → attach InlineKeyboardMarkup |
| **Follow-up inline buttons after lead creation** | "Book showing / See similar / Remind later" inline keyboard in 24h follow-up | MEDIUM | Missing — described in #447 background automation section | Callback → agent intent; integrates with NurturingScheduler |
| **crm_search_leads for manager** | Full-text search across deals/contacts from manager menu | MEDIUM | Missing (#443) | Kommo API search endpoint; manager enters query via TextInput window |

### Anti-Features (Deliberately NOT Build)

Features that seem good but create problems in this architecture.

| Anti-Feature | Why Requested | Why Problematic | Alternative |
|--------------|---------------|-----------------|-------------|
| **Full inline keyboard CRM editor** | "Would be nice to edit CRM fields without typing" | Turns bot into a form app; aiogram-dialog state explosion; duplicates Kommo web UI; maintenance nightmare | HITL confirmation for agent-initiated writes is sufficient; users edit complex fields in Kommo directly |
| **Real-time live agent chat passthrough** | "Manager should see and respond inside Telegram" | Requires two-way websocket relay between manager's Telegram and client's Telegram; state management nightmare; Kommo already has live chat | `handoff_to_manager()` sends notification to manager with client context; manager replies in Kommo |
| **Voice + menu simultaneously** | "Voice should also trigger menu actions" | aiogram-dialog state and voice handler conflict on FSM; complex UX | Voice path → text pipeline is already clean; menus are for keyboard interaction only |
| **Caching agent responses** | "Cache LLM responses to reduce cost" | Agent uses `create_agent` with ReAct loop; caching intermediate tool calls creates stale CRM data; semantic cache already exists at RAG layer | Semantic cache at RAG layer (already built) is sufficient; CRM data must always be fresh |
| **Per-user conversation graphs** | "Each user should have a separate LangGraph instance" | Memory/CPU cost explodes at scale; current checkpoint-per-thread approach via Redis already isolates sessions | Existing `thread_id=session_id` checkpointer pattern is correct |
| **Multi-step HITL edits** | "User should be able to edit field values during HITL confirmation" | Adds dialog complexity; requires form input in HITL flow; likely UX confusion | Show preview → Confirm / Cancel binary choice. If user wants to change values, they cancel and re-request with corrected info |
| **Agent-written E2E tests against live Telegram API** | "Test against real Telegram" | Flaky, slow, requires bot tokens in CI, hits rate limits | Mocked aiogram approach: `AsyncMock(Message)` + patch `agent.ainvoke()` — sufficient for E2E coverage without live API |

---

## Feature Dependencies

```
[Guard fix (#439)]
    └──required-before──> [Text path agent invocation] (any feature using agent)

[Pipeline refactor (#442)]
    └──required-before──> [HITL (#443)]
    └──required-before──> [Menu skeleton (#447)]
    └──required-before──> [New tools (#445)]

[HITL (#443)]
    └──required-before──> [Menu skeleton full (#447)] (buttons 4, 6 need HITL tools)
    └──required-before──> [CRM submenu (#447)] (write actions need HITL)
    └──provides──> [crm_search_leads, crm_get_my_leads, crm_get_my_tasks, crm_update_contact]

[Menu skeleton (#447)]
    └──required-before──> [E2E tests (#446)] (E2E tests navigate menu)
    └──requires──> [i18n (#444)] for localized button text

[i18n (#444)]
    └──enhances──> [Menu skeleton (#447)] (button text from locale files)
    └──enhances──> [System prompt] (per-locale prompt variants)
    └──required-by──> [Settings language switch] (already partial)

[New tools (#445)]
    └──provides──> [mortgage_calculator, daily_summary, handoff_to_manager, SessionSummaryWorker]
    └──required-before──> [Menu buttons 5, 8 client / 6, 8 manager (#447)]
    └──required-before──> [E2E full coverage (#446)]

[BANT funnel → CRM lead]
    └──requires──> [funnel.py results window] (exists as placeholder)
    └──requires──> [crm_create_lead] (already exists)
    └──requires──> [lead_scoring] (already exists)
    └──requires──> [HITL] for create confirmation

[E2E tests (#446)]
    └──requires──> All phases merged
    └──requires──> Mocked agent.ainvoke() pattern established

[Guard on text path (#439)]
    └──independent──> All other features (can be fixed in parallel with #442)

[Session summary worker]
    └──requires──> [crm_add_note] (already exists)
    └──requires──> [APScheduler] (already in production via NurturingScheduler)
    └──enhances──> Langfuse observability (session_summary span)

[Property catalog with scope/filters]
    └──requires──> rag_tool.py scope/filters extension
    └──requires──> RAG pipeline routing for scope
    └──enhances──> Menu buttons 2 (catalog), 7 (FAQ)

[CRM submenu inline keyboard]
    └──requires──> [crm_get_deal, crm_get_contacts] (already exist)
    └──requires──> [HITL] for write actions in submenu
    └──enhances──> Manager workflow efficiency
```

### Dependency Notes

- **Guard (#439) is independent**: Can be merged in parallel with Phase 1 (#442). Should ship first or concurrently because it fixes a HIGH-risk security gap present in production now.
- **#442 gates #443, #444, #447, #445**: Pipeline refactor is the critical-path blocker for all downstream phases.
- **i18n and menu are co-dependent**: Menu uses i18n getters; i18n middleware must be configured before menu expansion is testable.
- **BANT funnel → CRM conflicts with anti-feature "no multi-step HITL edits"**: Funnel collects structured data via dialog steps (no HITL needed for each step); single HITL confirm at funnel completion is the correct pattern.

---

## MVP Definition

The active phases (#442→#443→#444→#445→#446) define the milestone MVP.

### Phase ordering matches dependency graph:

- [ ] **Phase 0 (guard fix, #439)** — ship immediately; HIGH security risk in production
- [ ] **Phase 1 (#442)** — pipeline refactor; unblocks everything downstream
- [ ] **Phase 2 (#443)** — 4 new CRM tools + HITL; unblocks menu write buttons and E2E HITL tests
- [ ] **Phase 3 (#444/#447)** — menu expansion to 9+9 buttons + i18n system prompt; user-facing impact
- [ ] **Phase 4 (#445)** — mortgage, daily_summary, handoff, background workers; completes feature set
- [ ] **Phase 5 (#446)** — E2E tests + cleanup + epic close

### Launch With (milestone complete when):

- [ ] Client sees 9 buttons; manager sees 9 buttons on /start
- [ ] Every button generates correct intent → correct tool call
- [ ] HITL confirmation on all write operations (create_lead, update_lead, create_task, update_contact)
- [ ] Guard runs on text path before agent (closes #439)
- [ ] i18n: system prompt delivered in user's locale (RU/UK/EN)
- [ ] mortgage_calculator, daily_summary, handoff tools available
- [ ] SessionSummaryWorker running on 30-min idle
- [ ] E2E tests for menu navigation, BANT funnel, HITL flow, full agent flow

### Add After Validation (v1.x):

- [ ] Property catalog with scope/filters — rag_search extension (medium complexity, requires RAG pipeline change)
- [ ] CRM submenu inline keyboard from deal/contact cards — depends on #447 stable
- [ ] Follow-up inline buttons (24h/3d/7d) in nurturing sequence — depends on NurturingDispatch

### Future Consideration (v2+):

- [ ] Nurturing dispatch from Qdrant preferences — infrastructure exists, dispatch wiring is HIGH complexity
- [ ] Manager live chat passthrough — explicitly anti-feature (see above)
- [ ] Per-locale Langfuse prompt variants with A/B testing
- [ ] Voice-triggered menu (low priority, voice already has own clean path)

---

## Feature Prioritization Matrix

| Feature | User Value | Implementation Cost | Priority |
|---------|------------|---------------------|----------|
| Guard text path fix (#439) | HIGH (security) | LOW | P0 — ship immediately |
| Pipeline refactor (#442) | MEDIUM (internal) | MEDIUM | P1 — unblocks all |
| HITL on write CRM ops (#443) | HIGH | MEDIUM | P1 |
| Menu 9+9 expansion (#444/#447) | HIGH | MEDIUM | P1 |
| i18n system prompt (#444) | MEDIUM | LOW | P1 |
| Mortgage calculator (#445) | HIGH | LOW | P1 |
| Manager daily summary (#445) | HIGH (manager UX) | MEDIUM | P1 |
| Handoff to manager (#445) | HIGH (safety net) | MEDIUM | P1 |
| SessionSummaryWorker (#445) | MEDIUM | MEDIUM | P1 |
| E2E tests (#446) | MEDIUM (confidence) | MEDIUM | P1 |
| BANT → auto CRM lead | HIGH | MEDIUM | P2 |
| rag_search scope/filters | HIGH | MEDIUM | P2 |
| CRM submenu inline keyboard | MEDIUM | MEDIUM | P2 |
| Property catalog via RAG | MEDIUM | HIGH | P2 |
| Nurturing dispatch | MEDIUM | HIGH | P3 |

**Priority key:** P0 = ship before any new code, P1 = this milestone, P2 = next milestone, P3 = future

---

## Competitor Feature Analysis

Studied: generic property bot designs (AgentiveAIQ, n8n RAG templates), aiogram-dialog production examples (table booking, restaurant bots), LangGraph HITL documentation.

| Feature | Generic RAG Bots | CRM-Only Bots | This System | Assessment |
|---------|-----------------|---------------|-------------|------------|
| Structured qualification funnel | Rare (free text) | Yes (forms) | Yes (aiogram-dialog BANT) | Differentiator |
| HITL on write ops | No | Yes (manual approval) | Phase 2 | Table stakes for CRM |
| Role-based UI | Rare | Yes (agent/manager split) | Phase 3 | Table stakes for B2B |
| Multi-language | Sometimes | Rarely | Yes (RU/UK/EN) | Differentiator in CIS market |
| Lead scoring + nurturing | No | Some | Yes (production) | Strong differentiator |
| Voice input | No | No | Yes (production) | Differentiator |
| Hybrid semantic search | No (keyword or dense) | No | Yes (RRF + ColBERT) | Differentiator |
| Session auto-summary to CRM | No | Rare | Phase 4 | Differentiator |
| Guard / content filtering | Rarely | No | Yes (voice), Phase 0 (text) | Table stakes for production |
| E2E tests | Rarely | No | Phase 5 | Internal quality |

---

## Implementation Notes Per Feature

### HITL Pattern (HIGH confidence — LangGraph official docs verified)

```python
# Inside @tool function (e.g., crm_create_lead):
from langgraph.types import interrupt, Command

@tool
async def crm_create_lead(name: str, budget: str, config: RunnableConfig) -> str:
    preview = f"Создать сделку: {name}, бюджет {budget}"
    decision = interrupt({"preview": preview, "action": "create_lead", "args": {...}})
    if decision.get("action") == "approve":
        # execute actual Kommo API call
        ...
    return "Операция отменена"

# Bot side: callback handler for hitl:confirm / hitl:cancel
# → graph.invoke(Command(resume={"action": "approve"}), config=config)
```

The `interrupt()` approach is cleaner than `interrupt_before` static breakpoints: it can show preview data, supports conditional interruption (only for write ops, not reads), and persists state across async Telegram callback latency. [HIGH confidence — LangGraph docs + multiple 2025 production examples]

### i18n Approach (MEDIUM confidence — official aiogram docs verified)

Two viable approaches in this codebase:
1. **aiogram_i18n + FluentRuntimeCore** — already partially wired in dialogs (i18n getters use `i18n.get()`)
2. **Langfuse PM per-locale prompt** — `get_prompt("supervisor_agent_ru")`, `get_prompt("supervisor_agent_uk")`

Recommendation: Use approach 2 for system prompt (already has Langfuse PM integration in agent.py via `get_prompt()`). Use approach 1 for dialog text (already partially wired). Keep both layers separate — dialog i18n and LLM i18n are orthogonal.

### Guard Text Path Fix (HIGH confidence — issue #439 documented the exact gaps)

Three fixes required in `bot.py` and `agents/agent.py`:
1. `detect_injection(message.text)` call in `handle_query()` BEFORE `agent.ainvoke()`
2. Add safety instructions to `DEFAULT_SYSTEM_PROMPT` (refuse harmful requests, no system info leak)
3. Store `original_user_query` in `BotContext` so guard checks original, not reformulation

### E2E Testing Pattern (MEDIUM confidence — community pattern, no canonical aiogram E2E framework)

No canonical E2E framework exists for aiogram bots. The production pattern is:
```python
# Mocked aiogram Message
msg = AsyncMock(spec=Message)
msg.from_user = MagicMock(id=12345)
msg.text = "Покажи каталог"

# Patch agent.ainvoke
with patch("telegram_bot.bot.create_bot_agent") as mock_agent:
    mock_agent.return_value.ainvoke = AsyncMock(return_value={"messages": [...]})
    await bot.handle_query(msg)
    mock_agent.return_value.ainvoke.assert_called_once()
```

This approach (already used in `tests/unit/agents/`) is the right direction. Issue #446 extends it to cover menu navigation, BANT funnel flow, and HITL confirm/cancel.

### Menu Architecture (HIGH confidence — defined in #447 plan, matches aiogram-dialog patterns)

The "buttons = text intent shortcuts" pattern is architecturally sound and matches how production aiogram-dialog bots work (table booking example: steps collect data → final action is a service call). The key implementation decision is:
- Buttons 1, 7, 9 (client) → `Start()` widget → sub-dialog (FunnelSG, FaqSG, SettingsSG) — no agent
- Buttons 2, 3, 4, 5, 6, 8 (client) → `on_click` handler → `intent_text` → `agent.ainvoke()` — one agent for all
- Manager buttons 1-8 → same pattern, different intents and tools

---

## Sources

- LangGraph HITL official docs: https://langchain-ai.github.io/langgraph/cloud/how-tos/add-human-in-the-loop/ [HIGH confidence]
- LangGraph interrupt() patterns: https://docs.langchain.com/oss/python/langgraph/interrupts [HIGH confidence]
- aiogram-dialog documentation: https://aiogram-dialog.readthedocs.io/en/develop [HIGH confidence]
- aiogram i18n official docs: https://docs.aiogram.dev/en/v3.19.0/utils/i18n.html [HIGH confidence]
- aiogram_i18n + Fluent production example: https://habr.com/ru/articles/987482/ [MEDIUM confidence]
- Production aiogram-dialog bot (table booking): https://medium.com/@amverait/friends-hello-8460dfe86ef1 [MEDIUM confidence]
- HITL LangGraph patterns series (2025): https://medium.com/the-advanced-school-of-ai/human-in-the-loop-in-langgraph-approve-or-reject-pattern-fcf6ba0c5990 [MEDIUM confidence]
- BANT chatbot qualification for real estate (2025): https://agentiveaiq.com/listicles/best-5-buyer-qualification-chats-for-real-estate-agencies [MEDIUM confidence]
- Project codebase: `telegram_bot/dialogs/`, `telegram_bot/agents/`, `docs/plans/`, GitHub issues #439–#447 [HIGH confidence]

---

*Feature research for: Production RAG + CRM Telegram Bot (Real Estate Assistant)*
*Researched: 2026-02-19*

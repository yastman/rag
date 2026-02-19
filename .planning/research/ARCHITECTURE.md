# Architecture Research

**Domain:** Production RAG + CRM Telegram bot — milestone feature integration
**Researched:** 2026-02-19
**Confidence:** HIGH (all claims grounded in actual codebase files + verified against aiogram-dialog and LangGraph docs)

---

## System Overview

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                          aiogram Dispatcher Layer                           │
│                                                                             │
│  ThrottlingMiddleware → ErrorMiddleware → I18nMiddleware → RouteHandler     │
│                                                                             │
│  ┌───────────────────────────────────┐  ┌──────────────────────────────┐   │
│  │      Dialog Router Layer          │  │     Free-text Handler Layer  │   │
│  │  (aiogram-dialog, FSM active)     │  │  (aiogram, no FSM state)     │   │
│  │                                   │  │                              │   │
│  │  ClientMenuSG / ManagerMenuSG     │  │  handle_query()              │   │
│  │  SettingsSG / FunnelSG / FaqSG    │  │  handle_voice()              │   │
│  │  HITLConfirmSG (new)              │  │  handle_feedback()           │   │
│  └────────────────┬──────────────────┘  └──────────┬───────────────────┘   │
└───────────────────┼──────────────────────────────── ┼ ──────────────────────┘
                    │                                  │
                    │ (dialog done → FSM clears)        │ (no FSM → falls through)
                    │                                  │
          ┌─────────▼──────────────────────────────────▼──────────────────┐
          │                    Agent SDK Layer                             │
          │                                                                │
          │   create_bot_agent(model, tools, context_schema=BotContext)    │
          │         ↓                                                      │
          │   LLM tool_choice → rag_search | history_search | crm_*       │
          │         ↓ (BotContext DI via configurable["bot_context"])      │
          └─────────────────────────────────┬──────────────────────────────┘
                                            │
              ┌─────────────────────────────┼──────────────────────────────┐
              │                             │                              │
   ┌──────────▼──────────┐      ┌──────────▼──────────┐     ┌────────────▼──────┐
   │  RAG Pipeline       │      │  History Sub-graph  │     │   CRM Tools       │
   │  (text path)        │      │  (4-node LangGraph) │     │  (8 @tools)       │
   │                     │      │                     │     │                   │
   │  Phase #442:        │      │  guard → retrieve   │     │  crm_get_deal     │
   │  rag_pipeline()     │      │  → grade → rewrite  │     │  crm_create_lead  │
   │  6-step async       │      │  → summarize        │     │  crm_update_lead  │
   │  (replaces 11-node  │      │                     │     │  crm_upsert_contact│
   │  LangGraph graph)   │      │  Guard: #432        │     │  crm_add_note     │
   │                     │      │  (pending)          │     │  crm_create_task  │
   │  Voice: still uses  │      │                     │     │  crm_link_contact │
   │  LangGraph graph    │      │                     │     │  crm_get_contacts │
   └─────────────────────┘      └─────────────────────┘     └───────────────────┘
              │                                                         │
              │                                                 HITL: interrupt()
              │                                                 + callback_query
              │
   ┌──────────▼─────────────────────────────────────────────────────────────────┐
   │                         Services Layer                                     │
   │                                                                            │
   │  CacheLayerManager (Redis, 6-tier) │ QdrantService (gRPC, batch)           │
   │  BGEM3HybridEmbeddings             │ ColbertRerankerService                 │
   │  KommoClient (OAuth2 + TokenStore) │ HistoryService (Qdrant)               │
   │  LangfuseClient (@observe, scores) │ LeadScoringStore (asyncpg)            │
   └────────────────────────────────────────────────────────────────────────────┘
```

---

## Component Boundaries

| Component | Responsibility | Communicates With |
|-----------|---------------|-------------------|
| `PropertyBot` (bot.py) | Lifecycle, handler registration, service DI, startup | Dispatcher, all services |
| `Dispatcher` (aiogram) | Route messages to handlers or dialog routers | ThrottlingMiddleware, I18nMiddleware, ErrorMiddleware |
| Dialog Routers (aiogram-dialog) | FSM-driven menus: client menu, funnel, FAQ, settings, HITL confirm | Dispatcher (dp.include_router), DialogManager, UserService |
| `handle_query` / `handle_voice` | Free-text and voice entry points | Agent SDK (create_bot_agent), LangGraph graph (voice) |
| Agent SDK (`create_bot_agent`) | LLM routing: picks tool or responds directly | rag_search, history_search, CRM tools; BotContext for DI |
| `rag_search` @tool | Wraps RAG pipeline, writes Langfuse scores | RAGPipeline (simplified #442) or build_graph() |
| RAG Pipeline (#442 target) | 6-step async: guard → cache → retrieve → grade → rerank/rewrite → generate | Cache, BGE-M3, Qdrant, LLM, Langfuse |
| LangGraph voice graph | 11-node StateGraph for voice: transcribe → guard → classify → ... | Same services as RAG pipeline |
| History sub-graph | 4-node LangGraph: retrieve → grade → rewrite → summarize | HistoryService, LLM |
| Guard node | Regex + optional ML injection detection, mode=hard/soft/log | LLMGuardClient (opt-in) |
| CRM @tools (8 tools) | Kommo API CRUD operations | KommoClient |
| HITL confirmation (new) | Pause CRM writes for user approval before execute | Agent SDK interrupt() + callback_query handler |
| BotContext (context.py) | DI container: 13 service fields injected into all tools | Populated by PropertyBot, read by all @tools |
| `write_langfuse_scores` | 14+ RAG metrics to Langfuse per pipeline invocation | Langfuse SDK |

---

## Data Flow

### Text Path (Current)

```
User message (text)
    ↓
ThrottlingMiddleware → ErrorMiddleware → I18nMiddleware
    ↓
[FSM state active?]
    ├── YES: Dialog router handles (menu buttons, funnel steps, HITL confirm)
    └── NO: handle_query() → _handle_query_supervisor()
              ↓
          create_bot_agent(model, tools, checkpointer)  ← new agent each call
              ↓ configurable["bot_context"] = BotContext (DI)
          agent.ainvoke({"messages": [HumanMessage]}, config={callbacks, thread_id})
              ↓ LLM decides tool
          ┌──────────────────────────────────────────────────────┐
          │ rag_search(query)    → RAGPipeline.run(query, ctx)   │
          │ history_search(q)   → build_history_graph().ainvoke  │
          │ crm_*(args)         → KommoClient API call           │
          │ (direct response)   → LLM answer without tool        │
          └──────────────────────────────────────────────────────┘
              ↓
          response_text → split → message.answer() + feedback keyboard
              ↓
          write_langfuse_scores() + history_service.save_turn()
```

### Voice Path (Current — stays LangGraph)

```
User message (voice .ogg)
    ↓
handle_voice() → download bytes → make_initial_state(voice_audio=bytes)
    ↓
build_graph(cache, embeddings, sparse, qdrant, reranker, llm, message)
    ↓
graph.ainvoke(state, config={thread_id, checkpoint_ns})
    ↓
START → route_start → transcribe (Whisper/LiteLLM)
     → guard → classify → cache_check → retrieve → grade
     → [rerank | rewrite | generate] → cache_store → respond → summarize → END
    ↓
write_langfuse_scores(lf, result) + history_service.save_turn()
```

### Dialog / Menu Path (aiogram-dialog)

```
/start command
    ↓
cmd_start() → dialog_manager.start(ClientMenuSG.main, mode=StartMode.RESET_STACK)
    ↓
aiogram-dialog FSM active for this user
    ↓ (all subsequent messages routed through dialog router, not free-text handler)
Client clicks "Подобрать недвижимость"
    ↓
FunnelSG.property_type → FunnelSG.budget → FunnelSG.timeline → FunnelSG.results
    dialog_manager.dialog_data accumulates: {property_type, budget, timeline}
    ↓ (results window: placeholder today, RAG integration pending)
FunnelSG.results → Cancel() → dialog_manager.done() → FSM clears
    ↓ (user back to free-text mode — next message goes to handle_query)
```

### HITL Confirmation Flow (target architecture)

```
Agent decides to call crm_create_lead(name="...", budget=...)
    ↓
[HITL pattern — Option A: inline callback_query]
crm_create_lead tool sends InlineKeyboard: "Create deal X? [Confirm] [Cancel]"
    ↓
User clicks "Confirm" → callback_query → handle_hitl_confirm()
    ↓ executes KommoClient.create_lead()
    ↓ replies to agent with result

[HITL pattern — Option B: LangGraph interrupt()]
interrupt() inside CRM write tool → graph pauses (requires checkpointer)
    ↓
Command(resume=True/False) → resumes with user decision
    ↓ proceeds or aborts
```

**IMPORTANT:** Option A (callback_query) is simpler and fits current architecture.
Option B (LangGraph interrupt) requires the agent's MemorySaver checkpointer and
correct thread_id routing — feasible but adds complexity. Option A preferred.

### Guard Integration (target — all paths)

```
Text path:   handle_query → agent.ainvoke → rag_search tool → rag_pipeline.guard_step()
Voice path:  handle_voice → graph.ainvoke → guard_node (already wired, #439 gap: text bypasses)
History:     history_search tool → build_history_graph → guard node (pending #432)
Dialogs:     MessageInput widgets (funnel free-text fields) → guard before agent invoke
```

---

## Recommended Project Structure (current + additions)

```
telegram_bot/
├── agents/
│   ├── agent.py           # create_bot_agent factory (stable, no changes)
│   ├── context.py         # BotContext DI dataclass (add hitl_bot field if needed)
│   ├── rag_tool.py        # @tool wrapping RAG pipeline (update to rag_pipeline #442)
│   ├── history_tool.py    # @tool wrapping history graph (stable)
│   ├── crm_tools.py       # 8 CRM @tools (add HITL intercept layer)
│   ├── rag_pipeline.py    # NEW: 6-step async pipeline (#442, replaces build_graph in tool)
│   └── history_graph/     # History sub-graph (add guard node #432)
├── dialogs/
│   ├── states.py          # FSM states (add HITLConfirmSG)
│   ├── client_menu.py     # Client menu dialog (stable)
│   ├── manager_menu.py    # Manager menu dialog (new #444)
│   ├── funnel.py          # BANT funnel (wire to RAG in Phase 2)
│   ├── faq.py             # FAQ (stable)
│   ├── settings.py        # Settings + language (stable)
│   └── hitl_confirm.py    # NEW: HITL confirm dialog for CRM writes (#443)
├── graph/
│   ├── graph.py           # LangGraph 11-node (voice path — keep)
│   ├── nodes/
│   │   ├── guard.py       # Guard node (text path gap: wire into rag_pipeline)
│   │   └── ...            # Other nodes (stable)
│   └── state.py           # RAGState (stable)
├── bot.py                 # PropertyBot (add HITL callback handler)
└── feedback.py            # Feedback keyboard (existing, model for HITL keyboard)
```

---

## Architectural Patterns

### Pattern 1: Dialog vs Free-Text Routing (aiogram-dialog FSM priority)

**What:** aiogram-dialog registers as a Router via `dp.include_router(dialog)`. When a user has an active FSM state, aiogram routes their messages to the dialog router first. The free-text handler (`F.text`) only fires when no FSM state is active.

**When to use:** Structured interaction (menus, funnel, HITL confirmation). FSM state is the switch.

**Confirmed behavior (HIGH confidence from docs):** `setup_dialogs(dp)` wires the dialog middleware. When FSM is active, the dialog's `MessageInput` widget captures messages before the `F.text` handler fires. When `dialog_manager.done()` is called, FSM clears and free-text handler resumes.

**Implication for build order:** Dialog routers MUST be registered before `setup_dialogs(dp)` call and before `F.text` handler registration would cause conflicts. Current `bot.py` does this correctly in `start()`.

```python
# Current correct order in PropertyBot.start():
dp.include_router(client_menu_dialog)   # register dialog routers
dp.include_router(settings_dialog)
dp.include_router(funnel_dialog)
dp.include_router(faq_dialog)
aiogram_setup_dialogs(dp)               # wire dialog middleware

# Free-text handler registered in __init__ (earlier)
dp.message(F.text)(self.handle_query)   # fires only when no FSM state active
```

### Pattern 2: BotContext DI — Service Access in All Tools

**What:** `BotContext` dataclass is populated once per request in `handle_query` and passed via `config["configurable"]["bot_context"]`. All `@tool` functions receive it by accessing `config.get("configurable", {}).get("bot_context")`.

**When to use:** Any new tool or pipeline that needs service access (kommo_client, embeddings, qdrant, cache). Never instantiate services inside tools — always read from BotContext.

**Implication:** Adding HITL to CRM tools requires either (a) adding `bot: Bot` field to BotContext for sending confirmation messages, or (b) using a side-channel (e.g., asyncio.Event in config["configurable"]).

```python
# Existing pattern — extend for HITL
@dataclass
class BotContext:
    telegram_user_id: int
    session_id: str
    language: str
    kommo_client: Any | None
    # ... existing fields ...
    bot: Any | None = None          # aiogram.Bot for HITL message sending
    hitl_enabled: bool = False      # feature flag for HITL confirmation
```

### Pattern 3: Simplified RAG Pipeline (6-step async, #442)

**What:** `rag_pipeline()` replaces `build_graph().ainvoke()` inside `rag_search` tool for text path. Plain async function, no StateGraph, no LangGraph overhead. Voice path keeps LangGraph graph (transcription needs graph state).

**When to use:** Text queries. The function signature is: `async def rag_pipeline(query: str, ctx: BotContext) -> PipelineResult`.

**Guard integration:** Guard becomes step 0 in the pipeline function, not a LangGraph node for text path. Same `guard_node()` logic reused, but called directly.

```python
# Target pattern (rag_pipeline.py #442)
async def rag_pipeline(query: str, ctx: BotContext) -> PipelineResult:
    # Step 0: Guard (fixes #439 text path bypass)
    guard_result = await guard_node({"messages": [...]}, guard_mode=ctx.guard_mode)
    if guard_result.get("guard_blocked"):
        return PipelineResult(response=BLOCKED_RESPONSE, blocked=True)

    # Step 1: Cache check
    # Step 2: Retrieve (BGE-M3 dense+sparse → RRF)
    # Step 3: Grade (RRF threshold)
    # Step 4: Rerank (ColBERT, conditional)
    # Step 5: Generate (LLM)
    # Step 6: Cache store
```

**Build order implication:** #442 (pipeline refactor) must complete before wiring funnel dialog results to RAG, because FunnelSG.results needs to call `rag_pipeline()` not `build_graph()`.

### Pattern 4: HITL via Inline Keyboard (callback_query pattern)

**What:** CRM write tools (create_lead, update_lead, upsert_contact) send a confirmation InlineKeyboard before executing. The `handle_hitl_confirm` callback handler executes the deferred action.

**When to use:** Any destructive or irreversible CRM operation initiated by the agent.

**Implementation:** Uses the existing `feedback.py` pattern (InlineKeyboardMarkup + callback handler). State is stored in Redis or bot context with a TTL.

```python
# Proposed: hitl_confirm.py (mirrors feedback.py structure)
_HITL_PREFIX = "hitl:"

def build_hitl_keyboard(action_id: str, action_summary: str) -> InlineKeyboardMarkup:
    """Build confirm/cancel keyboard for CRM action."""
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="Подтвердить", callback_data=f"{_HITL_PREFIX}ok:{action_id}"),
        InlineKeyboardButton(text="Отмена", callback_data=f"{_HITL_PREFIX}cancel:{action_id}"),
    ]])

# In PropertyBot._register_handlers():
self.dp.callback_query(F.data.startswith("hitl:"))(self.handle_hitl_confirm)
```

**State storage for deferred action:** The CRM tool stores the pending action in `rag_result_store` (already in `configurable`) or Redis with `action_id` as key and TTL=60s.

### Pattern 5: Guard Wired Into All Paths

**What:** The existing `guard_node()` function in `graph/nodes/guard.py` is the canonical guard implementation. It must be called explicitly in:
1. Text path: step 0 of `rag_pipeline()` (fixes #439)
2. Voice path: already wired in LangGraph graph
3. History sub-graph: inject before `retrieve` node (fixes #432)
4. Funnel free-text inputs: call before forwarding user text to agent

**Current gap:** Text path (`handle_query → agent.ainvoke`) bypasses guard entirely. The agent's system prompt has soft guardrails but regex guard_node never runs.

**Fix architecture:** `rag_pipeline()` calls `guard_node()` directly. For the agent path (before tool invocation), a `pre_tool_guard` wrapper can intercept tool calls. Simpler: guard in `rag_pipeline()` covers the most dangerous path (document retrieval + LLM generation with injected content).

```python
# History guard (history_graph/graph.py) — add guard node before retrieve
workflow.add_node("guard", functools.partial(guard_node, guard_mode=guard_mode))
workflow.add_edge(START, "guard")       # guard first
workflow.add_conditional_edges("guard", route_after_guard, {
    "retrieve": "retrieve",
    "summarize": "summarize",           # early exit on injection
})
```

### Pattern 6: E2E Test Architecture

**What:** Three test tiers for the integrated system:
1. Unit: `tests/unit/agents/`, `tests/unit/graph/` — mocked services, test node logic
2. Integration: `tests/integration/test_graph_paths.py` — real LangGraph with mocked services, no Docker
3. E2E (Telethon): `tests/e2e/` or `scripts/e2e/` — real Telegram API, bot must be running

**For new features:**
- Dialog tests: aiogram-dialog `BotClient` test utility (HIGH confidence — documented in aiogram-dialog test docs)
- HITL tests: callback_query simulation via `create_callback_query()` in test
- Pipeline refactor tests: `tests/unit/agents/test_rag_pipeline.py` (new file, mirrors existing `test_rag_tool.py`)
- Guard integration tests: extend `tests/unit/graph/test_guard_node.py` for pipeline path

---

## Anti-Patterns

### Anti-Pattern 1: Instantiating Services Inside Tools

**What people do:** Create `KommoClient()`, `QdrantService()`, or `CacheLayerManager()` inside `@tool` functions.

**Why it's wrong:** Services have connection pools, auth state (OAuth2 tokens), and warmup costs. Instantiating per-call creates connection leaks, re-authentication on every tool call, and breaks dependency injection.

**Do this instead:** Always read from `BotContext` via `config.get("configurable", {}).get("bot_context")`. Services are initialized once in `PropertyBot.__init__()` and `PropertyBot.start()`.

### Anti-Pattern 2: Registering Dialog Routers After `setup_dialogs()`

**What people do:** Call `aiogram_setup_dialogs(dp)` then `dp.include_router(new_dialog)`.

**Why it's wrong:** `setup_dialogs` wires the middleware that processes dialog updates. Routers registered after it may not receive dialog events correctly.

**Do this instead:** Include ALL dialog routers before calling `setup_dialogs(dp)`. Current `PropertyBot.start()` is the correct pattern — extend it there.

### Anti-Pattern 3: Rebuilding Agent Per Message

**What people do (already in codebase):** `create_bot_agent(...)` called inside `_handle_query_supervisor()` on every message.

**Why it's a concern:** The agent factory call includes LLM client initialization. With the current architecture this is intentional (tool list varies by user role), but for high-traffic the cost adds up.

**Do this instead:** Cache compiled agent per role/tool-set combination if performance becomes a bottleneck. Currently acceptable — document as known tech debt.

### Anti-Pattern 4: Using LangGraph `interrupt()` for HITL in Telegram Context

**What people do:** Use LangGraph's `interrupt()` inside CRM write tools for HITL, assuming the checkpointer handles state between Telegram messages.

**Why it's wrong:** The current `_agent_checkpointer` is `MemorySaver` (in-process), not Redis-backed. `interrupt()` requires the graph to be re-invoked with `Command(resume=...)` in the same process instance. Telegram callbacks arrive via polling with no guarantee of same process continuity in multi-replica deployments.

**Do this instead:** Inline keyboard + callback_query pattern (Pattern 4 above). Store deferred action in Redis with TTL. This is stateless, survives restarts, and matches existing `feedback.py` pattern.

### Anti-Pattern 5: Mixing Dialog State and Free-Text Agent State

**What people do:** Try to access `dialog_manager` from inside `handle_query`, or call `agent.ainvoke` from inside a dialog handler.

**Why it's wrong:** aiogram-dialog manages its own FSM stack separate from the agent's conversation memory (Redis checkpointer with thread_id). Mixing them creates state divergence — the dialog thinks the user is at step X, the agent thinks conversation is at Y.

**Do this instead:** Treat dialogs and agent as separate state machines. Dialog collects structured input (funnel answers) → on completion (`dialog_manager.done()`) → result stored to Redis or DB → free-text agent picks it up via tool (e.g., `rag_search` uses funnel context from BotContext). The hand-off point is `dialog_manager.done()` → data persisted → agent reads from context.

---

## Integration Points

### Internal Boundaries

| Boundary | Communication | Notes |
|----------|---------------|-------|
| Dialogs ↔ Agent | Indirect: dialog collects data → stored → agent reads via BotContext | No direct call between them |
| `rag_search` tool ↔ RAG pipeline | Direct async call: `await rag_pipeline(query, ctx)` after #442 | Currently: `build_graph().ainvoke()` |
| CRM tools ↔ HITL | Pending action stored in Redis/configurable → callback resolves | `action_id` as correlation key |
| Guard ↔ all paths | Direct function call: `await guard_node(state, guard_mode=...)` | Shared implementation, no subgraph |
| BotContext ↔ all tools | Read-only DI: `config["configurable"]["bot_context"]` | Populated once per request in handle_query |
| Langfuse ↔ all paths | `@observe` decorators + `write_langfuse_scores()` | Fail-soft: scoring errors never break user response |

### External Services

| Service | Integration Pattern | Notes |
|---------|---------------------|-------|
| LiteLLM proxy | ChatOpenAI(base_url=config.llm_base_url) | All LLM calls route here |
| BGE-M3 API | async httpx to bge-m3:8000/encode/hybrid | Dense+sparse in one call |
| Qdrant gRPC | QdrantService.async_client (gRPC:6334) | batch upsert, group_by |
| Redis | CacheLayerManager (pipeline, TTL), AsyncRedisSaver checkpointer | Connection pool, ExponentialBackoff |
| Kommo API v4 | KommoClient (async httpx, OAuth2 auto-refresh) | KommoTokenStore in Redis |
| Langfuse v3 | langfuse.openai.AsyncOpenAI + get_client() | PII masking, @observe spans |

---

## Build Order Implications

Dependencies between the four milestone features determine implementation sequence:

```
1. Pipeline Refactor (#442) — rag_pipeline() async function
   └─ No blockers. Can start immediately.
   └─ Enables: guard wired into text path (fixes #439)
   └─ Enables: funnel dialog → RAG results integration
   └─ Enables: cleaner test surface for unit tests

2. Guard-All-Paths (#439, #432) — concurrent with #442
   └─ Text path guard: depends on #442 (guard goes into rag_pipeline step 0)
   └─ History guard: independent — modify history_graph/graph.py
   └─ Voice guard: already done (no change needed)

3. Menu / Dialog Skeleton (#447) — parallel with #442
   └─ No dependency on pipeline refactor for skeleton/navigation
   └─ FunnelSG.results RAG integration: depends on #442 (needs rag_pipeline())
   └─ HITLConfirmSG: depends on crm_tools HITL pattern (step 4)

4. HITL Confirmation (#443) — after menu skeleton
   └─ Depends on: menu skeleton (HITLConfirmSG state), CRM tools test coverage (#441)
   └─ Requires: bot field in BotContext, hitl_confirm.py, callback handler
   └─ Does NOT depend on pipeline refactor

5. E2E Tests (#406, #446) — last
   └─ Depends on: all above features implemented and stable
   └─ Integration tests (graph paths): can be written during #442
   └─ Dialog tests: written with menu skeleton (#447)
   └─ HITL callback tests: written with #443
```

**Recommended parallel tracks:**
- Track A: `#442 (rag_pipeline) → #439 (text guard fix)`
- Track B: `#432 (history guard) — independent`
- Track C: `#447 (menu skeleton) → #443 (HITL) → #444 (menu expansion)`
- Track D: `#441 (CRM test coverage) → #440 (CRM Langfuse scores)`

E2E tests (#406, #446) as final integration gate after all tracks stabilize.

---

## Sources

- `telegram_bot/bot.py` — PropertyBot architecture, handler registration order, dialog setup in `start()`
- `telegram_bot/agents/agent.py` — `create_bot_agent()` factory, BotContext schema
- `telegram_bot/agents/context.py` — BotContext dataclass (13 fields)
- `telegram_bot/agents/rag_tool.py` — Current `build_graph().ainvoke()` pattern, Phase 2 note
- `telegram_bot/agents/history_graph/graph.py` — History sub-graph structure
- `telegram_bot/agents/crm_tools.py` — CRM tool pattern, `_get_kommo()` helper
- `telegram_bot/graph/graph.py` — `build_graph()` assembly, guard wiring, conditional edges
- `telegram_bot/graph/nodes/guard.py` — guard_node implementation, INJECTION_PATTERNS
- `telegram_bot/graph/state.py` — RAGState (25 fields), guard fields in state
- `telegram_bot/dialogs/` — All 5 dialog modules: states, client_menu, funnel, faq, settings
- `telegram_bot/feedback.py` — Inline keyboard pattern (model for HITL keyboard)
- `telegram_bot/middlewares/i18n.py` — I18nMiddleware, user_service injection into middleware_data
- `.planning/PROJECT.md` — Active issues, known bugs, constraint inventory
- aiogram-dialog docs (Context7, HIGH confidence): setup_dialogs, include_router, MessageInput, FSM state routing
- LangGraph docs (Context7, HIGH confidence): interrupt(), Command(resume=), checkpointer requirement for HITL

---

*Architecture research for: production RAG + CRM Telegram bot — milestone feature integration*
*Researched: 2026-02-19*

# Stack Research

**Domain:** Production RAG + CRM Telegram bot — subsequent milestone additions
**Researched:** 2026-02-19
**Confidence:** HIGH (core libs verified via Context7 + PyPI official releases)

---

## Context: What Already Exists (Do Not Re-research)

The existing stack is production-grade and stays unchanged:
Python 3.12, uv, LangGraph 1.0.3, aiogram 3.25, aiogram-dialog 2.4, langchain-core 1.2,
FastAPI, BGE-M3 (local CPU), Qdrant 1.16+, Redis 7+, Langfuse v3, Kommo CRM (OAuth2 + httpx),
LiveKit voice, APScheduler 3.x, Ruff, MyPy.

This document only covers **new** libraries and patterns for the six open issues:
- #442 — async RAG pipeline simplification
- #441 — CRM tool test coverage
- #439 — guard node on all paths
- #447 — menu skeleton (client/manager dialogs)
- #443 — HITL confirmation
- #444 — i18n

---

## Recommended Stack (New Additions Only)

### 1. Pipeline Simplification (#442)

**Already in stack. No new dependencies.**

LangGraph 1.0.3 `interrupt()` + `Command(resume=...)` is the 2025-2026 standard for HITL
in graph pipelines. The existing 11-node StateGraph is the correct architecture.
Simplification means refactoring internal node composition, not swapping frameworks.

| Technology | Version | Purpose | Why Recommended |
|------------|---------|---------|-----------------|
| `langgraph` | `>=1.0.3,<2.0` (existing) | RAG pipeline + HITL interrupt | Already in stack; 1.0 is the stability release (Oct 2025). `interrupt()` API is the standard HITL primitive — pauses graph, surfaces payload to caller, resumes with `Command(resume=value)`. Verified via Context7. |
| `langgraph-checkpoint-redis` | `>=0.2.0` (existing) | Durable checkpointing | Required for interrupt resume across async Telegram updates. |

**Pattern (verified via Context7 — see LangGraph interrupt docs):**

```python
from langgraph.types import interrupt, Command

def approval_node(state):
    decision = interrupt({"question": "Approve?", "details": state["action"]})
    return Command(goto="proceed" if decision else "cancel")

# In Telegram handler — resume with user's choice:
graph.invoke(Command(resume=True), config={"configurable": {"thread_id": tid}})
```

**What NOT to do:** Do not add `langgraph-sdk` (cloud deployment SDK — not needed for
self-hosted). Do not switch to `langchain.agents` create_react_agent for the inner RAG
pipeline — it is already handled by the create_agent SDK wrapper.

---

### 2. CRM Test Coverage (#441)

**Core tool: `respx` — already available via `pytest-httpx`. Consider adding `respx` directly.**

| Technology | Version | Purpose | Why Recommended |
|------------|---------|---------|-----------------|
| `respx` | `0.22.0` | Mock `httpx.AsyncClient` in CRM tests | The definitive mock library for httpx. Supports `@respx.mock` decorator, `respx_mock` pytest fixture, route-based matching, and async context managers. PyPI stable (Dec 2024). 161 code snippets in Context7. pytest-httpx (already in stack) works differently — it patches at transport level. respx works at router level and is better for class-wrapped clients like KommoClient. |

**Pattern (verified via Context7 — respx docs):**

```python
import respx
import httpx
import pytest

@pytest.fixture
def mocked_kommo():
    with respx.mock(base_url="https://testcompany.kommo.com") as mock:
        mock.patch("/api/v4/leads/5001").return_value = httpx.Response(
            200, json={"id": 5001}
        )
        yield mock

async def test_update_lead(kommo_client, mocked_kommo):
    result = await kommo_client.update_lead(5001, {"name": "Test"})
    assert result["id"] == 5001
    assert mocked_kommo["patch_lead"].called
```

**Decision: Keep `pytest-httpx` for simple cases, add `respx` for KommoClient class-level
mocking.** The existing `patch.object(kommo_client._client, "request", ...)` pattern in
current tests works but is brittle — respx fixtures are more idiomatic for 2025.

**Installation:**
```bash
uv add respx --dev
```

**Confidence:** HIGH — verified on PyPI (0.22.0, Dec 2024), Context7 (94.4 score).

---

### 3. Guard Node on All Paths (#439)

**No new dependencies. Pure architecture pattern.**

The existing `guard_node` in `telegram_bot/graph/nodes/guard.py` is correct and production-
quality (21 regex patterns, EN+RU, configurable guard_mode: hard/soft/log, optional ML layer).

**The gap is wiring:** guard currently only fires on the RAG path (`START → guard → classify`).
It needs to fire on: history_search sub-graph entry, CRM tool inputs, voice path entry.

**Pattern (verified via LangGraph docs + OWASP LLM Prompt Injection Cheat Sheet):**

The 2025-2026 recommended approach is **"input guardrail at each graph/subgraph entry"**
not a single global middleware. LangGraph nodes are the right boundary — add guard as the
first node in each sub-graph's START edge.

```python
# history_graph: guard before retrieve
workflow.add_edge(START, "guard")
workflow.add_edge("guard", "retrieve")  # or respond if blocked

# For CRM tools: wrap tool inputs with detect_injection() before LLM call
# (reuse existing detect_injection() from guard.py — no import cost)
from telegram_bot.graph.nodes.guard import detect_injection
```

**What NOT to use:** `llm-guard` (the PyPI package) as a mandatory dependency on the
hot path — it loads DeBERTa v3 (~450MB, 100-200ms CPU latency). Keep it opt-in via
`GUARD_ML_ENABLED=true` as currently wired. The regex layer is sufficient for production.

---

### 4. Menu System — Client/Manager Dialogs (#447)

**Already in stack. `aiogram-dialog 2.4.0` is the right tool.**

| Technology | Version | Purpose | Why Recommended |
|------------|---------|---------|-----------------|
| `aiogram-dialog` | `2.4.0` (existing) | Multi-window dialog FSM, keyboards, navigation | The production standard for aiogram 3.x UI. 235 code snippets in Context7. Supports SwitchTo/Next/Back widgets, sub-dialogs with start/done/on_process_result, and data passing. PyPI latest: 2.4.0 (Jul 2025). |

**Key patterns (verified via Context7 — aiogram-dialog stable docs):**

```python
from aiogram.filters.state import StatesGroup, State
from aiogram_dialog import Dialog, Window, DialogManager
from aiogram_dialog.widgets.kbd import Button, Row, SwitchTo, Back, Start, Cancel
from aiogram_dialog.widgets.text import Const, Format

class ClientMenuSG(StatesGroup):
    main = State()       # Main menu
    search = State()     # RAG search
    history = State()    # Conversation history

class ManagerMenuSG(StatesGroup):
    main = State()       # Manager main
    crm = State()        # CRM tools
    confirm = State()    # HITL confirmation

# Sub-dialog result handling:
async def on_confirmation_result(start_data, result, manager: DialogManager):
    if result.get("confirmed"):
        # execute CRM action
        pass

dialog = Dialog(
    Window(
        Const("Главное меню"),
        Row(
            SwitchTo(Const("Поиск"), id="search", state=ClientMenuSG.search),
            SwitchTo(Const("История"), id="history", state=ClientMenuSG.history),
        ),
        state=ClientMenuSG.main,
    ),
    ...
    on_process_result=on_confirmation_result,
)
```

**Role separation (client vs manager):** Use separate `StatesGroup` hierarchies and
separate `Dialog` objects. Role check in dialog `on_start` via `manager.middleware_data`.
This avoids shared state pollution between user roles.

**What NOT to do:** Do not build menu navigation with raw aiogram InlineKeyboardMarkup +
callback_query handlers — it does not scale to multi-step flows and lacks FSM state
management. aiogram-dialog is the correct abstraction.

---

### 5. HITL Confirmation (#443)

**No new dependencies. LangGraph interrupt + aiogram-dialog sub-dialog.**

Two complementary patterns depending on context:

#### Pattern A: LangGraph `interrupt()` — for pipeline actions (CRM writes, lead creation)

```python
# In CRM tool or graph node:
from langgraph.types import interrupt

async def crm_create_lead_with_approval(state, config):
    payload = state["pending_lead"]
    decision = interrupt({
        "action": "create_lead",
        "preview": payload,
        "prompt": "Создать сделку?"
    })
    if decision:
        result = await kommo_client.create_lead(payload)
        return {"lead_created": True, "lead_id": result["id"]}
    return {"lead_created": False}
```

**Resume from Telegram callback:**
```python
# In aiogram callback handler — user pressed "Yes"
await graph.ainvoke(
    Command(resume=True),
    config={"configurable": {"thread_id": thread_id}}
)
```

#### Pattern B: aiogram-dialog sub-dialog — for menu-driven confirmations

```python
class ConfirmSG(StatesGroup):
    confirm = State()

async def on_yes(callback, button, manager: DialogManager):
    await manager.done(result={"confirmed": True})

async def on_no(callback, button, manager: DialogManager):
    await manager.done(result={"confirmed": False})

confirm_dialog = Dialog(
    Window(
        Format("Подтвердить: {dialog_data[action]}?"),
        Row(
            Button(Const("Да"), id="yes", on_click=on_yes),
            Button(Const("Нет"), id="no", on_click=on_no),
        ),
        state=ConfirmSG.confirm,
    )
)
```

**Decision:** Use Pattern B (aiogram-dialog sub-dialog) for menu-triggered confirmations
(manager approving CRM actions from the menu). Use Pattern A (LangGraph interrupt) for
conversational HITL where the bot is mid-pipeline. Both patterns are complementary.

**Confidence:** HIGH — both patterns verified via Context7.

---

### 6. i18n (#444)

**`fluentogram 1.2.1` is already in stack. No new dependency needed.**

| Technology | Version | Purpose | Why Recommended |
|------------|---------|---------|-----------------|
| `fluentogram` | `1.2.1` (existing) | Fluent (.ftl) i18n, stub generator, aiogram3 integration | Production-ready, Aiogram3-specific, precompiled Fluent via `fluent_compiler`. Type-safe dot-access (`translator.menu.search()`). CLI stub generator for IDE autocomplete. Last release Jul 2025. |

**Comparison with alternatives:**

| Library | Use When |
|---------|----------|
| `fluentogram 1.2.1` | Aiogram3 + type-safe stubs + precompiled FTL — already in stack, correct choice |
| `aiogram-i18n 1.4` | Needed if you want gettext OR fluent + built-in middleware wiring + multiple backends. More configuration, slightly less opinionated. |
| `aiogram built-in i18n` | SimpleI18nMiddleware (auto-detect from User object) or FSMI18nMiddleware (persist in FSM) — use only for GNU gettext, not Fluent |

**Decision: Stay with `fluentogram`.** The project already has it. aiogram-i18n adds no
value unless the team needs gettext fallback, which this project does not.

**Key integration pattern (verified via GitHub + PyPI):**

```python
# locales/ru/main.ftl
menu-main = Главное меню
menu-search = Поиск по базе
menu-history = История чата
crm-confirm = Подтвердить действие: { $action }?

# In aiogram-dialog window:
from aiogram_dialog.widgets.text import Format
Window(
    Format("{menu_main}"),  # value from fluentogram translator passed via getter
    ...
)
```

**Locale storage:** Use `FSMI18nMiddleware` (aiogram built-in) or fluentogram's
`FileStorage` + middleware for per-user locale persistence in Redis/FSM.

---

## Supporting Libraries Summary

| Library | Version | Added? | Purpose |
|---------|---------|--------|---------|
| `respx` | `0.22.0` | NEW (dev) | httpx mock for KommoClient tests |
| `langgraph` | `>=1.0.3` | existing | HITL interrupt pattern |
| `aiogram-dialog` | `2.4.0` | existing | Menu system, HITL sub-dialogs |
| `fluentogram` | `1.2.1` | existing | i18n Fluent .ftl |
| `telethon` | `>=1.42.0` | existing (dev) | E2E Telegram tests via userbot |

---

## E2E Testing Stack

**Already in stack: `telethon>=1.42.0` (dev dependency).**

| Technology | Version | Purpose | Why Recommended |
|------------|---------|---------|-----------------|
| `telethon` | `>=1.42.0` (existing) | E2E bot testing via Telegram MTProto userbot | Industry standard for Telegram bot E2E tests. `StringSession` enables CI/CD (session in env var, no database). Sequential updates for deterministic test ordering. Already in dev deps. |
| `pytest-asyncio` | `>=1.2.0` (existing) | Async test support | Required for Telethon async conversation API. |

**Pattern (verified via multiple sources — established 2025 community pattern):**

```python
# conftest.py
from telethon import TelegramClient
from telethon.sessions import StringSession
import pytest

@pytest.fixture(scope="session")
async def tg_client():
    client = TelegramClient(
        StringSession(os.environ["TELEGRAM_STRING_SESSION"]),
        api_id=int(os.environ["TELEGRAM_API_ID"]),
        api_hash=os.environ["TELEGRAM_API_HASH"],
    )
    await client.connect()
    yield client
    await client.disconnect()

# test_bot_e2e.py
async def test_start_command(tg_client):
    async with tg_client.conversation("@YourBot", timeout=10) as conv:
        await conv.send_message("/start")
        response = await conv.get_response()
        assert "Главное меню" in response.text
```

**CI consideration:** Store `TELEGRAM_STRING_SESSION` as a CI secret. Use `max_messages=10000`
in conversations to avoid ValueError on long test sessions.

---

## Installation (New Dependencies Only)

```bash
# Only new addition:
uv add respx --dev

# All existing deps already in pyproject.toml — no changes needed
```

---

## Alternatives Considered

| Recommended | Alternative | Why Not |
|-------------|-------------|---------|
| `respx 0.22.0` | `pytest-httpx` (existing) | pytest-httpx patches transport globally; respx is route-based and better for class-wrapped clients like KommoClient. Both valid — use respx for complex KommoClient tests. |
| `respx 0.22.0` | `unittest.mock.patch.object` (existing) | Current approach works but is brittle (patches internal `_client.request`). respx gives assertable routes, response side effects, and call verification without touching internals. |
| `fluentogram` (existing) | `aiogram-i18n` | aiogram-i18n is better if you need gettext fallback or multiple i18n backends. This project uses only Fluent and fluentogram is already wired. Switching = unnecessary migration. |
| LangGraph `interrupt()` | Custom Redis-backed approval queue | interrupt() is built into LangGraph checkpointing — no extra queue infra needed. The `Command(resume=...)` pattern is the 2025-2026 standard. |
| aiogram-dialog 2.4.0 | Raw InlineKeyboardMarkup | Raw keyboards don't provide FSM state management, window composition, or sub-dialog result routing. aiogram-dialog is the correct abstraction for multi-step menus. |
| guard_node at sub-graph START | Global HTTP middleware | LangGraph nodes are the correct boundary for input validation — middleware runs outside graph context and can't access graph state. Guard as first node is the 2025 recommended pattern. |

---

## What NOT to Use

| Avoid | Why | Use Instead |
|-------|-----|-------------|
| `llm-guard` (DeBERTa) on hot path | 100-200ms CPU latency, ~450MB model weight per request. Kills UX for synchronous Telegram responses. | Existing regex guard (< 1ms). Keep DeBERTa opt-in via `GUARD_ML_ENABLED=true` for async moderation workflows. |
| `aiogram-dialog` v1.x | Targets aiogram v2.x (EOL). API is incompatible with aiogram 3.25. | aiogram-dialog 2.4.0 (v2.x series supports aiogram v3.x). |
| `langchain.agents` `create_react_agent` for inner RAG | Replaces the structured 11-node LangGraph pipeline with an unstructured ReAct loop. Loses deterministic routing, caching nodes, and Langfuse observability spans. | Keep existing `build_graph()` StateGraph for RAG pipeline; `create_bot_agent` (SDK) for the outer supervisor. |
| `APScheduler v4` | Breaking API changes from v3. Existing code uses v3 API (`apscheduler>=3.11.2,<4.0`). | APScheduler v3.x (pinned `<4.0` in pyproject.toml). |
| New vector DB or embedding provider | BGE-M3 + Qdrant is production-tuned (gRPC, batch, ColBERT rerank). Migration cost >> benefit. | Existing BGE-M3 + Qdrant stack. |

---

## Stack Patterns by Scenario

**If adding a new CRM tool that requires manager approval:**
- Tool executes LangGraph `interrupt()` with action preview
- Telegram HITL handler resumes with `Command(resume=bool)`
- No new dependencies

**If adding a new menu screen:**
- Add `State` to existing `StatesGroup` or create a new one
- New `Window` in existing `Dialog`
- Use `SwitchTo` / `Back` widgets for navigation
- Pass data via `manager.dialog_data` or `manager.start()` + `manager.done(result=...)`

**If adding a new locale (e.g., UA):**
- Create `locales/uk/main.ftl`
- Register in fluentogram `FileStorage`
- Set locale via `FSMI18nMiddleware.set_locale(state, "uk")`

**If writing a new KommoClient test:**
- Use `respx.mock(base_url="https://testcompany.kommo.com")` fixture
- Define routes with `.return_value = httpx.Response(200, json=...)`
- Assert `mock["route_name"].called` and call count

---

## Version Compatibility

| Package A | Compatible With | Notes |
|-----------|-----------------|-------|
| `aiogram-dialog 2.4.0` | `aiogram 3.25.0` | v2.x series targets aiogram v3.x. Verified on PyPI Jul 2025. |
| `fluentogram 1.2.1` | `aiogram 3.25.0` | Optional `aiogram` extra. Jul 2025 release. |
| `langgraph 1.0.3` | `langgraph-checkpoint-redis 0.2.0` | 1.0.x checkpoint protocol. Pin `<2.0` to avoid breaking changes. |
| `respx 0.22.0` | `httpx >=0.25` (existing has `httpx>=0.27.0`) | Compatible. No conflict. |
| `telethon 1.42.0` | `pytest-asyncio 1.2.0` | Async session fixtures work. Use `scope="session"` carefully with xdist. |

---

## Sources

- Context7 `/websites/aiogram-dialog_readthedocs_io_en_stable` — Window widgets, transitions, sub-dialogs, on_process_result (HIGH)
- Context7 `/websites/langchain_oss_python_langgraph` — interrupt(), Command(resume=), HITL patterns (HIGH)
- Context7 `/langchain-ai/langgraph` — StateGraph RAG patterns, streaming (HIGH)
- Context7 `/lundberg/respx` — Pytest fixture patterns, async mock (HIGH)
- Context7 `/aiogram/aiogram` — FSMI18nMiddleware, SimpleI18nMiddleware (HIGH)
- PyPI `aiogram-dialog 2.4.0` — current version, Python >=3.9, aiogram v3.x (HIGH)
- PyPI `fluentogram 1.2.1` — current version, Jul 2025 (HIGH)
- PyPI `respx 0.22.0` — current version, Dec 2024, httpx >=0.25 (HIGH)
- GitHub `Arustinal/fluentogram` — features, dot-access API, FileStorage, CLI stubs (MEDIUM)
- WebSearch — Telethon StringSession E2E CI pattern, guard node security architecture (MEDIUM)
- Existing codebase — `telegram_bot/graph/nodes/guard.py`, `telegram_bot/agents/crm_tools.py`, `pyproject.toml` (HIGH, authoritative)

---

*Stack research for: Production RAG + CRM Telegram bot — subsequent milestone (simplified pipeline, CRM tests, guard coverage, menu system, HITL, i18n)*
*Researched: 2026-02-19*

# SDK Migration Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Migrate from LangChain/LangGraph to SDK-first stack: dishka DI + pydantic-ai agent + pydantic-graph voice + aiogram Routers + CallbackData factories.

**Architecture:** PropertyBot god-object (3400 LOC) decomposes into modular aiogram Routers with dishka DI. LangChain `create_agent()` → pydantic-ai Agent. LangGraph 11-node voice pipeline → pydantic-graph BaseNode subclasses. All callback f-string parsing → typed CallbackData factories.

**Tech Stack:** aiogram 3.25+, dishka 1.8, pydantic-ai, pydantic-graph, litellm, aiogram-dialog 2.5

**Design:** `docs/plans/2026-03-03-sdk-migration-design.md`

---

## Phase 1: Dependencies + dishka DI Container (2 days)

### Task 1: Update dependencies

**Files:**
- Modify: `pyproject.toml` (root)

**Step 1: Add new dependencies**

```toml
# After "pydantic-settings>=2.12.0", add:
"dishka>=1.8.0",
"pydantic-ai>=0.1.0",
```

**Step 2: Run sync**

Run: `uv sync`
Expected: Dependencies install without conflicts

**Step 3: Verify imports work**

Run: `python -c "from dishka import make_async_container, Provider, provide, Scope; print('dishka OK')"`
Run: `python -c "from pydantic_ai import Agent; print('pydantic-ai OK')"`
Run: `python -c "from pydantic_graph import Graph, BaseNode, End, GraphRunContext; print('pydantic-graph OK')"`
Expected: All print OK

**Step 4: Commit**

```bash
git add pyproject.toml uv.lock
git commit -m "chore(deps): add dishka and pydantic-ai for SDK migration"
```

---

### Task 2: Create dishka Provider (APP scope)

**Files:**
- Create: `telegram_bot/di/__init__.py`
- Create: `telegram_bot/di/providers.py`
- Test: `tests/unit/di/test_providers.py`

**Step 1: Write failing test**

```python
# tests/unit/di/test_providers.py
"""Tests for dishka DI providers."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from dishka import make_async_container, Scope

from telegram_bot.di.providers import AppProvider, RequestProvider


@pytest.mark.asyncio
async def test_app_provider_creates_cache():
    """APP scope provider creates CacheLayerManager."""
    with patch("telegram_bot.di.providers.CacheLayerManager") as mock_cache:
        mock_instance = AsyncMock()
        mock_cache.return_value = mock_instance
        container = make_async_container(AppProvider())
        async with container() as request_container:
            from telegram_bot.integrations.cache import CacheLayerManager
            cache = await request_container.get(CacheLayerManager)
            assert cache is mock_instance
        await container.close()
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/di/test_providers.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'telegram_bot.di'`

**Step 3: Create `__init__.py`**

```python
# telegram_bot/di/__init__.py
"""Dishka dependency injection providers."""
```

**Step 4: Write APP scope provider**

```python
# telegram_bot/di/providers.py
"""Dishka providers for bot services."""
from __future__ import annotations

from collections.abc import AsyncIterator

from dishka import Provider, Scope, provide

from telegram_bot.config import BotConfig
from telegram_bot.integrations.cache import CacheLayerManager
from telegram_bot.integrations.embeddings import BGEM3HybridEmbeddings
from telegram_bot.services.bge_m3_client import BGEM3Client
from telegram_bot.services.qdrant import QdrantService


class AppProvider(Provider):
    """APP-scoped providers — singleton lifetime, created once at startup."""

    scope = Scope.APP

    @provide
    def config(self) -> BotConfig:
        return BotConfig()

    @provide
    def bge_m3_client(self, config: BotConfig) -> BGEM3Client:
        return BGEM3Client(base_url=config.bge_m3_url)

    @provide
    def embeddings(self, config: BotConfig) -> BGEM3HybridEmbeddings:
        return BGEM3HybridEmbeddings(base_url=config.bge_m3_url)

    @provide
    async def cache(self, config: BotConfig) -> AsyncIterator[CacheLayerManager]:
        cache = CacheLayerManager(
            redis_url=config.redis_url,
            bge_m3_url=config.bge_m3_url,
        )
        await cache.initialize()
        yield cache

    @provide
    def qdrant(self, config: BotConfig) -> QdrantService:
        return QdrantService(
            url=config.qdrant_url,
            collection_name=config.qdrant_collection,
        )


class RequestProvider(Provider):
    """REQUEST-scoped providers — per Telegram update lifecycle."""

    scope = Scope.REQUEST
    # Filled in Task 3
```

**Step 5: Run test**

Run: `uv run pytest tests/unit/di/test_providers.py -v`
Expected: PASS

**Step 6: Commit**

```bash
git add telegram_bot/di/ tests/unit/di/
git commit -m "feat(di): add dishka AppProvider with core service providers"
```

---

### Task 3: Strip I18nMiddleware to i18n-only

**Files:**
- Modify: `telegram_bot/middlewares/i18n.py`
- Test: `tests/unit/middlewares/test_i18n_stripped.py`

**Step 1: Write failing test**

```python
# tests/unit/middlewares/test_i18n_stripped.py
"""Test that I18nMiddleware only injects i18n, not services."""
import pytest
from unittest.mock import AsyncMock, MagicMock

from telegram_bot.middlewares.i18n import I18nMiddleware


@pytest.mark.asyncio
async def test_i18n_middleware_only_injects_locale_and_translator():
    """I18nMiddleware should ONLY inject 'i18n' and 'locale', not services."""
    hub = MagicMock()
    translator = MagicMock()
    hub.get_translator_by_locale.return_value = translator

    middleware = I18nMiddleware(hub=hub)

    handler = AsyncMock()
    event = MagicMock()
    event.from_user = MagicMock(language_code="ru")

    data: dict = {}
    await middleware(handler, event, data)

    # MUST inject i18n and locale
    assert "i18n" in data
    assert "locale" in data

    # MUST NOT inject services (these move to dishka)
    assert "user_service" not in data
    assert "kommo_client" not in data
    assert "property_bot" not in data
    assert "apartments_service" not in data
    assert "favorites_service" not in data

    handler.assert_awaited_once()
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/middlewares/test_i18n_stripped.py -v`
Expected: FAIL — middleware still injects services

**Step 3: Refactor I18nMiddleware**

Read `telegram_bot/middlewares/i18n.py` and strip `__init__` to only accept `hub: TranslatorHub`. Remove all service parameters. `__call__` should only set `data["i18n"]` and `data["locale"]`.

**Step 4: Run test**

Run: `uv run pytest tests/unit/middlewares/test_i18n_stripped.py -v`
Expected: PASS

**Step 5: Run full test suite to catch regressions**

Run: `uv run pytest tests/unit/ -x --timeout=30`
Expected: Some tests will fail where handlers expect services from middleware data — note these for Phase 2

**Step 6: Commit**

```bash
git add telegram_bot/middlewares/i18n.py tests/unit/middlewares/test_i18n_stripped.py
git commit -m "refactor(i18n): strip I18nMiddleware to i18n-only — services move to dishka"
```

---

## Phase 2: Router Decomposition (3 days)

### Task 4: Create commands router

**Files:**
- Create: `telegram_bot/routers/__init__.py`
- Create: `telegram_bot/routers/commands.py`
- Test: `tests/unit/routers/test_commands.py`

**Step 1: Write failing test**

```python
# tests/unit/routers/test_commands.py
"""Tests for commands router."""
import pytest
from aiogram import Router
from telegram_bot.routers.commands import router as commands_router


def test_commands_router_is_router():
    assert isinstance(commands_router, Router)


def test_commands_router_has_start_handler():
    """Router should have /start handler registered."""
    handler_names = [
        h.callback.__name__
        for h in commands_router.message.handlers
    ]
    assert "cmd_start" in handler_names
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/routers/test_commands.py -v`
Expected: FAIL — module not found

**Step 3: Extract commands from PropertyBot**

```python
# telegram_bot/routers/__init__.py
"""Aiogram routers — modular handler decomposition."""

# telegram_bot/routers/commands.py
"""Command handlers: /start, /help, /clear, /stats, /metrics, /call, /history, /clearcache."""
from __future__ import annotations

import logging

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message
from dishka.integrations.aiogram import FromDishka

from telegram_bot.services.user_service import UserService

logger = logging.getLogger(__name__)

router = Router(name="commands")


@router.message(Command("start"))
async def cmd_start(
    message: Message,
    user_service: FromDishka[UserService],
) -> None:
    """Handle /start command."""
    if message.from_user:
        await user_service.ensure_exists(message.from_user)
    await message.answer("Добро пожаловать!")


@router.message(Command("help"))
async def cmd_help(message: Message) -> None:
    """Handle /help command."""
    await message.answer("Используйте меню или задайте вопрос текстом.")


@router.message(Command("clear"))
async def cmd_clear(message: Message) -> None:
    """Handle /clear command — reset conversation."""
    await message.answer("История очищена.")
```

NOTE: This is a skeleton. Full implementation copies logic from `bot.py` cmd_start (line ~766), cmd_help (~846), cmd_clear (~870), etc. Each command handler references services via `FromDishka[ServiceType]` instead of `self._service`.

**Step 4: Run test**

Run: `uv run pytest tests/unit/routers/test_commands.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add telegram_bot/routers/ tests/unit/routers/
git commit -m "feat(routers): extract commands router from PropertyBot"
```

---

### Task 5: Create voice router

**Files:**
- Create: `telegram_bot/routers/voice.py`
- Test: `tests/unit/routers/test_voice.py`

Extract `handle_voice()` from `bot.py:2855` into `routers/voice.py`. Services injected via `FromDishka[]`. Voice graph invoked via `FromDishka[Graph]` (pydantic-graph — wired in Phase 6). Initially, keep LangGraph invocation as-is; Phase 6 replaces.

**Step 1-5:** Same TDD pattern as Task 4.

**Commit:** `feat(routers): extract voice router from PropertyBot`

---

### Task 6: Create menu router

**Files:**
- Create: `telegram_bot/routers/menu.py`
- Test: `tests/unit/routers/test_menu.py`

Extract `handle_menu_button()` from `bot.py:1042`. 6 menu actions dispatched by text match.

**Commit:** `feat(routers): extract menu router from PropertyBot`

---

### Task 7: Create query router (catch-all text)

**Files:**
- Create: `telegram_bot/routers/query.py`
- Test: `tests/unit/routers/test_query.py`

Extract `handle_query()` → `_handle_query_supervisor()` → dual-path (client direct + agent SDK). This is the most complex router — must be registered LAST (after menu, commands, FSM).

**Commit:** `feat(routers): extract query router from PropertyBot`

---

### Task 8: Create factory.py (bot assembly)

**Files:**
- Create: `telegram_bot/factory.py`
- Modify: `telegram_bot/main.py`
- Test: `tests/unit/test_factory.py`

**Step 1: Write failing test**

```python
# tests/unit/test_factory.py
"""Tests for bot factory."""
import pytest
from unittest.mock import patch, MagicMock

from aiogram import Bot, Dispatcher


@pytest.mark.asyncio
async def test_create_bot_returns_bot_and_dispatcher():
    from telegram_bot.factory import create_bot
    from telegram_bot.config import BotConfig

    with patch.object(BotConfig, "__init__", lambda self: None):
        config = BotConfig.__new__(BotConfig)
        config.telegram_token = "test:token"
        config.redis_url = "redis://localhost:6379"
        config.bge_m3_url = "http://localhost:8000"
        config.qdrant_url = "http://localhost:6333"
        config.qdrant_collection = "test"
        config.admin_ids = []

        bot, dp = await create_bot(config)
        assert isinstance(bot, Bot)
        assert isinstance(dp, Dispatcher)
        await bot.session.close()
```

**Step 2: Implement factory**

```python
# telegram_bot/factory.py
"""Bot factory: creates Bot + Dispatcher + dishka container + routers."""
from __future__ import annotations

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from dishka import make_async_container
from dishka.integrations.aiogram import setup_dishka, AiogramProvider

from telegram_bot.config import BotConfig
from telegram_bot.di.providers import AppProvider, RequestProvider
from telegram_bot.middlewares.throttling import setup_throttling_middleware
from telegram_bot.routers.commands import router as commands_router
from telegram_bot.routers.voice import router as voice_router
from telegram_bot.routers.menu import router as menu_router
from telegram_bot.routers.query import router as query_router


async def create_bot(config: BotConfig) -> tuple[Bot, Dispatcher]:
    """Create bot with dishka DI container and modular routers."""
    bot = Bot(
        token=config.telegram_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = Dispatcher()

    # DI container
    container = make_async_container(
        AppProvider(), RequestProvider(), AiogramProvider(),
    )
    setup_dishka(container=container, router=dp, auto_inject=True)
    dp.shutdown.register(container.close)

    # Middleware
    setup_throttling_middleware(dp, rate_limit=1.5, admin_ids=config.admin_ids)

    # Error handler
    from telegram_bot.routers.errors import register_error_handlers
    register_error_handlers(dp)

    # Routers (ORDER MATTERS — FSM first, catch-all last)
    from telegram_bot.handlers.phone_collector import create_phone_router
    from telegram_bot.handlers.handoff import create_handoff_router

    dp.include_router(create_phone_router())
    dp.include_router(create_handoff_router())
    dp.include_router(commands_router)
    dp.include_router(voice_router)
    dp.include_router(menu_router)
    # callback routers (Phase 3)
    dp.include_router(query_router)  # LAST — catch-all

    return bot, dp
```

**Step 3: Update main.py**

```python
# telegram_bot/main.py — updated entry point
async def main():
    config = BotConfig()
    initialize_langfuse(...)
    bot, dp = await create_bot(config)

    try:
        await dp.start_polling(bot)
    finally:
        await bot.session.close()
```

**Step 4: Commit**

```bash
git add telegram_bot/factory.py telegram_bot/main.py tests/unit/test_factory.py
git commit -m "feat(factory): bot assembly with dishka DI + modular routers"
```

---

## Phase 3: CallbackData Factories (1 day)

### Task 9: Create typed callback models

**Files:**
- Create: `telegram_bot/callbacks/models.py`
- Test: `tests/unit/callbacks/test_models.py`

**Step 1: Write test**

```python
# tests/unit/callbacks/test_models.py
from telegram_bot.callbacks.models import FeedbackCallback, FavoriteCallback


def test_feedback_callback_pack_unpack():
    cb = FeedbackCallback(action="like", trace_id="abc123")
    packed = cb.pack()
    assert packed.startswith("fb:")
    unpacked = FeedbackCallback.unpack(packed)
    assert unpacked.action == "like"
    assert unpacked.trace_id == "abc123"


def test_favorite_callback_pack_unpack():
    cb = FavoriteCallback(action="add", item_id="apt_42")
    packed = cb.pack()
    assert packed.startswith("fav:")
    unpacked = FavoriteCallback.unpack(packed)
    assert unpacked.action == "add"
    assert unpacked.item_id == "apt_42"
```

**Step 2: Implement models**

```python
# telegram_bot/callbacks/models.py
"""Typed CallbackData factories — replaces f-string parsing."""
from aiogram.filters.callback_data import CallbackData


class FeedbackCallback(CallbackData, prefix="fb"):
    action: str      # "like" | "dislike" | "done"
    trace_id: str = ""


class ServiceCallback(CallbackData, prefix="svc"):
    action: str      # service key or "back" | "menu"


class CtaCallback(CallbackData, prefix="cta"):
    action: str      # "get_offer" | "manager"
    service_key: str = ""


class FavoriteCallback(CallbackData, prefix="fav"):
    action: str      # "add" | "remove" | "viewing" | "viewing_all"
    item_id: str = ""


class ResultsCallback(CallbackData, prefix="results"):
    action: str      # "more" | "refine" | "viewing"
    offset: int = 0


class HitlCallback(CallbackData, prefix="hitl"):
    action: str      # "approve" | "reject"
    request_id: str = ""


class ClearCacheCallback(CallbackData, prefix="cc"):
    tier: str = "all"


class CardCallback(CallbackData, prefix="card"):
    item_id: str


class AskCallback(CallbackData, prefix="ask"):
    question_id: str
```

**Step 3: Run test, commit**

```bash
git add telegram_bot/callbacks/ tests/unit/callbacks/
git commit -m "feat(callbacks): typed CallbackData factories for all 9 prefixes"
```

---

### Task 10: Create callback routers using CallbackData.filter()

**Files:**
- Create: `telegram_bot/routers/callbacks/feedback.py`
- Create: `telegram_bot/routers/callbacks/favorites.py`
- Create: `telegram_bot/routers/callbacks/services.py`
- Create: `telegram_bot/routers/callbacks/results.py`
- Create: `telegram_bot/routers/callbacks/cta.py`
- Create: `telegram_bot/routers/callbacks/hitl.py`
- Test: `tests/unit/routers/callbacks/test_feedback.py`

Extract each callback handler from `bot.py` into its own router using `CallbackData.filter()` instead of `F.data.startswith("prefix:")`.

**Example — feedback router:**

```python
# telegram_bot/routers/callbacks/feedback.py
from aiogram import Router, F
from aiogram.types import CallbackQuery
from dishka.integrations.aiogram import FromDishka

from telegram_bot.callbacks.models import FeedbackCallback

router = Router(name="feedback")


@router.callback_query(FeedbackCallback.filter(F.action == "done"))
async def feedback_done(callback: CallbackQuery) -> None:
    await callback.answer()


@router.callback_query(FeedbackCallback.filter())
async def handle_feedback(
    callback: CallbackQuery,
    callback_data: FeedbackCallback,
) -> None:
    """Handle like/dislike feedback — write Langfuse score."""
    value = 1.0 if callback_data.action == "like" else 0.0
    trace_id = callback_data.trace_id

    await callback.answer("Спасибо за отзыв!")

    from langfuse import get_client as get_langfuse_client
    lf = get_langfuse_client()
    if lf and trace_id:
        lf.create_score(
            trace_id=trace_id,
            name="user_feedback",
            value=value,
            data_type="NUMERIC",
        )
```

**Same pattern for each callback prefix.** One router per domain, registered in `factory.py`.

**Commit:** `feat(callbacks): extract all callback routers with CallbackData.filter()`

---

## Phase 4: pydantic-ai Agent (3 days)

### Task 11: Create BotDeps typed dataclass

**Files:**
- Create: `telegram_bot/agent/deps.py`
- Test: `tests/unit/agent/test_deps.py`

**Step 1: Write test**

```python
# tests/unit/agent/test_deps.py
from telegram_bot.agent.deps import BotDeps


def test_bot_deps_requires_core_fields():
    deps = BotDeps(
        telegram_user_id=123,
        session_id="test",
        language="ru",
        cache=None,
        embeddings=None,
        qdrant=None,
    )
    assert deps.telegram_user_id == 123
    assert deps.role == "client"
```

**Step 2: Implement**

```python
# telegram_bot/agent/deps.py
"""Typed dependencies for pydantic-ai agent."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class BotDeps:
    """Runtime dependencies injected into agent tools via RunContext[BotDeps]."""

    telegram_user_id: int
    session_id: str
    language: str
    cache: Any  # CacheLayerManager
    embeddings: Any  # BGEM3HybridEmbeddings
    qdrant: Any  ***REMOVED***Service
    reranker: Any | None = None
    kommo_client: Any | None = None
    llm: Any | None = None
    role: str = "client"
    apartments_service: Any | None = None
    history_service: Any | None = None
    bot: Any | None = None  # aiogram Bot (for handoff)
    manager_ids: list[int] = field(default_factory=list)
```

**Step 3: Run test, commit**

```bash
git add telegram_bot/agent/ tests/unit/agent/
git commit -m "feat(agent): add BotDeps typed dataclass for pydantic-ai"
```

---

### Task 12: Create pydantic-ai Agent with RAG tool

**Files:**
- Create: `telegram_bot/agent/bot_agent.py`
- Create: `telegram_bot/agent/tools/rag.py`
- Test: `tests/unit/agent/test_bot_agent.py`

**Step 1: Write failing test**

```python
# tests/unit/agent/test_bot_agent.py
import pytest
from unittest.mock import AsyncMock, MagicMock

from pydantic_ai import Agent

from telegram_bot.agent.bot_agent import create_bot_agent
from telegram_bot.agent.deps import BotDeps


def test_create_bot_agent_returns_pydantic_agent():
    agent = create_bot_agent(model="test")
    assert isinstance(agent, Agent)


@pytest.mark.asyncio
async def test_agent_has_rag_search_tool():
    agent = create_bot_agent(model="test")
    tool_names = [t.name for t in agent._tools]
    assert "rag_search" in tool_names
```

**Step 2: Implement agent factory**

```python
# telegram_bot/agent/bot_agent.py
"""Pydantic-AI agent factory — replaces LangChain create_agent()."""
from __future__ import annotations

from pydantic_ai import Agent

from telegram_bot.agent.deps import BotDeps
from telegram_bot.agent.tools.rag import rag_search
from telegram_bot.agent.tools.history import history_search
from telegram_bot.agent.tools.crm import (
    crm_get_deal, crm_create_lead, crm_update_lead,
    crm_upsert_contact, crm_add_note, crm_create_task,
    crm_link_contact_to_deal,
)
from telegram_bot.agent.tools.utility import mortgage_calculator, handoff


def create_bot_agent(
    *,
    model: str = "openai:gpt-oss-120b",
    system_prompt: str | None = None,
) -> Agent[BotDeps, str]:
    """Create pydantic-ai agent with typed tools and DI."""
    prompt = system_prompt or _default_system_prompt()

    agent: Agent[BotDeps, str] = Agent(
        model=model,
        deps_type=BotDeps,
        output_type=str,
        system_prompt=prompt,
    )

    # Register tools
    agent.tool()(rag_search)
    agent.tool()(history_search)
    agent.tool(requires_approval=True)(crm_create_lead)
    agent.tool(requires_approval=True)(crm_update_lead)
    agent.tool()(crm_get_deal)
    agent.tool()(crm_upsert_contact)
    agent.tool()(crm_add_note)
    agent.tool()(crm_create_task)
    agent.tool()(crm_link_contact_to_deal)
    agent.tool()(mortgage_calculator)
    agent.tool()(handoff)

    return agent


def _default_system_prompt() -> str:
    from telegram_bot.integrations.prompt_manager import get_prompt
    return get_prompt("client_agent", fallback="You are a helpful assistant.")
```

**Step 3: Implement RAG tool**

```python
# telegram_bot/agent/tools/rag.py
"""RAG search tool for pydantic-ai agent."""
from __future__ import annotations

from pydantic_ai import RunContext

from telegram_bot.agent.deps import BotDeps


async def rag_search(ctx: RunContext[BotDeps], query: str) -> str:
    """Search knowledge base for relevant information about the query."""
    from telegram_bot.agent.pipeline.rag_core import rag_pipeline

    result = await rag_pipeline(
        query=query,
        cache=ctx.deps.cache,
        embeddings=ctx.deps.embeddings,
        qdrant=ctx.deps.qdrant,
        reranker=ctx.deps.reranker,
    )
    return result.get("response", "Информация не найдена.")
```

**Step 4: Run tests, commit**

```bash
git add telegram_bot/agent/ tests/unit/agent/
git commit -m "feat(agent): pydantic-ai Agent with rag_search tool"
```

---

### Task 13: Migrate remaining tools (CRM, history, utility)

**Files:**
- Create: `telegram_bot/agent/tools/crm.py`
- Create: `telegram_bot/agent/tools/history.py`
- Create: `telegram_bot/agent/tools/utility.py`
- Create: `telegram_bot/agent/tools/apartments.py`
- Test: `tests/unit/agent/tools/test_crm.py`

Port each `@tool` function from `telegram_bot/agents/` to pydantic-ai style:
- Replace `config: RunnableConfig` → `ctx: RunContext[BotDeps]`
- Replace `config.get("configurable", {}).get("bot_context")` → `ctx.deps`
- CRM write tools: `requires_approval=True` for HITL

**Example CRM tool:**

```python
# telegram_bot/agent/tools/crm.py
async def crm_create_lead(ctx: RunContext[BotDeps], name: str, phone: str) -> str:
    """Create new lead in Kommo CRM. Requires manager approval."""
    if ctx.deps.kommo_client is None:
        return "CRM недоступен"
    lead = await ctx.deps.kommo_client.create_lead(name=name, phone=phone)
    return f"Лид #{lead.id} создан: {name}"
```

**Commit:** `feat(agent): migrate all 13 tools to pydantic-ai RunContext`

---

### Task 14: DRY — extract shared rag_core.py

**Files:**
- Create: `telegram_bot/agent/pipeline/rag_core.py`
- Modify: `telegram_bot/agents/rag_pipeline.py` (import from rag_core)
- Test: `tests/unit/agent/pipeline/test_rag_core.py`

Extract shared functions from `telegram_bot/agents/rag_pipeline.py` and `telegram_bot/graph/nodes/` (cache_check, retrieve, grade, rerank, rewrite) into `rag_core.py`. Both text path (pydantic-ai agent) and voice path (pydantic-graph) call these shared functions.

Addresses H1-H4 from audit #728 — eliminates ~300 LOC duplication.

**Commit:** `refactor(rag): extract shared pipeline functions to rag_core.py — DRY #728`

---

### Task 15: Wire Langfuse observability for pydantic-ai

**Files:**
- Create: `telegram_bot/agent/observe.py`
- Test: `tests/unit/agent/test_observe.py`

```python
# telegram_bot/agent/observe.py
"""Langfuse observability wrapper for pydantic-ai tools."""
from functools import wraps
from typing import Any, Callable

from langfuse.decorators import observe as langfuse_observe


def observe_tool(name: str):
    """Decorator to wrap pydantic-ai tool with Langfuse span."""
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        @langfuse_observe(name=name, capture_input=False, capture_output=False)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            return await func(*args, **kwargs)
        return wrapper
    return decorator
```

Apply to each tool: `@observe_tool("tool-rag-search")` before registration.

**Commit:** `feat(observability): Langfuse @observe wrapper for pydantic-ai tools`

---

## Phase 5: DRY rag_core.py (1 day)

### Task 16: Shared pipeline functions

Already covered in Task 14. This phase ensures both `rag_pipeline.py` (text) and voice nodes (graph) import from `rag_core.py`.

Verify: `uv run pytest tests/unit/agents/ tests/unit/graph/ -v`

**Commit:** `refactor(rag): wire both text and voice paths through rag_core.py`

---

## Phase 6: pydantic-graph Voice Pipeline (3 days)

### Task 17: Create RAGVoiceState dataclass

**Files:**
- Create: `telegram_bot/voice/state.py`
- Test: `tests/unit/voice/test_state.py`

**Step 1: Write test**

```python
# tests/unit/voice/test_state.py
from telegram_bot.voice.state import RAGVoiceState


def test_voice_state_defaults():
    state = RAGVoiceState(user_id=123, session_id="test")
    assert state.query == ""
    assert state.documents == []
    assert state.grade_confidence == 0.0
    assert state.max_rewrite_attempts == 1
```

**Step 2: Implement**

```python
# telegram_bot/voice/state.py
"""Typed state for pydantic-graph voice pipeline."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class RAGVoiceState:
    """Voice pipeline state — replaces LangGraph RAGState TypedDict."""

    user_id: int
    session_id: str
    query: str = ""
    input_type: str = "voice"
    voice_audio: bytes = b""
    voice_duration_s: float = 0.0
    stt_text: str = ""
    query_type: str = ""
    documents: list[dict[str, Any]] = field(default_factory=list)
    response: str = ""
    grade_confidence: float = 0.0
    cache_hit: bool = False
    max_rewrite_attempts: int = 1
    rewrite_count: int = 0
    query_embedding: list[float] | None = None
    sparse_embedding: dict[str, Any] | None = None
    rerank_applied: bool = False
    response_sent: bool = False
```

**Commit:** `feat(voice): add RAGVoiceState typed dataclass for pydantic-graph`

---

### Task 18: Implement voice nodes as BaseNode subclasses

**Files:**
- Create: `telegram_bot/voice/__init__.py`
- Create: `telegram_bot/voice/nodes/transcribe.py`
- Create: `telegram_bot/voice/nodes/guard.py`
- Create: `telegram_bot/voice/nodes/classify.py`
- Create: `telegram_bot/voice/nodes/cache.py`
- Create: `telegram_bot/voice/nodes/retrieve.py`
- Create: `telegram_bot/voice/nodes/grade.py`
- Create: `telegram_bot/voice/nodes/rerank.py`
- Create: `telegram_bot/voice/nodes/rewrite.py`
- Create: `telegram_bot/voice/nodes/generate.py`
- Create: `telegram_bot/voice/nodes/cache_store.py`
- Create: `telegram_bot/voice/nodes/respond.py`
- Test: `tests/unit/voice/nodes/test_guard.py`
- Test: `tests/unit/voice/nodes/test_grade.py`

**Example — GradeNode with conditional routing:**

```python
# telegram_bot/voice/nodes/grade.py
"""Grade retrieved documents by RRF confidence."""
from __future__ import annotations

from dataclasses import dataclass

from pydantic_graph import BaseNode, GraphRunContext, End

from telegram_bot.voice.state import RAGVoiceState


@dataclass
class GradeNode(BaseNode[RAGVoiceState]):
    """Grade documents and route: generate (high conf) | rerank (low) | rewrite (retry)."""

    async def run(
        self, ctx: GraphRunContext[RAGVoiceState]
    ) -> "GenerateNode | RerankNode | RewriteNode":
        from telegram_bot.voice.nodes.generate import GenerateNode
        from telegram_bot.voice.nodes.rerank import RerankNode
        from telegram_bot.voice.nodes.rewrite import RewriteNode

        if ctx.state.grade_confidence >= 0.018:
            return GenerateNode()

        if ctx.state.rewrite_count < ctx.state.max_rewrite_attempts:
            ctx.state.rewrite_count += 1
            return RewriteNode()

        return RerankNode()
```

**Each node calls shared functions from `rag_core.py`** — no duplication.

**Test pattern:**

```python
# tests/unit/voice/nodes/test_grade.py
import pytest
from telegram_bot.voice.state import RAGVoiceState
from telegram_bot.voice.nodes.grade import GradeNode
from telegram_bot.voice.nodes.generate import GenerateNode
from telegram_bot.voice.nodes.rerank import RerankNode
from telegram_bot.voice.nodes.rewrite import RewriteNode
from pydantic_graph import GraphRunContext
from unittest.mock import MagicMock


@pytest.mark.asyncio
async def test_grade_high_confidence_routes_to_generate():
    state = RAGVoiceState(user_id=1, session_id="t", grade_confidence=0.05)
    ctx = GraphRunContext(state=state, deps=MagicMock())
    result = await GradeNode().run(ctx)
    assert isinstance(result, GenerateNode)


@pytest.mark.asyncio
async def test_grade_low_confidence_routes_to_rewrite():
    state = RAGVoiceState(user_id=1, session_id="t", grade_confidence=0.005)
    ctx = GraphRunContext(state=state, deps=MagicMock())
    result = await GradeNode().run(ctx)
    assert isinstance(result, RewriteNode)


@pytest.mark.asyncio
async def test_grade_exhausted_rewrites_routes_to_rerank():
    state = RAGVoiceState(
        user_id=1, session_id="t", grade_confidence=0.005,
        rewrite_count=1, max_rewrite_attempts=1,
    )
    ctx = GraphRunContext(state=state, deps=MagicMock())
    result = await GradeNode().run(ctx)
    assert isinstance(result, RerankNode)
```

**Commit per batch:** `feat(voice): implement 11 BaseNode subclasses for pydantic-graph pipeline`

---

### Task 19: Assemble voice Graph + RedisStatePersistence

**Files:**
- Create: `telegram_bot/voice/graph.py`
- Create: `telegram_bot/voice/persistence.py`
- Test: `tests/unit/voice/test_graph.py`

```python
# telegram_bot/voice/graph.py
"""Voice pipeline graph — 11 nodes, conditional routing."""
from pydantic_graph import Graph

from telegram_bot.voice.nodes.transcribe import TranscribeNode
from telegram_bot.voice.nodes.guard import GuardNode
from telegram_bot.voice.nodes.classify import ClassifyNode
from telegram_bot.voice.nodes.cache import CacheCheckNode
from telegram_bot.voice.nodes.retrieve import RetrieveNode
from telegram_bot.voice.nodes.grade import GradeNode
from telegram_bot.voice.nodes.rerank import RerankNode
from telegram_bot.voice.nodes.rewrite import RewriteNode
from telegram_bot.voice.nodes.generate import GenerateNode
from telegram_bot.voice.nodes.cache_store import CacheStoreNode
from telegram_bot.voice.nodes.respond import RespondNode

voice_graph = Graph(
    nodes=[
        TranscribeNode, GuardNode, ClassifyNode,
        CacheCheckNode, RetrieveNode, GradeNode,
        RerankNode, RewriteNode, GenerateNode,
        CacheStoreNode, RespondNode,
    ],
)
```

**Commit:** `feat(voice): assemble pydantic-graph voice pipeline with 11 nodes`

---

## Phase 7: Error Handling + Cleanup (1 day)

### Task 20: Migrate ErrorHandlerMiddleware → dp.errors

**Files:**
- Create: `telegram_bot/routers/errors.py`
- Delete: `telegram_bot/middlewares/error_handler.py` (after migration)
- Test: `tests/unit/routers/test_errors.py`

```python
# telegram_bot/routers/errors.py
"""Global error handler via dp.errors — covers all event types."""
from aiogram import Dispatcher
from aiogram.types import ErrorEvent


def register_error_handlers(dp: Dispatcher) -> None:
    @dp.errors()
    async def global_error_handler(error_event: ErrorEvent) -> bool:
        import logging
        logger = logging.getLogger(__name__)
        logger.exception("Unhandled error", exc_info=error_event.exception)

        update = error_event.update
        if update.message:
            await update.message.answer("Произошла ошибка. Попробуйте позже.")
        elif update.callback_query:
            await update.callback_query.answer("Ошибка", show_alert=True)
        return True
```

**Commit:** `refactor(errors): migrate ErrorHandlerMiddleware to dp.errors`

---

### Task 21: Remove LangChain/LangGraph dependencies

**Files:**
- Modify: `pyproject.toml`

**Step 1: Remove deps**

```toml
# Remove these lines:
# "langchain-core>=...",
# "langchain-openai>=...",
# "langgraph>=...",
# "langgraph-checkpoint-redis>=...",
# "langmem>=...",
```

**Step 2: Run sync**

Run: `uv sync`

**Step 3: Verify no LangChain imports remain**

Run: `grep -r "from langchain" telegram_bot/ --include="*.py" | grep -v __pycache__`
Run: `grep -r "from langgraph" telegram_bot/ --include="*.py" | grep -v __pycache__`
Expected: Zero results (or only in deprecated files marked for deletion)

**Step 4: Commit**

```bash
git add pyproject.toml uv.lock
git commit -m "chore(deps): remove langchain and langgraph dependencies"
```

---

### Task 22: Delete PropertyBot class

**Files:**
- Delete or gut: `telegram_bot/bot.py` (keep only if legacy code needs transition)
- Delete: `telegram_bot/agents/agent.py` (replaced by `agent/bot_agent.py`)
- Delete: `telegram_bot/graph/graph.py` (replaced by `voice/graph.py`)
- Delete: `telegram_bot/graph/state.py` (replaced by `voice/state.py`)

**Step 1: Verify all functionality moved to routers**

Run: `grep -r "PropertyBot" telegram_bot/ --include="*.py" | grep -v __pycache__`
Ensure zero references outside deprecated files.

**Step 2: Delete files**

**Step 3: Run full test suite**

Run: `make check && uv run pytest tests/unit/ -n auto`
Expected: All pass

**Commit:** `refactor(bot): delete PropertyBot god-object — replaced by Routers + dishka`

---

## Phase 8: Integration Testing (2 days)

### Task 23: Golden-set voice pipeline comparison

**Files:**
- Create: `tests/integration/test_voice_golden_set.py`

Compare pydantic-graph voice pipeline output against LangGraph golden results for 5 representative queries. Ensure identical or near-identical responses.

**Commit:** `test(voice): golden-set regression tests for pydantic-graph pipeline`

---

### Task 24: Agent integration test with HITL

**Files:**
- Create: `tests/integration/test_agent_hitl.py`

Test that CRM write tools return `DeferredToolRequests`, and that resuming with approval/rejection produces correct output.

**Commit:** `test(agent): HITL integration test with Deferred Tools`

---

### Task 25: Full smoke test

**Files:**
- Create: `tests/integration/test_sdk_migration_smoke.py`

End-to-end smoke: bot creation → router registration → dishka container → agent invocation → callback handling.

Run: `make check && uv run pytest tests/ -n auto --timeout=60`
Expected: All pass

**Commit:** `test(integration): SDK migration smoke test`

---

## Verification Checklist

- [ ] `make check` passes (ruff + mypy)
- [ ] `uv run pytest tests/unit/ -n auto` — all pass
- [ ] `uv run pytest tests/integration/ -v` — all pass
- [ ] Zero `from langchain` / `from langgraph` imports
- [ ] `PropertyBot` class deleted
- [ ] All 9 callback prefixes use `CallbackData` factories
- [ ] `I18nMiddleware` has zero service dependencies
- [ ] dishka container manages all service lifecycle
- [ ] pydantic-ai agent handles text queries with HITL for CRM
- [ ] pydantic-graph voice pipeline produces golden-set results
- [ ] Langfuse traces show equivalent coverage

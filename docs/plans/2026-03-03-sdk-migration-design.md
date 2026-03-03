# Full SDK Migration Design: aiogram SDK-first Architecture

**Дата:** 2026-03-03
**Scope:** Полная миграция на SDK-решения — aiogram transport, DI, agent framework, voice pipeline
**Approach:** Big Bang — одна ветка, полный рефакторинг
**Predecessor:** Issue #728 (SDK Migration Audit), Issue #640 (Custom vs SDK)

---

## Executive Summary

Комплексная миграция на SDK-решения для устранения техдолга и масштабируемости:
- **PropertyBot god-object** (3400 LOC) → модульные aiogram Routers + dishka DI
- **LangChain agent SDK** → pydantic-ai (type-safe tool calling, Deferred Tools HITL)
- **LangGraph voice pipeline** (11 nodes) → pydantic-graph (единая экосистема)
- **Ручной callback parsing** → aiogram CallbackData factories
- **I18nMiddleware service locator** → dishka Provider scopes

**Результат:** Zero LangChain/LangGraph dependencies. Единый type-safe стек.

---

## Target Stack

```
Transport:     aiogram 3.25+ Routers + CallbackData factories
DI:            dishka 1.8 (APP + REQUEST scopes)
Complex UI:    aiogram-dialog 2.5 (funnel, wizards, CRM)
Agent:         pydantic-ai (tools, Deferred Tools HITL, structured output)
Voice:         pydantic-graph (11 nodes, conditional routing, state persistence)
LLM:           litellm (model-agnostic, OpenAI-compatible)
Cache:         CacheLayerManager (as-is — уже RedisVL SemanticCache внутри)
Embeddings:    BGE-M3 microservice (as-is — уже FlagEmbedding внутри)
Search:        QdrantService (as-is — justified custom, nested prefetch/ColBERT)
CRM:           KommoClient (as-is — нет Python SDK для Kommo)
Observability: Langfuse + custom @observe wrappers для pydantic-ai/graph
```

### Удаляемые зависимости

```
- langchain-core
- langchain-openai
- langchain (agents)
- langgraph
- langgraph-checkpoint
- langgraph-checkpoint-redis (custom)
```

### Добавляемые зависимости

```
+ dishka>=1.8.0
+ pydantic-ai>=0.1.0 (включает pydantic-graph)
```

---

## Architecture: Before vs After

### Before

```
telegram_bot/
├── bot.py                    # 3400 LOC god-object (PropertyBot)
│   ├── __init__              # 40 instance vars, all services
│   ├── _setup_middlewares()   # middleware registration
│   ├── _register_handlers()   # 30+ handler registrations
│   ├── cmd_start/help/clear/...  # command handlers
│   ├── handle_query()         # text → dual-path routing
│   ├── handle_voice()         # voice → LangGraph invoke
│   ├── handle_menu_button()   # menu dispatch
│   ├── handle_*_callback()    # 9 callback prefixes, f-string parsing
│   └── ...
├── agents/
│   ├── agent.py              # LangChain create_agent() + ChatOpenAI
│   ├── context.py            # BotContext dataclass
│   ├── rag_tool.py           # @tool + RunnableConfig unpacking
│   ├── crm_tools.py          # 8 @tool + RunnableConfig
│   └── rag_pipeline.py       # 6-step async (duplicated with graph/)
├── graph/
│   ├── graph.py              # LangGraph StateGraph (11 nodes)
│   ├── state.py              # RAGState TypedDict (25 fields)
│   └── nodes/                # 11 node functions
├── middlewares/
│   ├── i18n.py               # DI container disguised as middleware
│   └── ...
└── handlers/
    ├── phone_collector.py    # FSM router
    └── handoff.py            # Callback router
```

### After

```
telegram_bot/
├── main.py                   # Entry point: create_bot() + dp.start_polling()
├── factory.py                # Bot + Dispatcher + dishka container setup
├── di/
│   ├── providers.py          # dishka Providers (APP + REQUEST scope)
│   └── scopes.py             # Custom scope definitions if needed
├── routers/
│   ├── commands.py           # Router: /start, /help, /clear, /stats, /call, /history
│   ├── voice.py              # Router: F.voice → pydantic-graph pipeline
│   ├── menu.py               # Router: ReplyKeyboard button dispatch
│   ├── callbacks/
│   │   ├── feedback.py       # Router: FeedbackCallback(prefix="fb")
│   │   ├── services.py       # Router: ServiceCallback(prefix="svc")
│   │   ├── favorites.py      # Router: FavoriteCallback(prefix="fav")
│   │   ├── results.py        # Router: ResultsCallback(prefix="results")
│   │   ├── cta.py            # Router: CtaCallback(prefix="cta")
│   │   └── hitl.py           # Router: HitlCallback(prefix="hitl")
│   ├── apartments.py         # Router: apartment search fast-path
│   └── query.py              # Router: catch-all text → agent
├── agent/
│   ├── bot_agent.py          # pydantic-ai Agent[BotDeps, str] factory
│   ├── deps.py               # BotDeps dataclass (typed, dishka-injected)
│   ├── tools/
│   │   ├── rag.py            # @agent.tool() — rag_search
│   │   ├── history.py        # @agent.tool() — history_search
│   │   ├── crm.py            # @agent.tool(requires_approval=True) — 8 CRM tools
│   │   ├── apartments.py     # @agent.tool() — apartment_search
│   │   └── utility.py        # mortgage_calculator, daily_summary, handoff
│   └── pipeline/
│       └── rag_core.py       # Shared 6-step: cache→retrieve→grade→rerank→rewrite→generate
├── voice/
│   ├── graph.py              # pydantic-graph Graph (11 BaseNode subclasses)
│   ├── state.py              # RAGVoiceState dataclass (typed, validated)
│   ├── nodes/
│   │   ├── transcribe.py     # TranscribeNode(BaseNode[RAGVoiceState])
│   │   ├── guard.py          # GuardNode → RespondNode | ClassifyNode
│   │   ├── classify.py       # ClassifyNode → CacheCheckNode | RespondNode
│   │   ├── cache.py          # CacheCheckNode → RespondNode | RetrieveNode
│   │   ├── retrieve.py       # RetrieveNode → GradeNode
│   │   ├── grade.py          # GradeNode → GenerateNode | RerankNode
│   │   ├── rerank.py         # RerankNode → GenerateNode
│   │   ├── rewrite.py        # RewriteNode → RetrieveNode
│   │   ├── generate.py       # GenerateNode → CacheStoreNode
│   │   ├── cache_store.py    # CacheStoreNode → RespondNode
│   │   └── respond.py        # RespondNode → End[str]
│   └── persistence.py        # RedisStatePersistence(BaseStatePersistence)
├── callbacks/
│   ├── models.py             # CallbackData factories (typed)
│   └── __init__.py
├── middlewares/
│   ├── throttling.py         # As-is (community pattern)
│   └── i18n.py               # ONLY locale detection + translator injection
├── keyboards/                # As-is
├── dialogs/                  # As-is (aiogram-dialog)
├── services/                 # As-is (generate_response.py, qdrant, bge_m3_client, etc.)
├── integrations/             # As-is (cache.py, embeddings.py, prompt_manager.py)
└── handlers/
    ├── phone_collector.py    # As-is (FSM router)
    └── handoff.py            # As-is (callback router)
```

---

## Design by Component

### 1. dishka DI Container

**APP scope** (singleton, lifecycle = bot lifetime):

```python
class AppProvider(Provider):
    scope = Scope.APP

    @provide
    async def qdrant(self, config: BotConfig) -> AsyncIterator[QdrantService]:
        svc = QdrantService(url=config.qdrant_url)
        yield svc
        await svc.close()

    @provide
    async def cache(self, config: BotConfig) -> CacheLayerManager:
        cache = CacheLayerManager(redis_url=config.redis_url, bge_m3_url=config.bge_m3_url)
        await cache.initialize()
        return cache

    @provide
    def embeddings(self, config: BotConfig) -> BGEM3HybridEmbeddings:
        return BGEM3HybridEmbeddings(base_url=config.bge_m3_url)

    @provide
    def bot_agent(self, config: BotConfig) -> Agent[BotDeps, str]:
        return create_bot_agent(config)
    # + reranker, llm, langfuse, etc.
```

**REQUEST scope** (per-update, lifecycle = single Telegram update):

```python
class RequestProvider(Provider):
    scope = Scope.REQUEST

    @provide
    async def user_service(self, pg_pool: asyncpg.Pool, event: TelegramObject) -> UserService:
        user_id = event.from_user.id if event.from_user else 0
        return UserService(pg_pool, user_id)

    @provide
    async def kommo_client(self, config: BotConfig) -> KommoClient | None:
        if not config.kommo_enabled:
            return None
        return KommoClient(config.kommo_subdomain, ...)

    @provide
    def i18n(self, middleware_data: AiogramMiddlewareData) -> TranslatorRunner:
        return middleware_data.get("i18n")
```

**Setup:**

```python
# factory.py
from dishka import make_async_container
from dishka.integrations.aiogram import setup_dishka, AiogramProvider

async def create_bot(config: BotConfig) -> tuple[Bot, Dispatcher]:
    bot = Bot(token=config.telegram_token)
    dp = Dispatcher()

    container = make_async_container(
        AppProvider(), RequestProvider(), AiogramProvider(),
        context={BotConfig: config},
    )
    setup_dishka(container=container, router=dp, auto_inject=True)
    dp.shutdown.register(container.close)

    # Include routers
    dp.include_routers(
        commands_router, voice_router, menu_router,
        feedback_router, services_router, favorites_router,
        results_router, cta_router, hitl_router,
        apartments_router, query_router,
        phone_router, handoff_router,
    )
    return bot, dp
```

---

### 2. aiogram Routers (PropertyBot decomposition)

**Принцип:** каждый Router = один домен, свои фильтры, свой middleware (опционально).

**Пример — commands router:**

```python
# routers/commands.py
from dishka.integrations.aiogram import FromDishka

router = Router(name="commands")

@router.message(Command("start"))
async def cmd_start(
    message: Message,
    user_service: FromDishka[UserService],
    i18n: FromDishka[TranslatorRunner],
) -> None:
    await user_service.ensure_exists(message.from_user)
    await message.answer(i18n.get("welcome"), reply_markup=build_client_keyboard(i18n))
```

**Пример — favorites callback router:**

```python
# routers/callbacks/favorites.py
from aiogram.filters.callback_data import CallbackData

class FavoriteCallback(CallbackData, prefix="fav"):
    action: str  # "add", "remove", "viewing", "viewing_all"
    item_id: str = ""

router = Router(name="favorites")

@router.callback_query(FavoriteCallback.filter(F.action == "add"))
async def add_favorite(
    callback: CallbackQuery,
    callback_data: FavoriteCallback,
    favorites_service: FromDishka[FavoritesService],
) -> None:
    await favorites_service.add(callback.from_user.id, callback_data.item_id)
    await callback.answer("Добавлено в закладки")

@router.callback_query(FavoriteCallback.filter(F.action == "remove"))
async def remove_favorite(...):
    ...
```

---

### 3. pydantic-ai Agent (замена LangChain)

```python
# agent/bot_agent.py
from pydantic_ai import Agent

@dataclass
class BotDeps:
    telegram_user_id: int
    session_id: str
    language: str
    cache: CacheLayerManager
    embeddings: BGEM3HybridEmbeddings
    qdrant: QdrantService
    reranker: Any | None
    kommo_client: KommoClient | None
    apartments_service: ApartmentsService | None

bot_agent = Agent(
    model="litellm:gpt-oss-120b",  # через LiteLLM
    deps_type=BotDeps,
    output_type=str,
    system_prompt=get_system_prompt,  # Langfuse Prompt Manager
)

# Tools — type-safe, no RunnableConfig boilerplate
@bot_agent.tool()
async def rag_search(ctx: RunContext[BotDeps], query: str) -> str:
    """Search knowledge base for relevant information."""
    result = await rag_pipeline(
        query=query,
        cache=ctx.deps.cache,
        embeddings=ctx.deps.embeddings,
        qdrant=ctx.deps.qdrant,
        reranker=ctx.deps.reranker,
    )
    return format_context(result)

# CRM tools — HITL via Deferred Tools
@bot_agent.tool(requires_approval=True)
async def crm_create_lead(ctx: RunContext[BotDeps], name: str, phone: str) -> str:
    """Create new lead in CRM. Requires manager confirmation."""
    lead = await ctx.deps.kommo_client.create_lead(name=name, phone=phone)
    return f"Lead #{lead.id} created"
```

**Invocation в router:**

```python
# routers/query.py
@router.message(StateFilter(None), F.text)
async def handle_query(
    message: Message,
    agent: FromDishka[Agent[BotDeps, str]],
    deps: FromDishka[BotDeps],
) -> None:
    result = await agent.run(message.text, deps=deps)

    if isinstance(result.output, DeferredToolRequests):
        # HITL: отправить inline keyboard для подтверждения CRM-операции
        await send_hitl_confirmation(message, result)
        return

    await message.answer(result.output)
```

---

### 4. pydantic-graph Voice Pipeline (замена LangGraph)

```python
# voice/state.py
@dataclass
class RAGVoiceState:
    user_id: int
    session_id: str
    query: str = ""
    input_type: str = "voice"
    voice_audio: bytes = b""
    voice_duration_s: float = 0.0
    stt_text: str = ""
    query_type: str = ""
    documents: list[Document] = field(default_factory=list)
    response: str = ""
    grade_confidence: float = 0.0
    cache_hit: bool = False
    max_rewrite_attempts: int = 1
    rewrite_count: int = 0

# voice/nodes/guard.py
@dataclass
class GuardNode(BaseNode[RAGVoiceState]):
    """Check for prompt injection."""
    async def run(self, ctx: GraphRunContext[RAGVoiceState]) -> ClassifyNode | RespondNode:
        if is_injection(ctx.state.stt_text):
            ctx.state.response = "Не могу обработать этот запрос."
            return RespondNode()
        ctx.state.query = ctx.state.stt_text
        return ClassifyNode()

# voice/nodes/grade.py
@dataclass
class GradeNode(BaseNode[RAGVoiceState]):
    """Grade retrieved documents by RRF confidence."""
    async def run(self, ctx: GraphRunContext[RAGVoiceState]) -> GenerateNode | RerankNode | RewriteNode:
        if ctx.state.grade_confidence >= 0.018:
            return GenerateNode()
        if ctx.state.rewrite_count < ctx.state.max_rewrite_attempts:
            ctx.state.rewrite_count += 1
            return RewriteNode()
        return RerankNode()

# voice/graph.py
from pydantic_graph import Graph

voice_graph = Graph(
    nodes=[
        TranscribeNode, GuardNode, ClassifyNode,
        CacheCheckNode, RetrieveNode, GradeNode,
        RerankNode, RewriteNode, GenerateNode,
        CacheStoreNode, RespondNode,
    ]
)

# voice/persistence.py
class RedisStatePersistence(BaseStatePersistence[RAGVoiceState]):
    """Redis-backed state persistence for voice pipeline."""
    def __init__(self, redis: Redis, ttl: int = 7 * 24 * 3600):
        self.redis = redis
        self.ttl = ttl

    async def save(self, state: RAGVoiceState, snapshot: GraphSnapshot) -> None:
        key = f"voice:state:{state.user_id}"
        await self.redis.set(key, snapshot.model_dump_json(), ex=self.ttl)

    async def load(self, user_id: int) -> GraphSnapshot | None:
        key = f"voice:state:{user_id}"
        data = await self.redis.get(key)
        return GraphSnapshot.model_validate_json(data) if data else None
```

**Invocation:**

```python
# routers/voice.py
@router.message(F.voice)
async def handle_voice(
    message: Message,
    voice_graph: FromDishka[Graph],
    cache: FromDishka[CacheLayerManager],
    embeddings: FromDishka[BGEM3HybridEmbeddings],
) -> None:
    file = await message.bot.get_file(message.voice.file_id)
    voice_bytes = await message.bot.download_file(file.file_path)

    state = RAGVoiceState(
        user_id=message.from_user.id,
        session_id=f"voice:{message.chat.id}",
        voice_audio=voice_bytes,
        voice_duration_s=message.voice.duration,
    )

    result = await voice_graph.run(TranscribeNode(), state=state)
    if result:
        await message.answer(result)
```

---

### 5. CallbackData Factories (замена f-string parsing)

```python
# callbacks/models.py
from aiogram.filters.callback_data import CallbackData

class FeedbackCallback(CallbackData, prefix="fb"):
    action: str      # "like" | "dislike"
    trace_id: str

class ServiceCallback(CallbackData, prefix="svc"):
    action: str      # "passive_income" | "online_deals" | "back" | "menu"

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
    request_id: str

class ClearCacheCallback(CallbackData, prefix="cc"):
    tier: str        # "all" | "semantic" | "embeddings" | "search"
```

---

### 6. I18nMiddleware — только i18n

```python
# middlewares/i18n.py (после рефакторинга)
class I18nMiddleware(BaseMiddleware):
    """ONLY locale detection + translator injection. NO service locator."""

    def __init__(self, hub: TranslatorHub):
        self.hub = hub

    async def __call__(self, handler, event, data):
        user = data.get("event_from_user")
        locale = await self._detect_locale(user)
        data["i18n"] = self.hub.get_translator_by_locale(locale)
        data["locale"] = locale
        return await handler(event, data)
```

Все сервисы (kommo_client, user_service, pg_pool, bot_config, apartments_service, favorites_service) → dishka providers, NOT middleware injection.

---

### 7. Error Handling → dp.errors

```python
# factory.py
from aiogram.filters import ExceptionTypeFilter

@dp.errors(ExceptionTypeFilter(Exception))
async def global_error_handler(error_event: ErrorEvent) -> bool:
    logger.exception("Unhandled error", exc_info=error_event.exception)
    # Send user-friendly message
    update = error_event.update
    if update.message:
        await update.message.answer("Произошла ошибка. Попробуйте позже.")
    elif update.callback_query:
        await update.callback_query.answer("Ошибка", show_alert=True)
    return True  # Error handled
```

Покрывает ВСЕ event types (Message, CallbackQuery, InlineQuery), не только Message как сейчас.

---

## What Stays As-Is

| Component | Reason |
|-----------|--------|
| `CacheLayerManager` (730 LOC) | Уже RedisVL SemanticCache внутри. 6 tiers, RedisVL покрывает только 2 |
| `BGEM3Client` (403 LOC) | HTTP-клиент к микросервису. fastembed не поддерживает BGE-M3 (issues #348, #511 open) |
| `QdrantService` (1186 LOC) | Nested prefetch, ColBERT MaxSim, RRF — langchain-qdrant не поддерживает |
| `KommoClient` (287 LOC) | Нет Python SDK для Kommo CRM |
| `ApartmentFilterExtractor` | Zero-LLM regex NLU, domain-specific |
| `ResponseStyleDetector` | Zero-latency style scoring |
| `QueryPreprocessor` | Transliteration, dynamic RRF weights |
| `generate_response.py` (770 LOC) | 87% — Telegram streaming/formatting, NOT agent framework |
| Regex classifier/guard | <1ms latency — SDK adds overhead without benefit |
| aiogram-dialog dialogs | Already SDK, working correctly |
| Throttling middleware | Community pattern, works correctly |
| Docker infrastructure | Production-grade (profiles, digest pinning, security) |
| Phone collector FSM | Already aiogram Router |
| Handoff handler | Already aiogram Router |

---

## Dependency Changes

### Remove

```toml
# pyproject.toml — удалить
"langchain-core>=0.3",
"langchain-openai>=0.3",
"langgraph>=0.2",
"langgraph-checkpoint>=2.0",
```

### Add

```toml
# pyproject.toml — добавить
"dishka>=1.8.0",
"pydantic-ai>=0.1.0",  # includes pydantic-graph
```

### Keep

```toml
"aiogram>=3.25.0",
"aiogram-dialog>=2.4.0",
"litellm>=1.50",
"redisvl>=0.4",
"qdrant-client>=1.12",
"langfuse>=3.14",
```

---

## Risk Assessment

| Risk | Impact | Mitigation |
|------|--------|------------|
| pydantic-ai breaking changes (pre-1.0) | High | Pin exact version, vendor-lock tests |
| Deferred Tools HITL gaps | Medium | Write HITL integration test before migration |
| Redis checkpointer for pydantic-graph | Medium | Implement RedisStatePersistence (~50 LOC) early |
| Langfuse observability gaps | Medium | Write @observe wrapper before migrating tools |
| Regression in voice pipeline | High | Golden-set voice tests, A/B comparison |
| 3400 LOC PropertyBot decomposition | High | Extract routers one-by-one, test each |
| Missing LangGraph features (parallel) | Low | Pipeline is linear, no fan-out needed |

---

## Success Criteria

1. `make check` passes (ruff + mypy)
2. `make test-unit` passes (all existing + new tests)
3. Zero LangChain/LangGraph imports in codebase
4. PropertyBot class deleted, replaced by Router modules
5. All 9 callback prefixes use CallbackData factories
6. I18nMiddleware has zero service dependencies (only i18n)
7. dishka container manages all service lifecycle
8. pydantic-ai agent handles text queries with HITL for CRM writes
9. pydantic-graph voice pipeline produces identical results to LangGraph (golden-set)
10. Langfuse traces show equivalent observability coverage

---

## Estimated Effort

| Phase | Scope | Effort |
|-------|-------|--------|
| 1. dishka DI + I18n cleanup | Providers, container, middleware strip | 2 days |
| 2. Router decomposition | 6 routers from PropertyBot | 3 days |
| 3. CallbackData factories | 7 files, 9 prefixes | 1 day |
| 4. pydantic-ai agent | Agent + 13 tools + HITL + Langfuse wrapper | 3 days |
| 5. DRY rag_core.py | Shared pipeline functions | 1 day |
| 6. pydantic-graph voice | 11 nodes + RedisStatePersistence + tests | 3 days |
| 7. dp.errors + cleanup | Error handler, remove LangChain deps | 1 day |
| 8. Integration testing | Golden-set, regression, E2E smoke | 2 days |
| **Total** | | **~16 days** |

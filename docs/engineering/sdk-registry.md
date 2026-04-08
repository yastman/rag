---
paths: "telegram_bot/**,src/**,mini_app/**,pyproject.toml"
---

# SDK Registry — rag-fresh

> Реестр SDK- и framework-решений проекта для scoped product code.
> Читай этот файл вместе с `AGENTS.md` и ближайшим `AGENTS.override.md` перед написанием кода.
> SDK-first: если задача покрывается готовым SDK или нативной возможностью фреймворка — используй её.
>
> **Обновление:** при добавлении/удалении зависимости — обнови этот файл.
> Формат расширяемый: добавляй новые секции по шаблону внизу.
>
> **Роль в Codex CLI:** это обычный repo document, на который ссылается `AGENTS.md`.
> Это не special path и не отдельный механизм discovery.
>
> **Границы:** этот реестр обязателен для путей из `paths:` выше. Для `scripts/`, `tests/`,
> CI/ops и одноразовых локальных утилит используй его как сильную подсказку, но проверяй
> фактический код и текущий workflow отдельно.

## aiogram (core)
- **triggers:** bot, handler, router, middleware, filter, dispatcher, FSM, message, callback, command
- **context7_id:** /aiogram/aiogram
- **как_у_нас:**
  - `telegram_bot/bot.py` — PropertyBot, Dispatcher, handler registration order
  - `telegram_bot/handlers/` — Router модули (phone_collector.py)
  - `telegram_bot/middlewares/` — BaseMiddleware subclasses (i18n, throttling, error)
- **паттерны:**
  - Handler ordering: menu buttons (F.text.in_) → FSM handlers → catch-all (StateFilter(None))
  - Middleware: `dp.message.outer_middleware(middleware)` + `dp.callback_query.outer_middleware(middleware)`
  - Filters: `F.data.startswith("svc:")`, `F.text`, `Command("start")`, `StateFilter(None)`
- **gotchas:**
  - НЕ писать кастомный message routing — использовать aiogram Router + F filters
  - FSMContext только для простых flow (phone collection). Сложные → aiogram-dialog

## aiogram-dialog
- **triggers:** меню, кнопки, диалог, window, widget, keyboard, навигация, select, multiselect, states, SG
- **context7_id:** /aiogram/aiogram-dialog
- **как_у_нас:**
  - `telegram_bot/dialogs/` — все диалоги (funnel, client_menu, viewing, settings, CRM, ...)
  - `telegram_bot/dialogs/states.py` — все StatesGroup (25 классов)
  - `telegram_bot/bot.py:_setup_dialogs()` — регистрация через dp.include_router()
- **паттерны:**
  - Window: Format() + Column(Select/Button/Start) + Back/Cancel + getter= + state=
  - Dialog: wraps N Windows, root menus с launch_mode=LaunchMode.ROOT
  - StartMode.RESET_STACK + ShowMode.DELETE_AND_SEND при старте из handler'ов
  - Select: item_id_getter=operator.itemgetter(1), items="key_from_getter"
  - SwitchTo для навигации внутри диалога, Start для дочерних диалогов
  - MessageInput для free-text/voice: content_types=[ContentType.TEXT]
- **gotchas:**
  - НЕ писать кастомные FSM/state machines — всё через aiogram-dialog StatesGroup + Window
  - НЕ писать кастомные InlineKeyboard для навигации — использовать Select/Button/SwitchTo
  - States определяются ТОЛЬКО в states.py (централизованно)
  - setup_dialogs(dp) вызывается ПОСЛЕДНИМ после всех include_router

## langgraph
- **triggers:** graph, pipeline, node, edge, state, checkpoint, memory, agent, tool, RAG pipeline, voice
- **context7_id:** /langchain-ai/langgraph
- **как_у_нас:**
  - `telegram_bot/graph/graph.py` — voice RAG pipeline (11 nodes, StateGraph)
  - `telegram_bot/graph/state.py` — RAGState (TypedDict, ~50 fields)
  - `telegram_bot/graph/context.py` — GraphContext (TypedDict, DI container)
  - `telegram_bot/graph/nodes/` — retrieve, rerank, cache, guard, classify, rewrite
  - `telegram_bot/agents/history_graph/graph.py` — history search sub-graph (5 nodes)
  - `telegram_bot/agents/hitl.py` — interrupt() для HITL
  - `telegram_bot/integrations/memory.py` — AsyncRedisSaver / MemorySaver
- **паттерны:**
  - State = TypedDict (не Pydantic). Reducer: `Annotated[list, add_messages]`
  - DI через context_schema=GraphContext + Runtime[GraphContext] в нодах
  - Альтернативный DI: functools.partial (history sub-graph)
  - Conditional edges: route functions возвращают имя следующего node
  - Checkpointing: AsyncRedisSaver (prod) / MemorySaver (dev)
  - HITL: interrupt() в CRM tools → Command(resume=) в handler
- **gotchas:**
  - Text RAG path НЕ использует LangGraph — plain async functions в pipelines/client.py
  - НЕ использовать Pydantic для state — только TypedDict
  - compile() без checkpointer = без summarize node
  - recursion_limit=15 при compile().with_config()

## qdrant-client
- **triggers:** vector, search, qdrant, collection, embedding, hybrid, RRF, ColBERT, prefetch, filter, points
- **context7_id:** /qdrant/qdrant-client
- **как_у_нас:**
  - `telegram_bot/services/qdrant.py` — AsyncQdrantClient (production, prefer_grpc=True)
  - `src/retrieval/search_engines.py` — QdrantClient (sync, evaluation)
  - `telegram_bot/services/apartments_service.py` — direct client access
- **паттерны:**
  - ВСЕГДА query_points() (НИКОГДА .search() — deprecated в v1.17)
  - Dense-only: query_points(query=vector, using="dense")
  - 2-stage RRF: Prefetch[dense, sparse] → RrfQuery(k=rrf_k)
  - 3-stage ColBERT: Prefetch[Prefetch[dense, sparse] → RRF] → query colbert vectors
  - Named vectors: "dense" (BGE-M3), "bm42"/"sparse" (lexical), "colbert" (multivec)
  - Batch: query_batch_points() с list[QueryRequest]
  - Group-by: query_points_groups(group_by="doc_id")
- **gotchas:**
  - НИКОГДА .search() — только .query_points()
  - Apartments: payload filters без metadata. prefix
  - prefer_grpc=True для async клиента
  - QDRANT_TIMEOUT=30 для тяжёлых запросов

## instructor
- **triggers:** structured extraction, LLM parsing, response_model, Pydantic extraction, фильтры квартир
- **context7_id:** /instructor-ai/instructor
- **как_у_нас:**
  - `telegram_bot/services/apartment_llm_extractor.py` — единственное использование
- **паттерны:**
  - `ApartmentLlmExtractor(llm=...)` → `instructor.from_openai(llm)` → `chat.completions.create(response_model=PydanticModel)`
  - max_retries=2 для автоматического retry при validation error
  - Результат merge с regex extraction (regex wins на числовых полях)
- **gotchas:**
  - НЕ писать кастомный JSON parsing из LLM — использовать instructor + Pydantic model
  - Для Instructor-совместимого extraction path допустим native OpenAI client, если это текущий совместимый runtime contract
  - response_model = Pydantic v2 модель с Field(description=) для каждого поля

## redisvl
- **triggers:** cache, semantic cache, embedding cache, кеш, кэш, redis vector, similarity
- **context7_id:** /redis/redis-vl-python
- **как_у_нас:**
  - `telegram_bot/integrations/cache.py` — SemanticCache + EmbeddingsCache
  - `telegram_bot/services/vectorizers.py` — BgeM3CacheVectorizer (custom)
- **паттерны:**
  - SemanticCache: name="sem:v5:bge1024", distance_threshold по query_type (FAQ=0.12, GENERAL=0.08)
  - EmbeddingsCache: name="embeddings:v5", ttl=7 days
  - Lazy import внутри initialize() (избежать 7.5s startup penalty)
  - filterable_fields: query_type, language, user_id, cache_scope, agent_role (tag)
- **gotchas:**
  - ВСЕГДА lazy import redisvl (не на уровне модуля)
  - distance_threshold на RRF scale (~0.005–0.12), НЕ cosine [0-1]
  - BgeM3CacheVectorizer — кастомный, чтобы использовать тот же BGE-M3 что в pipeline

## redis-py (asyncio)
- **triggers:** redis, redis.asyncio, pubsub, TTL, event stream, handoff state, deep-link state
- **context7_id:** /redis/redis-py
- **как_у_нас:**
  - `mini_app/api.py` — lazy `aioredis.from_url()` для deep-link payload и pub/sub
  - `telegram_bot/integrations/cache.py` — async Redis path в cache layer
  - `telegram_bot/integrations/event_stream.py` — event stream publishing
  - `telegram_bot/services/handoff_state.py` — typed `Redis` dependency
  - `telegram_bot/preflight.py` — runtime preflight checks
- **паттерны:**
  - Async path = `import redis.asyncio as redis|aioredis`
  - Long-lived client через `from_url(..., decode_responses=True)` и reuse, не client-per-call
  - Ephemeral state хранить с явным TTL: `set(key, payload, ex=seconds)`
  - Pub/sub и coordination paths держать bounded и keyed по явным channel/key naming rules
- **gotchas:**
  - НЕ тащить sync Redis client в async runtime path
  - НЕ терять `ex=`/TTL на ephemeral state вроде mini app deep links
  - Reuse or close long-lived clients явно; не плодить новые соединения без причины

## langfuse
- **triggers:** observability, tracing, trace, span, score, metrics, monitoring, langfuse, observe
- **context7_id:** /langfuse/langfuse-python
- **как_у_нас:**
  - `telegram_bot/observability.py` — центральный модуль (init, observe, callback handler)
  - `telegram_bot/integrations/prompt_manager.py` — prompt management
  - `telegram_bot/scoring.py` — 14 RAG scores
  - `src/ingestion/unified/observability.py` — ingestion-side @observe
- **паттерны:**
  - @observe(name="node-X", capture_input=False, capture_output=False) на каждый node/step
  - propagate_attributes() — обязательная обёртка entry-point (иначе orphan traces)
  - langfuse.openai.AsyncOpenAI как drop-in замена openai.AsyncOpenAI (auto-tracing)
  - Prompt management: `telegram_bot.integrations.prompt_manager.get_prompt()` / `get_prompt_with_config()` → `client.get_prompt(...)`
  - CallbackHandler для LangChain/agent calls
  - PII masking через mask= параметр при Langfuse()
- **gotchas:**
  - Для основного bot/query/runtime path использовать `langfuse.openai.AsyncOpenAI`
  - НЕ возвращаться к manual `client.api.prompts.get(...)` probing, пока `client.get_prompt(...)` покрывает нужный path
  - propagate_attributes() ПЕРЕД любым @observe кодом
  - capture_input/output=False на тяжёлых нодах (payload bloat prevention)

## langmem
- **triggers:** summarization, conversation memory, сжатие, summary, compress messages
- **context7_id:** /langchain-ai/langmem
- **как_у_нас:**
  - `telegram_bot/graph/graph.py:136-171` — SummarizationNode (lazy import)
- **паттерны:**
  - SummarizationNode(max_tokens=512, max_tokens_before_summary=1024, max_summary_tokens=256)
  - input_messages_key="messages", output_messages_key="messages" (in-place)
  - Обёрнут в async wrapper с @observe + exception fallback
- **gotchas:**
  - Только с checkpointer (без checkpointer — node не добавляется в граф)
  - Lazy import внутри build_graph()

## apscheduler
- **triggers:** scheduler, cron, interval, job, periodic, nurturing, расписание
- **context7_id:** /agronholm/apscheduler
- **как_у_нас:**
  - `telegram_bot/services/nurturing_scheduler.py` — AsyncIOScheduler
- **паттерны:**
  - AsyncIOScheduler(job_defaults={"coalesce": True, "max_instances": 1, "misfire_grace_time": 300})
  - interval trigger для batch jobs, CronTrigger для daily/cron jobs
- **gotchas:**
  - v3 API (НЕ v4) — AsyncIOScheduler, не AsyncScheduler
  - shutdown(wait=False) при остановке

## fluentogram
- **triggers:** i18n, locale, translation, перевод, .ftl, fluent, язык, language
- **context7_id:** /Arustinal/fluentogram
- **как_у_нас:**
  - `telegram_bot/middlewares/i18n.py` — TranslatorHub, I18nMiddleware
  - `telegram_bot/locales/{ru,uk,en}/` — .ftl файлы
  - `telegram_bot/keyboards/` — i18n в keyboard builders
- **паттерны:**
  - TranslatorHub с fallback chain: uk→(uk,ru,en), ru→(ru,en), en→(en)
  - I18nMiddleware инжектит i18n: FluentTranslator в handler data
  - i18n.get("key-name") или i18n.get("key", var=value)
- **gotchas:**
  - НЕ хардкодить текст — всё через .ftl ключи
  - Locale resolving: DB → detect_locale(language_code) → "ru" (default)

## docling
- **triggers:** docling, document converter, parsing, chunking, docx, xlsx, csv, docling_native, docling_http
- **context7_id:** /docling-project/docling
- **как_у_нас:**
  - `src/ingestion/document_parser.py` — direct `DocumentConverter()` for universal parser path
  - `src/ingestion/docling_client.py` — `docling-serve` HTTP client
  - `src/ingestion/docling_native.py` — feature-flagged native adapter with the same chunk contract
  - `src/ingestion/unified/targets/qdrant_hybrid_target.py` — runtime backend selection
- **паттерны:**
  - Native path: direct `DocumentConverter()` only where local/runtime packaging allows it
  - HTTP path: `DoclingClient` / `DoclingConfig` for `docling-serve`
  - Preserve backend split: `docling_http` and `docling_native` are intentionally different operational modes
- **gotchas:**
  - НЕ схлопывать native и HTTP path без проверки runtime/deploy constraints
  - `docling` — optional ingest extra, не предполагать его наличие в base runtime
  - Preserve chunk contract between `DoclingClient` and `NativeDoclingAdapter`

## cocoindex
- **triggers:** cocoindex, ingestion flow, indexing pipeline, flow builder, target connector, embedding pipeline
- **context7_id:** /cocoindex-io/cocoindex
- **как_у_нас:**
  - `src/ingestion/unified/flow.py` — main flow definition
  - `src/ingestion/unified/targets/qdrant_hybrid_target.py` — custom target connector
- **паттерны:**
  - cocoindex.init(Settings(database=..., app_namespace="unified"))
  - @cocoindex_function() для pure Python operators
  - flow_builder.add_source(LocalFile(...)) → .transform() → collector.export()
- **gotchas:**
  - НЕ использовать env vars для init — explicit Settings()
  - Custom target: @target_connector, sync mutate() (без asyncio.run)

## livekit-agents
- **triggers:** voice, call, SIP, LiveKit, agent, TTS, STT, ElevenLabs
- **context7_id:** /livekit/agents
- **как_у_нас:**
  - `src/voice/agent.py` — LiveKit voice agent
  - `src/voice/sip_setup.py` — SIP trunk configuration
- **паттерны:**
  - livekit-agents + livekit-plugins-elevenlabs (TTS) + livekit-plugins-openai (STT)
- **gotchas:**
  - voice — optional extra (uv sync --extra voice)

## asyncpg
- **triggers:** postgres, database, SQL, lead scoring, DB, таблица, миграция
- **context7_id:** /MagicStack/asyncpg
- **как_у_нас:**
  - `telegram_bot/services/lead_scoring.py` — connection pool
  - `telegram_bot/integrations/postgres.py` — pool management
- **паттерны:**
  - asyncpg.create_pool() с min_size/max_size
  - pool.fetch/fetchrow/execute для queries
- **gotchas:**
  - НЕ писать raw SQL где можно — но ORM не используем, asyncpg напрямую

## fastapi
- **triggers:** fastapi, endpoint, route, lifespan, middleware, healthcheck, uvicorn, response_model, API
- **context7_id:** /fastapi/fastapi
- **как_у_нас:**
  - `src/api/main.py` — RAG API c `lifespan`, `app.state`, `/query`, `/health`
  - `mini_app/api.py` — Mini App backend + `CORSMiddleware`
  - `services/bge-m3-api/app.py` — embeddings/rerank service
  - `services/user-base/main.py` — dense embedding service
- **паттерны:**
  - Heavy startup/teardown через `lifespan`, не через module import side effects
  - Long-lived deps складывать в `app.state`
  - Request/response contracts через Pydantic models и `response_model=`
  - `/health` держать cheap и отделенным от тяжелых runtime endpoints
- **gotchas:**
  - НЕ переносить тяжелую инициализацию графа/моделей в import-time
  - Middleware/CORS добавлять только там, где это часть surface contract, не копировать без причины
  - Preserve structured error/health responses; не заменять их ad-hoc debug поведением

## httpx
- **triggers:** httpx, http client, external api, retry, timeout, transport, kommo, docling-serve, vectorizer service
- **context7_id:** /encode/httpx
- **как_у_нас:**
  - `telegram_bot/services/kommo_client.py` — first-party Kommo adapter on `httpx.AsyncClient`
  - `src/ingestion/docling_client.py` — `docling-serve` client
  - `telegram_bot/services/vectorizers.py` — sync/async clients for embedding service
- **паттерны:**
  - `httpx.AsyncClient` / `httpx.Client` with explicit timeout and bounded limits
  - Wrap raw HTTP in typed service/adapter boundaries instead of scattering calls through handlers
  - Retry only bounded transport / 429 / 5xx classes, not blanket retries on everything
- **gotchas:**
  - НЕ писать ad-hoc raw HTTP из transport-layer Telegram code
  - Для Kommo canonical path = current first-party `KommoClient`, не сторонний SDK
  - Reuse or close long-lived clients explicitly; не плодить client-per-request без причины

## tma.js
- **triggers:** telegram mini app, tma, webapp, initData, themeParams, viewport, swipe behavior
- **context7_id:** /telegram-mini-apps/tma.js
- **как_у_нас:**
  - `mini_app/frontend/src/bootstrap.ts` — `init()`, `initData.restore()`, `themeParams`, `viewport`, `swipeBehavior`
  - `mini_app/frontend/src/pages/QuestionSheet.tsx` — `miniApp`, `sendData`
  - `mini_app/frontend/src/pages/ExpertSheet.tsx` — `initData.user()`, query bootstrap
  - `mini_app/frontend/src/test-setup.ts` — package mocking for tests
- **паттерны:**
  - SDK init централизован в `bootstrap.ts`, не размазан по страницам
  - Runtime detection через `isTMA("complete")`; в dev path допустим mock env
  - Theme/viewport CSS vars и swipe behavior монтируются через SDK primitives
  - Telegram-specific data брать через `initData`, не через ручной `window.Telegram` parsing
- **gotchas:**
  - НЕ дублировать SDK init в page components
  - Dev/browser fallback path и Telegram runtime path должны оставаться разделенными
  - Mini App routing использует `HashRouter`; не переводить на browser history без отдельного Telegram deployment решения

## openai (Python SDK)
- **triggers:** LLM, генерация, completion, chat, AsyncOpenAI, OpenAI, модель, generate, structured output
- **context7_id:** /openai/openai-python
- **как_у_нас:**
  - `telegram_bot/services/llm.py` — основной LLM-клиент через `langfuse.openai.AsyncOpenAI`
  - `telegram_bot/services/query_preprocessor.py` — query classification
  - `telegram_bot/services/query_analyzer.py` — intent analysis
  - `telegram_bot/services/apartment_llm_extractor.py` — structured extraction (OpenAI direct)
  - `src/contextualization/openai.py` — chunk contextualization
- **паттерны:**
  - Основной bot/query/runtime path: `langfuse.openai.AsyncOpenAI` + `LLM_BASE_URL` → LiteLLM proxy
  - Structured output: `response_format=` где хватает native SDK, `instructor` только для bounded extraction paths
  - Isolated contextualization / compatibility paths могут использовать native `openai.AsyncOpenAI` / `OpenAI`
- **gotchas:**
  - Для основного runtime path НЕ импортировать raw `openai.AsyncOpenAI`; использовать Langfuse wrapper
  - Direct OpenAI SDK допустим только в изолированных contextualization / eval / Instructor-compatibility paths
  - НЕ хардкодить runtime model name — брать из config/env (`LLM_MODEL`)
  - `LLM_BASE_URL` обязателен для unified routing там, где path идет через LiteLLM

## groq
- **triggers:** groq, llama3, groq api, fast contextualization, groq contextualizer
- **context7_id:** /groq/groq-python
- **как_у_нас:**
  - `src/contextualization/groq.py` — Groq-based contextualization provider
- **паттерны:**
  - `AsyncGroq()` для async, `Groq()` для sync
  - Bounded usage as contextualization provider with tenacity retry on rate-limit / API-status errors
- **gotchas:**
  - НЕ расширять Groq в основной bot/runtime LLM path без отдельного решения
  - Прямой Groq API path обходит LiteLLM/Langfuse main-runtime conventions
  - Keep model choice and retry policy local to contextualization path

## voyageai
- **triggers:** rerank, embedding, voyage, ColBERT, contextualized embedding
- **context7_id:** /voyage-ai/voyageai-python
- **как_у_нас:**
  - `telegram_bot/services/voyage.py` — reranking service
  - `src/models/contextualized_embedding.py` — contextualized late-interaction embeddings
- **паттерны:**
  - `voyageai.Client()` для sync, lazy import (тяжёлые deps: pandas, scipy)
  - Rerank: `client.rerank(query, documents, model="rerank-2")`
- **gotchas:**
  - Тяжёлый import (pandas, scipy.stats) — lazy import ОБЯЗАТЕЛЬНО
  - НЕ импортировать на top-level в модулях бота (замедляет старт)

## anthropic
- **triggers:** Claude, Anthropic, contextualization, claude judge
- **context7_id:** /anthropics/anthropic-sdk-python
- **как_у_нас:**
  - `src/contextualization/claude.py` — chunk contextualization через Claude
  - `scripts/e2e/claude_judge.py` — e2e evaluation judge
- **паттерны:**
  - `AsyncAnthropic()` для async, `Anthropic()` для sync scripts
  - Только для contextualization и eval — основной LLM через openai SDK + LiteLLM
- **gotchas:**
  - НЕ использовать для основной генерации — только через LiteLLM unified routing
  - Прямой вызов Anthropic API = обход трейсинга Langfuse

---

## Шаблон для нового SDK

```markdown
## {sdk_name}
- **triggers:** keyword1, keyword2, keyword3
- **context7_id:** /org/project
- **как_у_нас:**
  - `path/to/main/usage.py` — краткое описание
- **паттерны:**
  - Основной паттерн использования
- **gotchas:**
  - НЕ делать X — делать Y
```

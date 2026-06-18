---
paths: "telegram_bot/**,src/**,mini_app/**,pyproject.toml,Makefile,.github/workflows/**"
---

# SDK Registry — rag-fresh

> SDK and framework registry for scoped product code in this project.
> Read this file together with `AGENTS.md` and the nearest `AGENTS.override.md` before writing code.
> SDK-first: if a task is covered by an existing SDK or native framework capability, use it.
>
> **Updating:** when adding or removing a dependency, update this file.
> The format is extensible: add new sections using the template at the bottom.
>
> **Role in the repository:** this is a normal repo document referenced by `AGENTS.md`.
> It is not a special path or a separate discovery mechanism.
>
> **Scope:** this registry is mandatory for paths listed in the `paths:` frontmatter above.
> For `scripts/`, `tests/`, CI/ops, and one-off local utilities, treat it as a strong hint
> but verify actual code and current workflows separately.

## uv
- **triggers:** uv, venv, .venv, lockfile, pyproject, dependency, dependency group, make check, candidate-check, CI install, worktree
- **context7_id:** /astral-sh/uv
- **как_у_нас:**
  - `Makefile` — local install/update/check/test targets and review-safe gates.
  - `.github/workflows/ci.yml` — GitHub-hosted lockfile and lightweight CI gates.
  - `.github/workflows/trusted-heavy.yml` — self-hosted heavy test setup with `uv sync --frozen`.
  - `docs/LOCAL-DEVELOPMENT.md` — local and worktree validation guidance.
- **паттерны:**
  - Normal developer install/update commands may use `uv sync`, `uv lock`, and plain `uv run`.
  - Review/candidate gates use `uv sync --frozen --check` first, then `uv run --no-sync` through `$(UV_RUN_NO_SYNC)`.
  - `uv run --frozen` prevents lockfile updates but can still sync/mutate the project environment.
  - `uv run --no-sync` is the native uv flag for running without environment sync.
  - Use `UV_PROJECT_ENVIRONMENT=/absolute/path` only intentionally; the same absolute env reused across projects/worktrees will be overwritten by each project.
- **gotchas:**
  - НЕ заменять uv своим env manager/wrapper unless there is a documented uv gap.
  - НЕ использовать bare `uv run` in review-safe gates (`check-frozen`, `candidate-check`, bot preflight); use `$(UV_RUN_NO_SYNC)`.
  - НЕ считать `uv run --frozen` read-only for `.venv`; it freezes lockfile behavior, not environment sync.
  - Shared `.venv` across worktrees is risky. Prefer isolated worktree envs, or run review-safe gates with `UV_PROJECT_ENVIRONMENT` only when the shared env has been prechecked.
  - Contracts: `tests/contract/test_makefile_review_gate_no_autosync_contract.py`, `tests/unit/test_makefile_contract.py`.

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
  - **Документированное исключение (#1232 / #2055):** `telegram_bot/handlers/phone_collector.py` остаётся на raw aiogram Router + FSMContext. Причина: lead capture использует `KeyboardButton(request_contact=True)` через `ReplyKeyboardMarkup`, а aiogram-dialog не предоставляет эквивалентного widget'а для one-tap contact share. Принудительный переход на inline `Select`/`Button` ухудшит UX (ручной ввод вместо одного тапа) и снизит opt-in rate. CRM quick actions и demo handler мигрируют (см. #2053, #2054), phone collector остаётся exception'ом до тех пор, пока продукт не примет более слабый UX или aiogram-dialog не добавит contact-share widget.

## imperative assistant pipeline
- **triggers:** pipeline, orchestration, RAG, voice, agent, tool
- **context7_id:** none; repo-native runtime
- **как_у_нас:** `src/runtime/pipeline/assistant_pipeline.py` owns orchestration; legacy graph factories are compatibility facades only.
- **паттерны:** prefer plain async functions, typed request/result contracts, and explicit dependency injection via `CoreDependencies`.
- **gotchas:** do not add LangChain/LangGraph/LangMem back to runtime dependencies for orchestration.

## qdrant-client
- **triggers:** vector, search, qdrant, collection, embedding, hybrid, RRF, ColBERT, prefetch, filter, points
- **context7_id:** /qdrant/qdrant-client
- **как_у_нас:**
  - `telegram_bot/services/qdrant.py` — AsyncQdrantClient (production, prefer_grpc=True)
  - `src/retrieval/search_engines.py` — QdrantClient (sync, evaluation)
  - `telegram_bot/services/apartments_service.py` — direct client access
- **паттерны:**
  - ВСЕГДА query_points() (НИКОГДА .search() — deprecated в v1.17)
  - Инициализация через `AsyncQdrantClient(..., prefer_grpc=True)`
  - Dense-only: `query_points(query=vector, using="dense")`
  - 2-stage RRF: `Prefetch[dense, sparse]` → `RrfQuery(k=rrf_k)`
  - 3-stage ColBERT: `Prefetch[Prefetch[dense, sparse] → RRF]` → `query_colbert`
  - Named vectors: "dense" (BGE-M3), "bm42"/"sparse" (lexical), "colbert" (multivec)
  - Batch: query_batch_points() с list[QueryRequest]
  - Group-by: `query_points_groups(group_by="doc_id")`
- **gotchas:**
  - НИКОГДА .search() — только .query_points()
  - Qdrant остаётся поисковым бекендом — не переносить векторный поиск на RedisVL
  - Apartments: payload filters без metadata. prefix
  - QDRANT_TIMEOUT=30 для тяжёлых запросов
  - `grpcio` НЕ объявляется как прямая зависимость (#2241). `qdrant-client`
    жёстко требует `grpcio>=1.41.0`, поэтому при `prefer_grpc=True` он
    подтягивается транзитивно. Прямой pin (`grpcio>=...`) — избыточен и только
    создаёт лишнюю работу резолверу/сборке в PR-проверках. Контракт:
    `tests/contract/test_grpcio_dependency_audit_contract.py`.

## LiteLLM structured output
- **triggers:** structured extraction, LLM parsing, response_model, Pydantic extraction, фильтры квартир
- **context7_id:** /BerriAI/litellm
- **как_у_нас:**
  - `src/runtime/llm/router.py` — canonical in-process LiteLLM SDK router and OpenAI-shaped chat client.
  - `telegram_bot/services/apartment_llm_extractor.py` — apartment filter extraction (single non-streaming call).
  - `telegram_bot/services/query_analyzer.py` — query intent / language classification (single non-streaming call).
- **паттерны:**
  - REQUIRED shape: `create_litellm_chat_client(...).chat.completions.create(response_model=PydanticModel, ...)`.
  - The router converts `response_model` into OpenAI-compatible `response_format={"type": "json_schema", ...}` and parses the returned JSON into the Pydantic model.
  - Retry/fallback is owned by LiteLLM routing; wrapper-only kwargs such as `max_retries` remain compatibility shims.
  - Результат extraction merge с regex (regex wins на числовых полях).
- **gotchas:**
  - НЕ добавлять второй structured-output SDK для активных путей — используйте `src.runtime.llm`.
  - НЕ строить скрытые OpenAI clients внутри feature-кода; runtime owns provider routing.
  - response_model = Pydantic v2 модель с `Field(description=)` для каждого поля.

## redisvl
- **triggers:** cache, semantic cache, embedding cache, кеш, кэш, redis vector, similarity
- **context7_id:** /redis/redis-vl-python
- **как_у_нас:**
  - `telegram_bot/integrations/cache.py` — SemanticCache + EmbeddingsCache
  - `telegram_bot/services/vectorizers.py` — BgeM3CacheVectorizer (custom)
- **паттерны:**
  - SemanticCache: name="sem:v8:bge1024", distance_threshold по query_type (FAQ=0.12, GENERAL=0.08)
  - EmbeddingsCache: name="embeddings:v5", base TTL=7d (переиспользуется и для query-bundle кеша)
  - Lazy import внутри initialize() (избежать 7.5s startup penalty)
  - filterable_fields: query_type, language, user_id, cache_scope, agent_role (tag)
  - BGE-M3 query-bundle: `EmbeddingsCache` с `model_name="bge-m3-query-bundle"` хранит:
    - dense как `embedding`
    - sparse + colbert в `metadata`
    - key material через `version:model:max_length:normalized_query`
  - TTL для query-bundle = точный TTL tier `embeddings` (по умолчанию 7d)
- **gotchas:**
  - ВСЕГДА lazy import redisvl (не на уровне модуля)
  - distance_threshold на RRF scale (~0.005–0.12), НЕ cosine [0-1]
  - BgeM3CacheVectorizer остается кастомным намеренно: вызывает тот же local BGE-M3 pipeline API, чтобы сохранить внутренние threshold/dimensions

## redis-py (asyncio)
- **triggers:** redis, redis.asyncio, pubsub, TTL, event stream, handoff state, deep-link state
- **context7_id:** /redis/redis-py
- **как_у_нас:**
  - `mini_app/api.py` — lazy `aioredis.from_url()` для deep-link payload и pub/sub
  - `telegram_bot/integrations/cache.py` — exact-key JSON tiers: sparse/search/rerank
  - `telegram_bot/integrations/event_stream.py` — event stream publishing
  - `telegram_bot/services/handoff_state.py` — typed `Redis` dependency
  - `telegram_bot/preflight.py` — runtime preflight checks
- **паттерны:**
  - Async path = `import redis.asyncio as redis|aioredis`
  - Long-lived client через `from_url(..., decode_responses=True)` и reuse, не client-per-call
  - Exact cache tiers и runtime-state (sparse/search/rerank/state/pubsub/deep-link) с явным TTL
  - Ephemeral state хранить с явным TTL: `set(key, payload, ex=seconds)`
  - Pub/sub и coordination paths держать bounded и keyed по явным channel/key naming rules
- **gotchas:**
  - НЕ тащить sync Redis client в async runtime path
  - НЕ терять `ex=`/TTL на ephemeral state вроде mini app deep links
  - НЕ считать, что RedisVL заменяет redis-py exact-key JSON кеши
  - Reuse or close long-lived clients явно; не плодить новые соединения без причины

## langfuse
- **triggers:** observability, tracing, trace, span, score, metrics, monitoring, langfuse, observe
- **context7_id:** /langfuse/langfuse-python
- **как_у_нас:**
  - `telegram_bot/observability.py` — центральный модуль (init, observe, callback handler)
  - `telegram_bot/scoring.py` — RAG quality scores written to Langfuse per query (see [`docs/RAG_QUALITY_SCORES.md`](../RAG_QUALITY_SCORES.md) for the full enumeration; parity is enforced by `tests/contract/test_rag_quality_scores_doc_drift.py`)
  - `src/ingestion/unified/observability.py` — ingestion-side @observe
- **паттерны:**
  - @observe(name="node-X", capture_input=False, capture_output=False) на каждый node/step
  - propagate_attributes() — обязательная обёртка entry-point (иначе orphan traces)
  - langfuse.openai.AsyncOpenAI как drop-in замена openai.AsyncOpenAI (auto-tracing)
  - Trace details: `client.api.trace.get(trace_id, fields="core,io,scores,metrics")`; nested observations сначала читать через SDK-native `client.api.observations.get_many(trace_id=..., fields="core,basic", cursor=...)`, а для self-hosted OSS fallback использовать SDK `client.api.trace.get(trace_id, fields="core,io,scores,observations,metrics")`
  - CallbackHandler для LangChain/agent calls
  - PII masking через mask= параметр при Langfuse()
- **gotchas:**
  - Для основного bot/query/runtime path использовать `langfuse.openai.AsyncOpenAI`
  - НЕ писать custom HTTP-клиент для observations. Langfuse Cloud: `api.observations.get_many(...)`; self-hosted OSS v4 может отвечать, что v2 observations доступны только Cloud, тогда fallback — SDK `trace.get(..., fields="...,observations,...")`.
  - Для полной локальной диагностики в Langfuse v3 лучше `langfuse api traces get <id> --fields core,io,scores,observations,metrics --json`; `traces list` иногда хватает, а `observations list` может быть 404

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
  - `src/runtime/graph/config.py::GraphConfig.create_llm()` — canonical async LLM-client factory through the in-process LiteLLM SDK router (`src.runtime.llm.router`)
  - `telegram_bot/services/query_preprocessor.py` — query classification
  - `telegram_bot/services/query_analyzer.py` — intent analysis
  - `telegram_bot/services/apartment_llm_extractor.py` — structured extraction (OpenAI direct)
  - `src/contextualization/openai.py` — chunk contextualization
- **паттерны:**
  - Основной bot/query/runtime chat path: `GraphConfig.create_llm()` → in-process LiteLLM SDK router; no Docker proxy/base URL
  - Структурированный output: `response_format=` / Instructor-compatible контракты в основном runtime
  - OpenAI SDK-native chat kwargs остаются top-level (`reasoning_effort`); provider-specific OpenAI-compatible controls (`disable_reasoning`, `reasoning_format`) идут через `extra_body={...}`. `disable_reasoning` взаимоисключает `reasoning_effort` / `reasoning_format`.
  - Raw `openai.AsyncOpenAI` / `OpenAI` допустим только в изолированных совместимых/compatibility paths (например, instructor-экстракшн/оценка)
- **gotchas:**
  - Для основного runtime chat path НЕ импортировать raw `openai.AsyncOpenAI`; использовать `GraphConfig.create_llm()` / `src.runtime.llm.router`
  - Direct OpenAI SDK не является основным runtime path; использовать только в изолированных contextualization/eval/Instructor-compatibility paths
  - НЕ прокидывать нестандартные provider kwargs (`disable_reasoning`, `reasoning_format`) напрямую в `chat.completions.create(...)`; OpenAI SDK отвергнет их как unexpected keyword arguments.
  - НЕ отправлять `disable_reasoning` вместе с `reasoning_effort`/`reasoning_format`; LiteLLM/Cerebras отвергает такой запрос.
  - НЕ хардкодить runtime model name — брать из config/env (`LLM_MODEL`)
  - `LLM_BASE_URL` не нужен для unified chat routing; provider keys are read directly by the LiteLLM SDK router

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

## opentelemetry-instrumentation (SDK-native auto-instrumentation)
- **triggers:** otel, traceparent, baggage, w3c-tracecontext, cross-service, propagator, instrumentor, auto-instrumentation, FastAPIInstrumentor, HTTPXClientInstrumentor, OTEL_PROPAGATORS
- **context7_id:** /open-telemetry/opentelemetry-python-contrib
- **как_у_нас:**
  - `src/observability_otel.py` — idempotent `activate_otel_instrumentations()` + `instrument_fastapi_app(app)` (#2225)
  - `src/observability.py` — calls `activate_otel_instrumentations()` after Langfuse init
  - `services/bge-m3-api/app.py` — calls `FastAPIInstrumentor.instrument_app(app)` + `LoggingInstrumentor`
  - `src/api/main.py` — calls `instrument_fastapi_app(app)` via the shared helper
  - `compose.yml` — `OTEL_PROPAGATORS=tracecontext,baggage` on every OTEL-instrumented service (#2246 F3)
  - `pyproject.toml` — `opentelemetry-instrumentation-{httpx,asyncpg,redis,grpc,aiohttp-client,requests,logging,fastapi}>=0.58b0`
- **паттерны:**
  - **Inbound FastAPI:** use `FastAPIInstrumentor.instrument_app(app)` or the shared `instrument_fastapi_app(app)` helper to extract W3C TraceContext + Baggage on every request.
  - **Outbound HTTP:** ride on `httpx` (sync `Client` or async `AsyncClient`) so the process-wide `HTTPXClientInstrumentor` injects `traceparent`/`baggage` automatically.
  - **Activation:** call `activate_otel_instrumentations()` once at startup (idempotent; per-instrumentor try/except).
  - **Propagators:** declare `OTEL_PROPAGATORS=tracecontext,baggage` explicitly in compose (defense-in-depth).
  - **Log-to-trace correlation:** `LoggingInstrumentor` injects `otelTraceID`/`otelSpanID` into every `LogRecord`.
  - **Test coverage:** `tests/contract/test_cross_service_trace_instrumentation_contract.py` (inbound FastAPI + outbound HTTPX + activation), `the removed OTel propagators contract` (compose OTEL_PROPAGATORS + .env.example doc).
- **gotchas:**
  - НЕ добавлять OTLP gRPC exporter — Langfuse v4 SDK handles OTLP export internally.
  - НЕ писать ручной propagation (`inject()`/`extract()`/`attach()`/`detach()`) поверх SDK-native FastAPIInstrumentor + HTTPXClientInstrumentor. Ручной propagation (#2229) удаляется в #2253/#2266 после runtime-доказательства cross-service continuity.
  - НЕ использовать raw-thread hops (`threading.Thread`, `ThreadPoolExecutor.submit`) рядом с `@observe` без `contextvars.copy_context()` — raw threads теряют OTEL parent context (#2246 F1).
  - `OTEL_PROPAGATORS` должен включать и `tracecontext`, и `baggage` — потеря baggage ломает Langfuse user/session/tags propagation через сервисные границы (#2226).
  - Double-instrumentation guard: `FastAPIInstrumentor.instrument_app` сам ставит флаг `_is_instrumented_by_opentelemetry`; в shared helper читаем его до вызова.
  - Отсутствующие `opentelemetry-instrumentation-*` пакеты пропускаются silently — это не ошибка, а graceful degradation.
  - Contracts: `tests/contract/test_cross_service_trace_instrumentation_contract.py`, `the removed OTel propagators contract`, `the removed end-to-end trace flow contract`.

## prometheus_client
- **triggers:** prometheus, metrics, histogram, counter, /metrics, make_asgi_app, REGISTRY, scrape
- **context7_id:** /prometheus/client_python
- **как_у_нас:**
  - `src/runtime/services/metrics.py` — canonical SDK-native ``pipeline_latency_seconds`` (Histogram) and ``rag_pipeline_events_total`` (Counter) with default ``prometheus_client.REGISTRY``
  - `telegram_bot/services/metrics.py` — back-compat re-export shim (#2047)
  - `telegram_bot/metrics_server.py` — standalone ASGI ``/metrics`` endpoint using ``make_asgi_app()`` (#2057)
  - `services/bge-m3-api/app.py:588-589` — canonical mount pattern: ``make_asgi_app()`` + ``app.mount("/metrics", metrics_app)``
  - `telegram_bot/handlers/command_handlers.py::cmd_metrics` — admin ``/metrics`` Telegram command uses ``generate_latest()``
- **паттерны:**
  - BСЕГДА использовать package-wide default ``prometheus_client.REGISTRY`` — не создавать кастомный ``CollectorRegistry``
  - ASGI экспозиция через ``make_asgi_app()`` (SDK-native)
  - ``generate_latest()`` для текстового дампа (Telegram команда или дебаг)
  - Метрики зарегистрированы на уровне модуля, а не внутри request-handler
- **gotchas:**
  - НЕ создавать кастомный ``CollectorRegistry()`` — ломает скрапинг через ``make_asgi_app``
  - НЕ писать кастомный HTTP-сервер для метрик — использовать ``make_asgi_app()`` + ``uvicorn``
  - ``TELEGRAM_BOT_METRICS_PORT`` (default 9092) — internal-only exposure
  - Контрактный тест: ``tests/contract/test_no_custom_metrics_registry_contract.py``

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

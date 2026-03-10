# SDK-First в tmux-swarm-orchestration — План реализации

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Вшить SDK-first логику в tmux-swarm скилл и создать проектный SDK-реестр для rag-fresh, чтобы агенты/воркеры всегда проверяли SDK-решения перед написанием кастомного кода.

**Architecture:** SDK-реестр живёт в `.claude/rules/sdk-registry.md` (проектный, автоподгружается). Скилл `tmux-swarm-orchestration` получает обязательную Phase 2.7 с автоматическим матчингом triggers из реестра. Worker contracts получают SDK-FIRST правило и `{sdk_registry_excerpt}`.

**Tech Stack:** Markdown (скиллы, rules), Context7 MCP (SDK docs), GrepAI/LSP (codebase context)

---

### Task 1: Создать SDK-реестр для rag-fresh

**Files:**
- Create: `.claude/rules/sdk-registry.md`

**Step 1: Создать файл реестра**

```markdown
# SDK Registry — rag-fresh

> Источник правды о SDK-решениях проекта. Агенты и воркеры проверяют этот файл
> ПЕРЕД написанием кода. SDK-first: если задача покрывается SDK — используй SDK.
>
> **Обновление:** при добавлении/удалении зависимости — обнови этот файл.
> Формат расширяемый: добавляй новые секции по шаблону внизу.

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
  - `telegram_bot/dialogs/states.py` — все StatesGroup (19 классов)
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
  - Score boosting: FormulaQuery с exp_decay
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
  - instructor.from_openai(AsyncOpenAI) → client.chat.completions.create(response_model=PydanticModel)
  - max_retries=2 для автоматического retry при validation error
  - Результат merge с regex extraction (regex wins на числовых полях)
- **gotchas:**
  - НЕ писать кастомный JSON parsing из LLM — использовать instructor + Pydantic model
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
  - CallbackHandler для LangChain/agent calls
  - PII masking через mask= параметр при Langfuse()
  - Prompt management: client.get_prompt(name) с TTL cache + fallback
- **gotchas:**
  - НЕ использовать openai.AsyncOpenAI напрямую — только langfuse.openai.AsyncOpenAI
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
  - has_job(job_id) для тестов
  - @observe() на job methods для Langfuse tracing
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

## cocoindex
- **triggers:** ingestion, ingest, indexing, pipeline, docling, chunker, embedding pipeline
- **context7_id:** /cocoindex-io/cocoindex
- **как_у_нас:**
  - `src/ingestion/unified/flow.py` — main flow definition
  - `src/ingestion/unified/targets/qdrant_hybrid_target.py` — custom target connector
- **паттерны:**
  - cocoindex.init(Settings(database=..., app_namespace="unified"))
  - @cocoindex_function() для pure Python operators
  - flow_builder.add_source(LocalFile(...)) → .transform() → collector.export()
  - FlowLiveUpdater для watch mode, flow.update() для one-shot
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
```

**Step 2: Проверить что файл корректный**

Run: `head -5 .claude/rules/sdk-registry.md`
Expected: `# SDK Registry — rag-fresh`

**Step 3: Commit**

```bash
git add .claude/rules/sdk-registry.md
git commit -m "docs(rules): add SDK registry for rag-fresh

Source of truth for all SDK solutions used in the project.
Agents/workers check this before writing custom code."
```

---

### Task 2: Изменить Phase 2.7 в SKILL.md — сделать обязательной

**Files:**
- Modify: `~/.claude/skills/tmux-swarm-orchestration/SKILL.md`

**Step 1: Заменить условную Phase 2.7 на обязательную**

Найти текущий блок Phase 2.7 (строки ~47-53) и заменить на:

```markdown
**Фаза 2.7: SDK КОНТЕКСТ** — **ОБЯЗАТЕЛЬНА** если `.claude/rules/sdk-registry.md` существует:

    # 1. Проверить наличие реестра:
    test -f .claude/rules/sdk-registry.md || echo "NO_REGISTRY"

    # 2. Если есть — прочитать и матчить triggers:
    Read .claude/rules/sdk-registry.md
    Для каждого SDK: сравнить triggers с issue body keywords
    Матч = SDK затронут → запомнить context7_id + как_у_нас + gotchas

    # 3. При матче — Sonnet субагент для актуальной документации:
    Agent(model="sonnet", subagent_type="general-purpose",
      prompt="Context7: resolve-library-id('{context7_id}') → query-docs('{topic из issue}')
      Резюме (300 слов) верни мне. Полный контекст → .claude/cache/sdk-{lib}-{N}.md")

    # 4. Собрать {sdk_registry_excerpt} — релевантные блоки из реестра для промта worker'а
    # Включает: как_у_нас + паттерны + gotchas для каждого совпавшего SDK

    # 5. Нет реестра — поведение как раньше (по усмотрению orch)

Переиспользование: одно исследование → N воркеров.
Даже без матча — {sdk_registry_excerpt} с полным списком SDK (только имена + triggers) для awareness.
```

**Step 2: Обновить таблицу конвейера**

В таблице "Конвейер" добавить "SDK?" перед каждым потоком (уже частично есть, убедиться что везде).

**Step 3: Обновить блок graphviz**

В `digraph flow` изменить label ноды sdk:
```
sdk [label="Фаза 2.7: SDK КОНТЕКСТ\nОБЯЗАТЕЛЬНО если sdk-registry.md\nматч triggers → Sonnet субагент"];
```

**Step 4: Проверить что SKILL.md валидный markdown**

Run: `head -60 ~/.claude/skills/tmux-swarm-orchestration/SKILL.md`
Expected: обновлённая Phase 2.7

**Step 5: Commit**

```bash
cd ~/.claude/skills/tmux-swarm-orchestration
git add SKILL.md
git commit -m "feat(tmux-swarm): make Phase 2.7 SDK research mandatory when registry exists"
```

---

### Task 3: Добавить SDK-FIRST в общие правила worker-contract.md

**Files:**
- Modify: `~/.claude/skills/tmux-swarm-orchestration/worker-contract.md`

**Step 1: Добавить SDK-FIRST правило в "Общие правила"**

После блока `SANDBOX:` и перед `ПРИ ОШИБКЕ:`, добавить:

```
    SDK-FIRST ПРАВИЛО:
    Если задача покрывается SDK из реестра — используй SDK, НЕ пиши кастом.
    Проверь {sdk_registry_excerpt} ниже ПЕРЕД написанием кода.
    Нашёл SDK решение → используй его паттерны и gotchas.
    Не нашёл → кастом допустим, но обоснуй в коммите почему.
```

**Step 2: Добавить {sdk_registry_excerpt} секцию в Контракт A**

После `SDK КОНТЕКСТ (если есть):` добавить:

```
    SDK РЕЕСТР (релевантные записи из .claude/rules/sdk-registry.md):
    {sdk_registry_excerpt}
```

**Step 3: Добавить {sdk_registry_excerpt} секцию в Контракт B**

Аналогично — после `SDK КОНТЕКСТ (если есть):`.

**Step 4: Добавить {sdk_registry_excerpt} секцию в Контракт D**

Аналогично — после `SDK КОНТЕКСТ (если есть):`.

**Step 5: Усилить Контракт C — обязательное чтение реестра**

В Контракт C после строки "Углуби SDK исследование если нужно" добавить:

```
    ОБЯЗАТЕЛЬНО: Read .claude/rules/sdk-registry.md (если существует).
    В плане — секция "SDK Coverage":
    - Какие SDK из реестра затронуты этой задачей
    - Какие SDK-паттерны использовать (из как_у_нас)
    - Если план предлагает кастом для чего-то из SDK — обосновать ПОЧЕМУ
```

**Step 6: Обновить SDK исследование субагентом — добавить реестр**

В блоке "SDK исследование субагентом" обновить prompt:

```
    Agent(
        description="SDK исследование для #{N}: {library}",
        prompt="""
        РЕЕСТР (из .claude/rules/sdk-registry.md):
        {sdk_registry_excerpt_for_this_library}

        Context7: resolve-library-id("{context7_id_from_registry}") → query-docs("{topic}")
        Exa: get_code_context_exa("{library} {topic} 2026")

        РЕЗУЛЬТАТ:
        А) Резюме (верни мне, макс 300 слов): ключевые сигнатуры, подход, SDK покрывает? ДА/НЕТ
           Сравни с "как_у_нас" из реестра — обнови если паттерн устарел.
        Б) Полный контекст (Write → .claude/cache/sdk-{library}-{N}.md):
           все сигнатуры, примеры, лучшие практики, анти-паттерны
        """,
        subagent_type="general-purpose",
        model="sonnet"
    )
```

**Step 7: Проверить файл**

Run: `grep -c "SDK-FIRST" ~/.claude/skills/tmux-swarm-orchestration/worker-contract.md`
Expected: `1`

Run: `grep -c "sdk_registry_excerpt" ~/.claude/skills/tmux-swarm-orchestration/worker-contract.md`
Expected: `5` (A, B, D, C, субагент)

**Step 8: Commit**

```bash
cd ~/.claude/skills/tmux-swarm-orchestration
git add worker-contract.md
git commit -m "feat(tmux-swarm): add SDK-FIRST rule and registry excerpt to all worker contracts"
```

---

### Task 4: Добавить SDK red-flag в red-flags.md

**Files:**
- Modify: `~/.claude/skills/tmux-swarm-orchestration/red-flags.md`

**Step 1: Прочитать текущий red-flags.md**

Run: `cat ~/.claude/skills/tmux-swarm-orchestration/red-flags.md`

**Step 2: Добавить SDK red-flag**

В чеклист добавить:

```markdown
### SDK-анти-паттерн
| Рационализация | Реальность |
|----------------|------------|
| "Быстрее написать самому" | SDK уже протестирован и поддерживается. Кастом = tech debt |
| "SDK слишком сложный" | Прочитай как_у_нас в реестре — паттерн уже отработан |
| "Мне нужна кастомная логика" | 90% случаев SDK покрывает. Проверь gotchas в реестре |
| "Не нашёл в SDK" | Context7 query-docs? Exa search? Реестр проверил? |
```

**Step 3: Commit**

```bash
cd ~/.claude/skills/tmux-swarm-orchestration
git add red-flags.md
git commit -m "feat(tmux-swarm): add SDK anti-pattern to red-flags checklist"
```

---

### Task 5: Синхронизировать локальную копию скилла в rag-fresh

**Files:**
- Sync: `/home/user/projects/rag-fresh/.claude/skills/tmux-swarm-orchestration/` ← `~/.claude/skills/tmux-swarm-orchestration/`

**Step 1: Скопировать обновлённые файлы**

```bash
cp ~/.claude/skills/tmux-swarm-orchestration/SKILL.md /home/user/projects/rag-fresh/.claude/skills/tmux-swarm-orchestration/SKILL.md
cp ~/.claude/skills/tmux-swarm-orchestration/worker-contract.md /home/user/projects/rag-fresh/.claude/skills/tmux-swarm-orchestration/worker-contract.md
cp ~/.claude/skills/tmux-swarm-orchestration/red-flags.md /home/user/projects/rag-fresh/.claude/skills/tmux-swarm-orchestration/red-flags.md
```

**Step 2: Проверить что копии идентичны**

```bash
diff ~/.claude/skills/tmux-swarm-orchestration/SKILL.md /home/user/projects/rag-fresh/.claude/skills/tmux-swarm-orchestration/SKILL.md
diff ~/.claude/skills/tmux-swarm-orchestration/worker-contract.md /home/user/projects/rag-fresh/.claude/skills/tmux-swarm-orchestration/worker-contract.md
diff ~/.claude/skills/tmux-swarm-orchestration/red-flags.md /home/user/projects/rag-fresh/.claude/skills/tmux-swarm-orchestration/red-flags.md
```

Expected: no output (files identical)

**Step 3: Commit в rag-fresh**

```bash
cd /home/user/projects/rag-fresh
git add .claude/skills/tmux-swarm-orchestration/SKILL.md .claude/skills/tmux-swarm-orchestration/worker-contract.md .claude/skills/tmux-swarm-orchestration/red-flags.md
git commit -m "feat(skills): sync tmux-swarm with SDK-first changes"
```

---

### Task 6: Добавить SDK maintenance правило в CLAUDE.md

**Files:**
- Modify: `/home/user/projects/rag-fresh/CLAUDE.md`

**Step 1: Добавить секцию в CLAUDE.md**

После секции "## Code Style" добавить:

```markdown
## SDK-First

**Правило:** перед написанием кода проверь `.claude/rules/sdk-registry.md` — если задача покрывается SDK, используй SDK.

**Обновление реестра:** при добавлении/удалении зависимости из `pyproject.toml` — обнови `.claude/rules/sdk-registry.md`.
```

**Step 2: Commit**

```bash
cd /home/user/projects/rag-fresh
git add CLAUDE.md
git commit -m "docs: add SDK-First rule to CLAUDE.md"
```

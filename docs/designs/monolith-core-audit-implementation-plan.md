# Аудит Архитектуры И План Реализации Монолитного Ядра

Статус: предлагается к исполнению
Дата: 2026-06-08
Связанные документы:

- [`product-simplification-e2e-plan.md`](product-simplification-e2e-plan.md)
- [`product-simplification-stage-0-decisions.md`](product-simplification-stage-0-decisions.md)
- [`unified-assistant-entrypoint-contract.md`](unified-assistant-entrypoint-contract.md)
- [`yaroslav-simplification-workflow.md`](yaroslav-simplification-workflow.md)

## 1. Цель Документа

Этот документ фиксирует аудит текущего состояния проекта и даёт подробный план
реализации будущего монолитного ядра ассистента.

Цель реализации — не переписать продукт заново, а развернуть ownership:

```text
сейчас:   telegram_bot владеет значимой частью RAG/runtime-логики
цель:     src.core + src.runtime владеют продуктовым ядром,
          telegram_bot остаётся production-адаптером
```

Главный результат:

```text
Telegram / E2E / будущий API
  -> src.core.run_assistant_request()
  -> src.runtime: classify -> retrieve -> generate -> grounding -> CRM proposal
  -> AssistantResult
```

## 2. Executive Summary

Проект уже движется в правильную сторону:

- Stage 0 принял направление на монолитное ядро в одном Python-процессе.
- `src/core/assistant.py` уже содержит публичную функцию
  `run_assistant_request()` и контракт `AssistantResult`.
- `src/runtime/` уже существует как место для shared runtime kernel.
- `tests/e2e_core/` уже содержит основу будущего live E2E: fixtures,
  golden cases, Qdrant helpers и harness.
- Статический layering ratchet уже доведён до пустого allowlist:
  `tests/data/known_layering_violations.json` содержит `{}`.

Главная оставшаяся проблема не в статических imports, а в runtime ownership:

- `src.core.assistant` при live dependencies динамически импортирует
  `telegram_bot.agents.rag_pipeline` и
  `telegram_bot.services.generate_response`.
- `src.runtime.graph.builder` по умолчанию всё ещё указывает на
  `telegram_bot.graph.graph:build_graph`.
- Grounding, generation, cache policy, response policy и часть pre-agent
  подготовки всё ещё принадлежат `telegram_bot`.
- `generate_response()` всё ещё смешивает core generation, Langfuse hooks,
  metrics и Telegram streaming/formatting concerns.
- `telegram_bot/bot.py` остаётся крупным orchestration модулем, где рядом живут
  Telegram transport, pre-agent logic, cache lookup, grounding mode и результат
  RAG.

План реализации должен быть инкрементальным: сначала защита поведения через
unit/contract/E2E, затем перенос runtime seams, затем подключение Telegram как
тонкого adapter, затем расширение golden E2E.

## 3. Фактическая Карта Кода

### 3.1. Размеры Основных Зон

Аудит строк Python-кода без учёта vendored virtualenv показал:

| Зона | Путь | Файлов | Строк | Будущая роль |
|---|---:|---:|---:|---|
| Bot services | `telegram_bot/services` | 66 | ~9.2k | Частично перенести в `src.runtime/*`, частично оставить adapter helpers |
| Bot agents | `telegram_bot/agents` | 17 | ~4.4k | RAG/tool logic переносить в runtime/domain |
| Bot graph | `telegram_bot/graph` | 25 | ~3.0k | Canonical graph должен быть в `src.runtime.graph` |
| Bot pipelines | `telegram_bot/pipelines` | 3 | ~0.7k | Client pipeline split: core runtime + Telegram adapter |
| Telegram dialogs | `telegram_bot/dialogs` | 23 | ~7.1k | Оставить в Telegram UI layer |
| Telegram handlers | `telegram_bot/handlers` | 6 | ~1.4k | Оставить в Telegram UI layer |
| Telegram keyboards | `telegram_bot/keyboards` | 7 | ~0.6k | Оставить в Telegram UI layer |
| Telegram middlewares | `telegram_bot/middlewares` | 6 | ~0.6k | Оставить transport/security layer |
| Core | `src/core` | 3 | ~0.7k | Публичный contract и entrypoint |
| Runtime | `src/runtime` | 18 | ~4.1k | Целевой дом для shared runtime kernel |
| Retrieval | `src/retrieval` | 5 | ~1.3k | Оставить core-facing retrieval helpers |
| Ingestion | `src/ingestion` | 27 | ~6.7k | Batch/offline ingestion path |
| API | `src/api` | 3 | ~0.5k | Optional adapter |
| Voice | `src/voice` | 8 | ~1.0k | Optional adapter |

Вывод: будущий монолит — это не перенос всего `telegram_bot`. Основной объём
UI (`dialogs`, `handlers`, `keyboards`, `middlewares`) должен остаться в
Telegram layer. Переносу подлежит только продуктовая и runtime-логика, которая
сейчас исторически живёт рядом с Telegram.

### 3.2. Текущие Product Entrypoints

| Entrypoint | Текущий модуль | Роль сейчас | Целевая роль |
|---|---|---|---|
| `run_assistant_request()` | `src/core/assistant.py` | Public skeleton/live seam, но live path динамически идёт в `telegram_bot` | Единственная core entrypoint для E2E/adapters |
| `PropertyBot._handle_query_supervisor()` | `telegram_bot/bot.py` | Главный Telegram text handler + orchestration | Adapter: собрать request context, вызвать core, отрендерить result |
| `run_client_pipeline()` | `telegram_bot/pipelines/client.py` | Deterministic path: classify/intent/RAG/generate/send/post-process | Split: runtime pipeline + Telegram send wrapper |
| `rag_pipeline()` | `telegram_bot/agents/rag_pipeline.py` | Retrieval/cache/grade/rerank/rewrite loop | `src.runtime.pipeline.rag_pipeline` или `src.runtime.retrieval` |
| `generate_response()` | `telegram_bot/services/generate_response.py` | LLM generation + grounding fallback + telemetry + Telegram streaming hooks | Core generation service + adapter streaming wrapper |
| `build_graph()` | `telegram_bot/graph/graph.py` | LangGraph factory | Canonical graph factory under `src.runtime.graph` |
| `POST /query` | `src/api/main.py` | Optional HTTP RAG API | Optional adapter over core if retained |
| Voice RAG client | `src/voice/*` | Optional voice surface | Optional adapter over core/API if retained |

## 4. Главные Архитектурные Находки

### 4.1. Static Layering Почти Исправлен, Но Runtime Coupling Остался

Статический contract проверяет `ast.Import` и `ast.ImportFrom` под `src/` и
`mini_app/`. Текущий allowlist пустой. Это хорошо, но не означает, что core уже
самостоятельный.

Оставшиеся coupling points:

| Coupling | Где | Почему важно | Целевое состояние |
|---|---|---|---|
| Dynamic import RAG | `src/core/assistant.py` -> `telegram_bot.agents.rag_pipeline` | Core live path зависит от bot package | `src.runtime.pipeline` |
| Dynamic import generation | `src/core/assistant.py` -> `telegram_bot.services.generate_response` | Ответ генерирует bot-owned module | `src.runtime.generation` |
| Graph default factory | `src/runtime/graph/builder.py` -> `telegram_bot.graph.graph:build_graph` | Runtime default указывает наружу в adapter | Default на `src.runtime.graph.graph:build_graph` |
| Generation transport leakage | `generate_response(message=...)` | Telegram streaming concern в generation service | Split core generation / Telegram streaming renderer |
| Grounding ownership | `telegram_bot.services.grounding_policy` + callers | Safety policy принадлежит bot layer | `src.runtime.grounding` |
| Cache policy ownership | `telegram_bot.services.cache_policy` | Response cache policy влияет на core result | `src.runtime.cache_policy` или runtime service |
| Langfuse hooks inside path | decorators/client calls in bot pipeline/generation | Optional diagnostics смешаны с product path | `log_event` first, optional instrumentation wrapper |

### 4.2. `src.core.assistant` Уже Правильный Public Contract, Но Нужен Split

Текущие dataclass-контракты полезны:

- `UserContext`
- `CoreDependencies`
- `CrmAction`
- `AssistantResult`
- `AssistantError`

Но они живут в одном файле с orchestration. Для роста лучше разделить:

```text
src/core/contracts.py     dataclass/protocol contracts
src/core/assistant.py     public entrypoint and orchestration shell
```

При этом первый implementation PR не обязан менять внешний импорт:
`src.core.__init__` может реэкспортировать старые имена.

### 4.3. Grounding — Обязательная Политика Ядра, Не Bot Helper

Grounding сейчас состоит из нескольких частей:

- detection of strict topics / strict query types;
- `grounding_mode` в state contract;
- safe fallback decision;
- semantic cache reuse policy;
- generation output flags (`grounded`, `legal_answer_safe`,
  `safe_fallback_used`, `semantic_cache_safe_reuse`);
- observability/cache metadata.

Целевой модуль:

```text
src/runtime/grounding/policy.py
src/runtime/grounding/contracts.py  (если понадобится)
```

Telegram может иметь shim:

```text
telegram_bot/services/grounding_policy.py
  # Deprecated: re-export shim, drop after migration cleanup.
  from src.runtime.grounding.policy import *
```

### 4.4. Generation Нужно Разделить На Core И Adapter Rendering

`generate_response()` сейчас делает слишком много:

- строит prompt/context;
- вызывает LLM streaming path;
- принимает `message` для Telegram streaming;
- форматирует/санитизирует ответ;
- пишет metrics и Langfuse metadata;
- применяет strict grounding fallback.

Целевой split:

```text
src/runtime/generation/service.py
  generate_answer(request, deps) -> GenerationResult

src/runtime/generation/context.py
  format retrieved docs for LLM context

src/runtime/generation/policy.py
  response style, coverage mode, fallback/default result helpers

telegram_bot/services/generate_response.py
  temporary shim or Telegram streaming wrapper
```

Правило: core generation не должен принимать Telegram `message` и не должен
сам отправлять сообщения. Он возвращает данные, которые adapter затем рендерит.

### 4.5. Ingestion Уже Достаточно Отделён

`src/ingestion` уже находится вне Telegram и должен оставаться offline/batch
частью. В online assistant path ingestion не должен становиться обязательной
runtime стадией. Для E2E он нужен как подготовка коллекции:

```text
test docs -> ingest/index -> Qdrant collection -> assistant request
```

### 4.6. Observability Должна Быть Product Logs First

Принятая модель Stage 0: structured JSON logs через `log_event(...)` — основной
механизм отладки. Langfuse/OTel могут оставаться, но не должны быть обязательным
runtime, CI или release gate.

Обязательные product events для core path:

- `assistant_request_started`
- `search_completed`
- `llm_completed`
- `grounding_completed`
- `crm_action_proposed`
- `assistant_request_completed`
- `dependency_failed`

## 5. Целевая Архитектура

### 5.1. Целевое Дерево

```text
src/
  core/
    __init__.py
    assistant.py              # run_assistant_request()
    contracts.py              # AssistantRequest/Result, UserContext, CrmAction
    dependencies.py           # optional Protocols / dependency bundle

  runtime/
    pipeline/
      assistant_pipeline.py   # classify -> retrieve -> generate -> grounding -> crm proposal
      contracts.py
    retrieval/
      service.py              # wrapper over existing retrieval/qdrant/rerank/cache path
      contracts.py
    generation/
      service.py              # pure core generation, no Telegram message send
      context.py
      contracts.py
    grounding/
      policy.py
    crm/
      actions.py              # propose only; no live writes without HITL
    graph/
      ...                     # canonical LangGraph modules if retained
    cache/
      policy.py               # semantic response cache policy if moved

  retrieval/                  # existing lower-level retrieval helpers
  ingestion/                  # existing batch/offline ingestion
  services/                   # external/client helpers already outside bot
  utils/product_events.py     # structured product logs

telegram_bot/
  bot.py / handlers / dialogs / keyboards / middlewares
  services/*                  # adapter-only helpers + temporary shims
  pipelines/*                 # temporary wrappers during migration
```

### 5.2. Dependency Direction

Allowed:

```text
telegram_bot -> src.core -> src.runtime -> src.retrieval/src.services/external clients
src/api      -> src.core
src/voice    -> src.core or optional API adapter
```

Forbidden for final state:

```text
src.core     -> telegram_bot
src.runtime  -> telegram_bot
src.retrieval -> telegram_bot
```

Temporary exception: compatibility shims under `telegram_bot/*` may re-export
from `src.runtime/*` until adapter imports are fully migrated.

### 5.3. Product Request Flow

```text
1. Adapter receives user input
   - Telegram Update
   - E2E direct call
   - optional API request

2. Adapter constructs AssistantRequest/UserContext
   - query
   - collection
   - request_id
   - user/session context
   - filters/role/language

3. src.core.run_assistant_request()
   - emits assistant_request_started
   - delegates to runtime assistant pipeline

4. Runtime pipeline
   - classify query
   - detect topic/filter/grounding hints
   - retrieve from Qdrant via existing hybrid path
   - rerank/grade/cache according to policy
   - generate answer via LLM provider
   - apply grounding/no-data/safe-fallback policy
   - propose CRM action only as data

5. Core returns AssistantResult
   - response_text
   - route/request_type
   - retrieved_doc_ids/sources/count
   - grounding fields
   - cache/generation metadata
   - proposed_crm_action, if any
   - request_id/latency/error fields

6. Adapter renders result
   - Telegram sends text/buttons/sources
   - HITL buttons confirm or reject CRM writes
   - E2E asserts product facts and logs
```

## 6. Реализационный План

План рассчитан на маленькие PR с сохранением поведения. Каждый этап должен
оставлять runnable state и focused tests.

### Phase A — Зафиксировать Аудит И Текущую Карту

**Цель:** чтобы команда договорилась о реальном состоянии и порядке миграции.

**Deliverables:**

- этот документ;
- обновлённый index в `docs/designs/README.md`;
- no runtime behavior changes.

**Checks:**

```bash
uv run pytest tests/contract/test_layering_no_telegram_bot_imports_contract.py -q
```

**Exit criteria:**

- план виден из design docs index;
- в документе явно различены static import violations и runtime coupling.

### Phase B — Укрепить Public Core Contract

**Цель:** сделать `src.core` стабильной поверхностью до переноса логики.

**Tasks:**

1. Создать `src/core/contracts.py`.
2. Перенести туда `UserContext`, `CoreDependencies`, `CrmAction`,
   `AssistantResult`, `AssistantError` или оставить `AssistantError` в
   `assistant.py`, если так проще.
3. Добавить `AssistantRequest` как явный request object:

   ```python
   @dataclass
   class AssistantRequest:
       query: str
       collection: str
       user_context: UserContext = field(default_factory=UserContext)
       request_id: str = ""
   ```

4. Сохранить backward compatibility текущей функции:

   ```python
   async def run_assistant_request(query: str, *, collection: str, ...)
   ```

5. Обновить `src/core/__init__.py` re-exports.
6. Расширить `tests/unit/core/test_assistant_entrypoint.py`:
   - import-only без Telegram;
   - skeleton mode без dependencies;
   - request_id propagation;
   - error result shape.

**Risks:** низкие. Это contract-only split.

**Exit criteria:**

- public imports не ломаются;
- no new `telegram_bot` imports under `src`;
- unit core tests pass.

### Phase C — Перенести Grounding Policy В Runtime

**Цель:** safety policy принадлежит ядру, а не Telegram.

**Tasks:**

1. Создать `src/runtime/grounding/policy.py`.
2. Перенести функции:
   - `is_high_risk_grounding_request`
   - `get_grounding_mode`
   - `is_strict_grounding_safe`
   - `semantic_cache_safe_reuse_allowed`
   - `should_safe_fallback`
   - `build_safe_fallback_response`
3. Оставить shim в `telegram_bot/services/grounding_policy.py`.
4. Переключить internal callers, где безопасно:
   - `telegram_bot/pipelines/client.py`
   - `telegram_bot/bot.py`
   - `telegram_bot/services/generate_response.py`
5. Добавить/обновить unit tests на новый canonical module.

**Write scope:**

```text
src/runtime/grounding/*
telegram_bot/services/grounding_policy.py
telegram_bot/pipelines/client.py
telegram_bot/bot.py
telegram_bot/services/generate_response.py
tests/unit/... grounding tests
```

**Risks:** средние. Grounding влияет на cache reuse и safe fallback.

**Mitigation:** сначала перенос без изменения логики, byte-for-byte где возможно,
затем tests.

**Exit criteria:**

- старые imports продолжают работать через shim;
- strict/no-data fallback behaviour не меняется;
- focused grounding/generation/client-pipeline tests pass.

### Phase D — Выделить Runtime Generation Core

**Цель:** отделить генерацию ответа от Telegram отправки сообщений.

**Tasks:**

1. Создать `src/runtime/generation/contracts.py`:

   ```text
   GenerationRequest
   GenerationResult
   GenerationDependencies
   ```

2. Создать `src/runtime/generation/service.py` с core-facing функцией:

   ```python
   async def generate_answer(request: GenerationRequest, deps: GenerationDependencies) -> GenerationResult:
       ...
   ```

3. Перенести pure helpers:
   - context formatting;
   - source/citation sanitization if not Telegram-specific;
   - fallback result shaping;
   - grounding fallback integration.
4. Оставить Telegram streaming и send-specific code в `telegram_bot`.
5. Сделать `telegram_bot/services/generate_response.py` thin wrapper:
   - вызывает `src.runtime.generation.generate_answer`;
   - если `message` передан, выполняет adapter streaming/rendering;
   - сохраняет старую signature на время миграции.
6. Обновить tests:
   - core generation без Telegram message;
   - wrapper compatibility;
   - safe fallback;
   - no documents / missing corpus.

**Risks:** высокие. Здесь смешаны LLM, streaming, formatting, Langfuse, metrics.

**Mitigation:** split по return-shape first, не менять prompt/LLM behavior в этом
PR. Langfuse hooks оставить wrapper-level до отдельного optionalization pass.

**Exit criteria:**

- core generation можно вызвать без Telegram imports и без `message`;
- old `generate_response()` callers работают;
- no user-visible answer behavior change outside intentional tests.

### Phase E — Перенести RAG Pipeline Ownership

**Цель:** core больше не должен динамически импортировать
`telegram_bot.agents.rag_pipeline`.

**Tasks:**

1. Создать `src/runtime/pipeline/rag.py` или
   `src/runtime/retrieval/service.py`.
2. Перенести `rag_pipeline()` как canonical implementation.
3. Оставить shim:

   ```text
   telegram_bot/agents/rag_pipeline.py -> src.runtime.pipeline.rag
   ```

4. Переключить callers:
   - `src/core/assistant.py`
   - `telegram_bot/pipelines/client.py`
   - tests where practical.
5. Сохранить old signature до завершения adapter migration.
6. Обновить docs/runtime README, если текущий migration table устарел.

**Risks:** высокие. RAG pipeline большой и связан с cache/qdrant/reranker/LLM
state.

**Mitigation:** PR должен быть mostly `git mv` + import rewrite + shim. Не менять
алгоритмы retrieve/grade/rerank/rewrite.

**Exit criteria:**

- `src.core.assistant` больше не импортирует `telegram_bot.agents.rag_pipeline`;
- legacy import path works through shim;
- focused RAG pipeline tests pass;
- E2E harness can call core path with dependencies.

### Phase F — Собрать `src.runtime.pipeline.assistant_pipeline`

**Цель:** единая runtime orchestration функция становится реальным ядром.

**Target API:**

```python
async def run_assistant_pipeline(
    request: AssistantRequest,
    dependencies: CoreDependencies,
) -> AssistantResult:
    ...
```

**Responsibilities:**

- classify;
- topic/filter/grounding hints;
- cache pre-check or delegate to RAG pipeline;
- retrieval/rerank/grade;
- generation;
- grounding completion;
- CRM action proposal;
- product logs;
- convert exceptions to recoverable `AssistantResult`.

**Tasks:**

1. Move live orchestration from `src/core/assistant.py` into runtime pipeline.
2. Keep `src.core.run_assistant_request()` as thin public wrapper.
3. Add `grounding_completed` log event.
4. Add optional `proposed_crm_action` plumbing as data only.
5. Add focused tests with fake dependencies.

**Exit criteria:**

- `src/core/assistant.py` has no dynamic imports from `telegram_bot`;
- `src.core` remains import-safe;
- all product logs include `request_id`;
- core tests cover success, cache hit, generation, fallback, dependency failure.

### Phase G — Подключить Telegram Как Тонкий Adapter

**Цель:** Telegram text path вызывает core entrypoint и рендерит
`AssistantResult`.

**Tasks:**

1. В `PropertyBot` собрать adapter dependency bundle once at startup:
   - cache;
   - embeddings;
   - sparse embeddings;
   - qdrant;
   - reranker;
   - llm;
   - config.
2. В text handler заменить direct orchestration на:

   ```python
   result = await run_assistant_request(
       user_text,
       collection=config.qdrant_collection,
       user_context=UserContext(...),
       dependencies=core_dependencies,
   )
   ```

3. Оставить legacy branch behind feature flag на 1-2 PR, если риск высок:

   ```text
   ASSISTANT_CORE_ENTRYPOINT_ENABLED=true
   ```

4. Adapter renders:
   - `response_text`;
   - sources;
   - HITL buttons for `proposed_crm_action`;
   - fallback/error messages.
5. Перенести Telegram-specific formatting out of runtime.
6. Добавить smoke tests:
   - adapter calls core with expected context;
   - result rendering;
   - error result rendering;
   - CRM HITL proposal rendering.

**Risks:** высокие. `telegram_bot/bot.py` содержит много edge cases:
streaming, cache, pre-agent filters, role/agent intent, feedback, handoff.

**Mitigation:** feature flag + shadow logging: сначала core result может
считаться в тестовом mode без замены отправки, затем включение для golden path.

**Exit criteria:**

- основной text flow может идти через `run_assistant_request()`;
- старый behavior сохранён или доступен behind rollback flag;
- Telegram smoke не является главным product proof.

### Phase H — Live E2E Golden Path

**Цель:** доказать продукт через core, не через Telegram.

**Tasks:**

1. Довести `tests/e2e_core/live_harness.py` до полного пути:

   ```text
   synthetic docs -> indexing/upsert -> Qdrant -> run_assistant_request -> assertions
   ```

2. Добавить live tests:
   - ingest + answer;
   - missing-in-corpus no-claim;
   - grounding strict fallback;
   - CRM/HITL proposal with mock CRM;
   - dependency failure shape.
3. Добавить/стабилизировать `make e2e-core-live`.
4. Добавить artifact writing:
   - query;
   - retrieved docs;
   - answer;
   - assertion result;
   - relevant product logs.

**Exit criteria:**

- `make e2e-core-live` доказывает real Qdrant + embeddings + LLM path или
  documented opt-in real LLM variant;
- Telegram не участвует в main E2E gate;
- artifacts достаточны для debugging.

### Phase I — Optional Surface Simplification

**Цель:** после защищённого golden path перестать держать optional surfaces как
обязательные release proof.

**Tasks:**

1. API: если нужен, сделать adapter over core. Если нет — пометить optional.
2. Voice: оставить optional route, не release gate.
3. Mini App: оставить optional; не должен тянуть Telegram internals.
4. Langfuse/OTel: optional diagnostics only.
5. k8s/monitoring: не основной local validation path.

**Exit criteria:**

- required checks не зависят от Langfuse/voice/mini app/k8s;
- docs ясно показывают core proof first;
- optional surfaces имеют маленькие smoke checks или явный статус.

### Phase J — Cleanup И Contract Ratchets

**Цель:** закрепить новую архитектуру статическими и runtime guardrails.

**Tasks:**

1. Добавить contract: `src/core` и `src/runtime` не содержат строковых dynamic
   imports `telegram_bot.*`, кроме allowlisted comments/docs if needed.
2. Добавить contract: `src.runtime.graph.builder.DEFAULT_FACTORY_SPEC` не
   указывает на `telegram_bot`.
3. Добавить contract: `generate_answer` не принимает Telegram `message`.
4. Удалить temporary feature flag после стабилизации.
5. Удалить shims по заранее принятому cleanup issue.
6. Обновить README architecture snapshot.

**Exit criteria:**

- dependency arrows enforced;
- old bot-owned RAG path удалён или shim-only;
- docs больше не утверждают устаревшее состояние.

## 7. Рекомендуемый Порядок PR

| PR | Название | Основной write scope | Риск | Проверки |
|---|---|---|---|---|
| 0 | Audit + implementation plan | `docs/designs/*` | Низкий | doc grep + layering contract |
| 1 | Core contracts split | `src/core/*`, `tests/unit/core/*` | Низкий | unit core + layering contract |
| 2 | Grounding runtime move | `src/runtime/grounding/*`, shims, focused callers/tests | Средний | grounding/generation/client tests |
| 3 | Generation core split | `src/runtime/generation/*`, `telegram_bot/services/generate_response.py` | Высокий | generation tests + client pipeline tests |
| 4 | RAG pipeline runtime move | `src/runtime/pipeline/*`, rag shim, core assistant | Высокий | RAG tests + core assistant tests |
| 5 | Runtime assistant pipeline | `src/runtime/pipeline/assistant_pipeline.py`, `src/core/assistant.py` | Средний | core success/error/cache tests |
| 6 | Telegram adapter integration | `telegram_bot/bot.py`, adapter tests | Высокий | bot smoke + focused integration |
| 7 | E2E golden path | `tests/e2e_core/*`, Makefile/docs | Средний | `make e2e-core-live` |
| 8 | Optional surfaces/docs cleanup | API/voice/docs/contracts | Средний | check + contract + smoke |
| 9 | Ratchets/shim cleanup | contracts, old shims | Средний | full focused contract suite |

## 8. Test Strategy

### 8.1. Per-PR Fast Checks

Baseline for docs/contract PRs:

```bash
uv run pytest tests/contract/test_layering_no_telegram_bot_imports_contract.py -q
```

Core contract changes:

```bash
uv run pytest tests/unit/core/ -q
uv run pytest tests/contract/test_layering_no_telegram_bot_imports_contract.py -q
```

Runtime move changes:

```bash
uv run pytest tests/unit/core/ -q
uv run pytest tests/unit/pipelines/test_client_pipeline.py -q
uv run pytest tests/contract/test_layering_no_telegram_bot_imports_contract.py -q
```

Generation/grounding changes:

```bash
uv run pytest tests/unit/pipelines/test_client_pipeline.py -q
uv run pytest tests/unit/core/ -q
```

E2E changes:

```bash
make e2e-core-live
```

### 8.2. Product Acceptance Checks

Golden cases should assert product behavior, not exact full answer text:

- required facts are present;
- forbidden facts are absent;
- expected docs are retrieved;
- missing corpus questions do not hallucinate;
- strict grounding either cites enough evidence or returns safe fallback;
- CRM writes are only proposed, never executed without HITL.

### 8.3. Observability Checks

Every request through core should be reconstructable by `request_id` from
structured logs:

```text
assistant_request_started
search_completed
llm_completed
grounding_completed
assistant_request_completed
```

Errors should use stable `error_type` values:

- `service_unavailable`
- `dependency_failed`
- `validation_error`
- `timeout`
- `rate_limited`

## 9. Main Risks And Mitigations

| Risk | Impact | Mitigation |
|---|---|---|
| Generation split changes user-visible answers | High | First PR keeps prompts/context behavior unchanged; wrapper compatibility tests |
| Telegram streaming gets broken | High | Keep streaming in adapter wrapper; feature flag rollout |
| Cache policy diverges in strict grounding | High | Move grounding first with no logic changes; focused cache tests |
| RAG pipeline move causes import cycles | Medium | `git mv` + shims; no algorithm change in move PR |
| Langfuse decorators keep core non-optional | Medium | Do not remove immediately; wrap after core E2E is stable |
| E2E flakiness from real LLM | Medium | Separate mock/fake LLM fast path from opt-in real LLM where necessary |
| Too much provider abstraction | Medium | Add protocols only when demanded by tests/callers; avoid platform rebuild |
| Large `telegram_bot/bot.py` makes adapter PR risky | High | Shadow mode + small render tests + keep rollback flag briefly |

## 10. Decisions Needed From Артём

Before implementation beyond low-risk contract moves:

1. Should Telegram text path switch to core behind a feature flag first, or should
   the branch cut directly once E2E is green?
2. Should `src/api` remain a maintained adapter, or be explicitly optional until
   a real consumer appears?
3. What is the minimal acceptable live E2E dependency set:
   - Qdrant + local embeddings + fake LLM;
   - Qdrant + local embeddings + real LLM opt-in;
   - Qdrant + service embeddings + real LLM?
4. Which CRM actions must appear in first `CrmAction` contract?
5. How long should legacy `telegram_bot.*` shims remain after migration?

## 11. Definition Of Done For The Monolith

The monolith implementation is complete when all statements below are true:

- `src.core.run_assistant_request()` executes the real product path without
  importing `telegram_bot` statically or dynamically.
- `src.runtime` owns classification/retrieval/generation/grounding/CRM proposal
  orchestration.
- `telegram_bot` is a production adapter: receive, call core, render,
  confirm/reject HITL.
- `make e2e-core-live` or its accepted equivalent proves the core product path
  against prepared documents and Qdrant.
- Langfuse/OTel/voice/mini app/k8s are optional diagnostics/surfaces, not
  required proof of product correctness.
- CRM writes remain behind explicit HITL confirmation.
- Documentation and contract tests enforce the dependency direction.

## 12. Immediate Next Step

After this audit lands, start with **PR 1: Core contracts split**. It is the
lowest-risk code PR and gives later PRs a stable target without moving RAG logic
yet.

Suggested first task description:

```text
Extract src.core contracts into src/core/contracts.py, add AssistantRequest,
preserve run_assistant_request() compatibility, and extend unit tests for
skeleton/error result shape. Do not move RAG/generation yet.
```

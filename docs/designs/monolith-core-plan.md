# Монолитное Ядро Ассистента — Единый План (Аудит + Фазы + Issues)

Статус: предлагается к исполнению
Дата: 2026-06-08
Заменяет (консолидирует в один документ):

- `monolith-core-audit-implementation-plan.md` (аудит + фазы A..J)
- `monolith-core-issue-backlog.md` (issues `CORE-001` … `CORE-010` + milestone)

Связанные документы:

- [`product-simplification-e2e-plan.md`](product-simplification-e2e-plan.md)
- [`product-simplification-stage-0-decisions.md`](product-simplification-stage-0-decisions.md)
- [`unified-assistant-entrypoint-contract.md`](unified-assistant-entrypoint-contract.md)
- [`yaroslav-simplification-workflow.md`](yaroslav-simplification-workflow.md)
- ADR: [`../adr/0015-sdk-native-baseline.md`](../adr/0015-sdk-native-baseline.md),
  [`../adr/0010-voice-path-create-agent-migration-plan.md`](../adr/0010-voice-path-create-agent-migration-plan.md),
  [`../adr/0012-langgraph-orchestration.md`](../adr/0012-langgraph-orchestration.md),
  [`../adr/0019-core-text-path-procedural-runtime.md`](../adr/0019-core-text-path-procedural-runtime.md)

---

## 0. Как Читать Этот Документ

Это **единый источник правды** по стабилизации монолитного ядра. Он объединяет:

1. аудит текущего кода (раздел 3);
2. архитектурные находки, включая сверку с SDK-native baseline (разделы 4–5);
3. целевую архитектуру и направление зависимостей (раздел 6);
4. фазы реализации A..J (раздел 7);
5. milestone, правила выполнения и спецификации issues `CORE-001…CORE-010`
   (раздел 8) — каждая issue замаплена на фазу;
6. стратегию тестов, риски, нужные решения и Definition of Done (разделы 9–12).

Маппинг фаза → issue зафиксирован в разделе 8.1, чтобы план и трекер не
расходились.

---

## 1. Цель

Развернуть ownership продуктового ядра, не переписывая продукт:

```text
сейчас:   telegram_bot владеет значимой частью RAG/runtime-логики
цель:     src.core + src.runtime владеют продуктовым ядром,
          telegram_bot остаётся production-адаптером
```

Главный результат:

```text
Telegram / E2E / опциональный API
  -> src.core.run_assistant_request()
  -> src.runtime: classify -> retrieve -> generate -> grounding -> CRM proposal
  -> AssistantResult
```

Не цель текущего пакета работ:

- не удалять voice, Mini App, API, Langfuse, OTel, k8s, monitoring;
- не трогать production CRM write paths;
- не добавлять новые зависимости;
- не делать один большой PR «сделать монолит».

---

## 2. Executive Summary

Проект уже движется в правильную сторону:

- Stage 0 принял направление на монолитное ядро в одном Python-процессе.
- `src/core/assistant.py` уже содержит публичную `run_assistant_request()` и
  контракт `AssistantResult`.
- `src/runtime/` уже существует как место для shared runtime kernel.
- `tests/e2e_core/` содержит основу live E2E: fixtures, golden cases, Qdrant
  helpers, harness.
- Статический layering ratchet доведён до пустого allowlist:
  `tests/data/known_layering_violations.json` == `{}`.

Главная оставшаяся проблема — не статические imports, а **runtime ownership**:

- `src.core.assistant` при live-зависимостях динамически импортирует
  `telegram_bot.agents.rag_pipeline` и `telegram_bot.services.generate_response`.
- `src.runtime.graph.builder.DEFAULT_FACTORY_SPEC` всё ещё указывает на
  `telegram_bot.graph.graph:build_graph`.
- Grounding, generation, cache policy, response policy и часть pre-agent
  подготовки принадлежат `telegram_bot`.
- `generate_response()` смешивает core generation, Langfuse hooks, metrics и
  Telegram streaming/formatting.

Дополнительно (см. раздел 5): план обязан быть сверен с **ADR 0015 (SDK-native
baseline)**, иначе перенос рискует закрепить кастомный/легаси код вместо движения
к `create_agent`.

---

## 3. Фактическая Карта Кода

### 3.1. Размеры Основных Зон

| Зона | Путь | Файлов | Строк (≈) | Будущая роль |
|---|---:|---:|---:|---|
| Bot services | `telegram_bot/services` | 66 | 9.2k | Частично в `src.runtime/*`, частично adapter helpers |
| Bot agents | `telegram_bot/agents` | 17 | 4.4k | RAG/tool logic → runtime/domain |
| Bot graph | `telegram_bot/graph` | 25 | 3.0k | См. раздел 5: миграция на `create_agent`, не релокация |
| Bot pipelines | `telegram_bot/pipelines` | 3 | 0.7k | Split: core runtime + Telegram adapter |
| Telegram dialogs | `telegram_bot/dialogs` | 23 | 7.1k | Оставить в Telegram UI layer |
| Telegram handlers | `telegram_bot/handlers` | 6 | 1.4k | Оставить в Telegram UI layer |
| Telegram keyboards | `telegram_bot/keyboards` | 7 | 0.6k | Оставить в Telegram UI layer |
| Telegram middlewares | `telegram_bot/middlewares` | 6 | 0.6k | Оставить transport/security layer |
| Core | `src/core` | 3 | 0.7k | Публичный contract и entrypoint |
| Runtime | `src/runtime` | 18 | 4.1k | Целевой дом для shared runtime kernel |
| Retrieval | `src/retrieval` | 5 | 1.3k | Core-facing retrieval helpers |
| Ingestion | `src/ingestion` | 27 | 6.7k | Batch/offline ingestion |
| API | `src/api` | 3 | 0.5k | Optional adapter |
| Voice | `src/voice` | 8 | 1.0k | Optional adapter |

> Примечание: размеры приблизительные на 2026-06-08. Точные цифры считать в момент
> исполнения фазы (`tokei`/`cloc` или `git ls-files '*.py' | xargs wc -l`),
> не полагаться на эти значения как на ratchet.

Вывод: монолит — это **не** перенос всего `telegram_bot`. UI-объём (`dialogs`,
`handlers`, `keyboards`, `middlewares`) остаётся в Telegram layer. Переносу
подлежит только продуктовая/runtime-логика, исторически живущая рядом с Telegram.

### 3.2. Текущие Product Entrypoints

| Entrypoint | Модуль | Роль сейчас | Целевая роль |
|---|---|---|---|
| `run_assistant_request()` | `src/core/assistant.py` | Public seam; live path динамически идёт в `telegram_bot` | Единственная core entrypoint |
| `PropertyBot._handle_query_supervisor()` | `telegram_bot/bot.py` | Главный Telegram text handler; уже `create_agent` SDK (#413) | Adapter: собрать context, вызвать core, отрендерить |
| `run_client_pipeline()` | `telegram_bot/pipelines/client.py` | Deterministic path: classify/intent/RAG/generate/send | Split: runtime pipeline + Telegram send wrapper |
| `rag_pipeline()` | `telegram_bot/agents/rag_pipeline.py` | Retrieval/cache/grade/rerank/rewrite | `src.runtime.pipeline` / `src.runtime.retrieval` |
| `generate_response()` | `telegram_bot/services/generate_response.py` | LLM gen + grounding fallback + telemetry + Telegram streaming | Core generation service + adapter streaming wrapper |
| `build_graph()` | `telegram_bot/graph/graph.py` | Voice-path кастомный StateGraph | **Миграция на `create_agent` (#1535)**, не релокация — см. раздел 5 |
| `POST /query` | `src/api/main.py` | Optional HTTP RAG API | Optional adapter over core |
| Voice RAG client | `src/voice/*` | Optional voice surface | Optional adapter over core/API |

---

## 4. Архитектурные Находки

### 4.1. Static Layering Исправлен, Runtime Coupling Остался

Статический contract проверяет `ast.Import`/`ast.ImportFrom` под `src/` и
`mini_app/`; allowlist пуст. Это хорошо, но core ещё не самостоятельный.

| Coupling | Где | Почему важно | Целевое состояние |
|---|---|---|---|
| Dynamic import RAG | `src/core/assistant.py` → `telegram_bot.agents.rag_pipeline` | Core live path зависит от bot package | `src.runtime.pipeline` |
| Dynamic import generation | `src/core/assistant.py` → `telegram_bot.services.generate_response` | Ответ генерирует bot-owned module | `src.runtime.generation` |
| Graph default factory | `src/runtime/graph/builder.py` → `telegram_bot.graph.graph:build_graph` | Runtime default указывает в adapter | См. раздел 5 |
| Generation transport leakage | `generate_response(message=...)` | Telegram streaming concern в generation | Split core gen / Telegram renderer |
| Grounding ownership | `telegram_bot.services.grounding_policy` | Safety policy в bot layer | `src.runtime.grounding` |
| Cache policy ownership | `telegram_bot.services.cache_policy` | Response cache policy влияет на core result | `src.runtime` service |
| Langfuse hooks inside path | decorators/client в bot pipeline/generation | Optional diagnostics смешаны с product path | `log_event` first, optional wrapper |

### 4.2. `src.core.assistant` — Правильный Контракт, Нужен Split

Контракты `UserContext`, `CoreDependencies`, `CrmAction`, `AssistantResult`,
`AssistantError` полезны, но живут в одном файле с orchestration. Разделить на
`src/core/contracts.py` (контракты) и `src/core/assistant.py` (entrypoint shell),
с реэкспортом старых имён из `src/core/__init__.py`.

### 4.3. Grounding — Политика Ядра, Не Bot Helper

Целевой дом: `src/runtime/grounding/policy.py` (+ shim в
`telegram_bot/services/grounding_policy.py`). Функции для переноса:
`is_high_risk_grounding_request`, `get_grounding_mode`, `is_strict_grounding_safe`,
`semantic_cache_safe_reuse_allowed`, `should_safe_fallback`,
`build_safe_fallback_response`.

### 4.4. Generation Разделить На Core И Adapter Rendering

`generate_response()` делает слишком много (prompt/context, LLM streaming,
`message` для Telegram, форматирование, metrics+Langfuse, strict fallback).
Целевой split: `src/runtime/generation/{service,context,policy,contracts}.py`,
а Telegram streaming/send — в `telegram_bot`. Правило: **core generation не
принимает Telegram `message` и сам сообщения не отправляет**.

### 4.5. Ingestion Уже Отделён

`src/ingestion` вне Telegram и остаётся offline/batch. В online assistant path
ingestion не должен быть обязательной runtime-стадией; для E2E он — подготовка
коллекции.

### 4.6. Observability — Product Logs First

`log_event(...)` — основной механизм. Langfuse/OTel опциональны, не release gate.
Обязательные события core path: `assistant_request_started`, `search_completed`,
`llm_completed`, `grounding_completed`, `crm_action_proposed`,
`assistant_request_completed`, `dependency_failed`.

---

## 5. Сверка С SDK-native Baseline (ADR 0015) И ADR-0019 — Ключевая Поправка

Эта секция — добавление к исходному аудиту. Без неё план рискует либо закрепить
кастомный legacy-код вместо движения к SDK-native adapter surfaces, либо ошибочно
перенести ownership core text RAG path в `create_agent`, что ADR-0019 уже отклонил.

**Примечание:** ADR-0019 (принят 2026-06-08) определил, что core text RAG path
— процедурный runtime через `run_assistant_pipeline()`, а не `create_agent`.
Создание `create_agent` остаётся SDK-native baseline для adapter/conversational
shell surfaces (Telegram, voice). См. `docs/adr/0019-core-text-path-procedural-runtime.md`.

### 5.1. Что Уже SDK-native В Коде

- **Telegram adapter text shell уже на `langchain.agents.create_agent` v1** +
  `before_model` middleware (`telegram_bot/agents/agent.py`,
  `telegram_bot/bot.py` — `_handle_query_supervisor`, «#413 — replaces
  build_supervisor_graph»). Это не меняет ADR-0019: canonical core text RAG
  path остаётся procedural runtime.
- Существует SDK-native middleware-слой
  `telegram_bot/graph/middleware/{cache,classify,guard}.py` — create_agent-совместимые
  замены легаси StateGraph-нод (зонтик #1535).
- Voice-путь мигрирует на `create_agent` (`telegram_bot/agents/voice_agent.py`,
  ADR 0010, #1535).
- Кастомный 5-tier cache (`src/runtime/integrations/cache.py`) — обоснованный
  custom по ADR 0015, **уже в `src/runtime`**.

### 5.2. Три Нестыковки Исходного Плана

1. **Релокация `build_graph` ≠ миграция.** Исходный план предлагал «канонический
   graph должен жить в `src.runtime.graph`». Но `build_graph` — это voice-path
   кастомный StateGraph, помеченный на удаление в пользу `create_agent` (ADR 0010
   / #1535). Перенос в `src.runtime` придаёт ему постоянство.
   **Решение:** не релоцировать `build_graph`; довести миграцию на `create_agent`
   (#1535) и удалить его. До закрытия #1535 — держать как явный временный shim,
   а `DEFAULT_FACTORY_SPEC` развязать через runtime-нейтральный фабричный модуль.

2. **`run_assistant_pipeline` — процедурный core, `create_agent` — adapter shell.**
   ADR-0019 решил: канонический текстовый путь — procedural runtime через
   `run_assistant_pipeline()`. `create_agent` остаётся для Telegram/voice adapter
   flows (conversational behavior, tool loops, history trimming, streaming).
   `run_assistant_pipeline()` не является обёрткой над `create_agent`; это
   самостоятельный procedural pipeline, владеющий classify/retrieve/generate/
   grounding/CRM proposal.

3. **Канонический путь определён (ADR-0019).** `rag_pipeline()` /
   `generate_response()` — код детерминированного `run_client_pipeline`. Решение
   принято: канонический текстовый путь — **процедурный (`run_assistant_pipeline`)**.
   `create_agent` — adapter shell only. Фазы E/F могут продолжать без блокера.

### 5.3. Принципы Сверки (обязательны на каждом code-PR)

- Любой новый custom поверх SDK требует строки-обоснования со ссылкой на ADR 0015.
- Перенос модуля не «легализует» легаси: если модуль — migration target (#1535),
  его переносят только как временный shim с привязкой к закрывающей issue.
- Middleware (`telegram_bot/graph/middleware/*`) — каноническая SDK-native замена
  StateGraph-нод для adapter/conversational shells; новые adapter-shell узлы
  добавлять как middleware/tools, не как StateGraph. Core text RAG behavior при
  этом остаётся за `run_assistant_pipeline()` по ADR-0019.

---

## 6. Целевая Архитектура

### 6.1. Целевое Дерево

```text
src/
  core/
    __init__.py
    assistant.py              # run_assistant_request() — public wrapper
    contracts.py              # AssistantRequest/Result, UserContext, CrmAction
    dependencies.py           # optional Protocols / dependency bundle
  runtime/
    pipeline/
      assistant_pipeline.py   # procedural core pipeline (ADR-0019)
      contracts.py
    retrieval/
      service.py              # wrapper над retrieval/qdrant/rerank/cache
      contracts.py
    generation/
      service.py              # pure core generation, без Telegram send
      context.py
      contracts.py
    grounding/
      policy.py
    crm/
      actions.py              # propose only; без live writes без HITL
    # graph/: НЕ канонический дом для build_graph; см. 5.2 / #1535
    cache/                    # cache policy если переносится из bot
  retrieval/ | ingestion/ | services/ | utils/product_events.py

telegram_bot/
  bot.py / handlers / dialogs / keyboards / middlewares
  agents/ graph/middleware/   # SDK-native create_agent + middleware (adapter shell only)
  services/*                  # adapter-only helpers + временные shims
  pipelines/*                 # временные wrappers на время миграции
```

### 6.2. Направление Зависимостей

Разрешено:

```text
telegram_bot -> src.core -> src.runtime -> src.retrieval/src.services/external
src/api      -> src.core
src/voice    -> src.core или optional API adapter
```

Запрещено в финале:

```text
src.core      -> telegram_bot
src.runtime   -> telegram_bot
src.retrieval -> telegram_bot
```

Временное исключение: compatibility shims под `telegram_bot/*` могут реэкспортить
из `src.runtime/*` до полной миграции adapter imports.

### 6.3. Product Request Flow

```text
1. Adapter получает вход (Telegram Update / E2E call / optional API)
2. Adapter строит AssistantRequest/UserContext (query, collection, request_id, ...)
3. src.core.run_assistant_request() -> assistant_request_started -> runtime
4. Runtime: classify -> hints -> retrieve(Qdrant hybrid) -> rerank/grade/cache
   -> generate(LLM) -> grounding/safe-fallback -> propose CRM action (data only)
5. Core возвращает AssistantResult (text, route, sources, grounding, metadata,
   proposed_crm_action?, request_id/latency/error)
6. Adapter рендерит: Telegram text/buttons/sources, HITL confirm/reject, E2E asserts
```

---

## 7. Фазы Реализации (A..J)

Маленькие PR с сохранением поведения; каждый этап оставляет runnable state и
focused tests.

- **Phase A — Зафиксировать аудит и карту.** Этот документ + обновлённый
  `docs/designs/README.md`. No runtime changes. Exit: план виден из index; static
  vs runtime coupling различены.
- **Phase B — Укрепить public core contract.** `src/core/contracts.py`,
  `AssistantRequest`, реэкспорты, расширить `tests/unit/core/`. Риск низкий.
- **Phase C — Перенести grounding policy в `src.runtime.grounding`.** + shim,
  переключить безопасных callers. Риск средний (cache reuse + safe fallback).
- **Phase D — Выделить runtime generation core.** `src/runtime/generation/*`;
  `generate_response()` → thin wrapper; убрать `message` из core. Риск высокий.
- **Phase E — Перенести RAG pipeline ownership.** `src/runtime/pipeline/rag.py`
  (+shim); `src.core.assistant` больше не импортит bot RAG. ADR-0019 уже снял
  прежний blocker №0: ownership идёт в procedural runtime, не в `create_agent`.
  Риск высокий.
- **Phase F — Собрать `src.runtime.pipeline.assistant_pipeline`** как процедурный
  core pipeline (ADR-0019). `run_assistant_request()` — public wrapper;
  `grounding_completed`; `proposed_crm_action` как данные. Риск средний.
- **Phase G — Telegram как тонкий adapter.** text path → `run_assistant_request()`;
  dependency bundle на старте; legacy branch за feature flag
  `ASSISTANT_CORE_ENTRYPOINT_ENABLED`. Риск высокий.
- **Phase H — Live E2E golden path.** `tests/e2e_core/live_harness.py`,
  `make e2e-core-live`, artifacts. Telegram вне main E2E gate.
- **Phase I — Optional surface simplification.** API/voice/miniapp/Langfuse/OTel/k8s
  явно optional; required checks от них не зависят.
- **Phase J — Cleanup и contract ratchets.** Contracts: нет dynamic
  `telegram_bot.*` под `src/core`+`src/runtime`; `DEFAULT_FACTORY_SPEC` не указывает
  в `telegram_bot`; `generate_answer` не принимает `message`. Удалить flags/shims.

---

## 8. Milestone И Issues

### 8.1. Маппинг Фаза → Issue

| Фаза | Issue | Название | Lane | Риск |
|---|---|---|---|---|
| A | (этот документ) | Audit + единый план | — | Низкий |
| B | `CORE-001` | Core contracts split | Quick execution | Низкий |
| C | `CORE-002` | Move grounding policy to runtime | Plan needed | Средний |
| J* | `CORE-003` | Runtime coupling ratchets | Plan needed | Низкий |
| D | `CORE-004` | Split generation core from Telegram rendering | Plan needed | Высокий |
| E | `CORE-005` | Move RAG pipeline ownership to runtime | Plan needed | Высокий |
| F | `CORE-006` | Build procedural runtime assistant pipeline | Plan needed | Средний |
| H | `CORE-007` | Core E2E golden path | Plan needed | Средний |
| G | `CORE-008` | Telegram thin adapter rollout | Plan needed | Высокий |
| I | `CORE-009` | Optional surfaces status cleanup | Design first | Средний |
| J | `CORE-010` | Shim cleanup and final docs | Plan needed | Средний |

\* `CORE-003` можно начинать рано (ratchet проектируется параллельно), закрывать в фазе J.

### 8.2. Milestone

```text
Milestone: Stabilize Core Monolith
Описание: Make the assistant core the only product owner for text RAG requests:
contracts first, then grounding/generation/RAG ownership, then Telegram as a thin
adapter, then one core E2E proof. Procedural runtime is canonical for core text
RAG; SDK-native `create_agent` stays adapter/conversational-shell only; optional
platform surfaces stay optional until core reliability is proven.
```

### 8.3. Правила Выполнения

1. Один issue = один архитектурный шов; явный allowed write scope.
2. Не запускать `uv sync`/`pip install`/`npm install`/`docker build`/`compose up`
   без отдельного решения.
3. Docs/plan PR — только лёгкие проверки (`git diff --check`, link check).
4. Code PR — только focused checks, если окружение готово.
5. Optional surfaces не делать обязательными для core proof.
6. CRM writes — только после HITL.
7. **Каждый code-PR сверяется с ADR 0015 (раздел 5.3).**

### 8.4. Week 1 Focus

Делаем: `CORE-001` (contracts), `CORE-002` (grounding), при наличии времени
проектирование `CORE-003` (ratchets). Не делаем: перенос `rag_pipeline()`, split
`generate_response()`, переключение Telegram на core, Docker/Compose/k8s,
Langfuse/OTel optionalization сверх docs/contracts, live CRM writes.

### 8.5. Краткие Спецификации Issues

Полные acceptance criteria см. в теле каждой GitHub issue (создаются по этому
документу). Сводка scope:

- **CORE-001** — `src/core/contracts.py` + `AssistantRequest`; сохранить
  `run_assistant_request()`; не трогать RAG/generation/Telegram/Docker.
- **CORE-002** — grounding → `src/runtime/grounding/policy.py` + shim; без смены
  порогов/текста.
- **CORE-003** — ratchet: нет строковых `telegram_bot.` в executable code под
  `src/core`+`src/runtime`; allowlist только сужается.
- **CORE-004** — `GenerationRequest/Result`; core gen без `message`; старый
  `generate_response()` — wrapper; prompts без изменений.
- **CORE-005** — `rag_pipeline()` → `src.runtime` (mostly `git mv` + shim); core
  не импортит bot RAG; алгоритмы не менять. **Блокер: решение №0.**
- **CORE-006** — `run_assistant_pipeline(request, deps)` как procedural core
  pipeline (ADR-0019); `run_assistant_request()` — public wrapper; product logs с
  `request_id`.
- **CORE-007** — live E2E: synthetic docs → Qdrant → core → asserts (required/
  forbidden facts, missing-corpus, grounding fallback); artifacts.
- **CORE-008** — Telegram text path → core; dependency bundle; рендер result +
  HITL; rollback flag.
- **CORE-009** — пометить API/voice/miniapp/Langfuse/OTel/k8s как optional;
  core proof — primary.
- **CORE-010** — удалить shims/flags после стабилизации; финальные docs;
  enforce dependency direction.

---

## 9. Стратегия Тестов

Per-PR fast checks:

```bash
# docs/contract
uv run pytest tests/contract/test_layering_no_telegram_bot_imports_contract.py -q
# core contract
uv run pytest tests/unit/core/ -q
# runtime move
uv run pytest tests/unit/pipelines/test_client_pipeline.py -q
# E2E
make e2e-core-live
```

Product acceptance (golden cases проверяют поведение, не точный текст):
required facts присутствуют; forbidden facts отсутствуют; нужные docs извлечены;
missing-corpus не галлюцинирует; strict grounding либо цитирует, либо safe
fallback; CRM только предлагается.

Observability: каждый запрос реконструируется по `request_id`. Стабильные
`error_type`: `service_unavailable`, `dependency_failed`, `validation_error`,
`timeout`, `rate_limited`.

---

## 10. Риски И Митигации

| Риск | Влияние | Митигация |
|---|---|---|
| Generation split меняет ответы | High | Первый PR не трогает prompts/context; wrapper-тесты |
| Telegram streaming ломается | High | Streaming в adapter wrapper; feature flag |
| Cache policy расходится в strict grounding | High | Перенос grounding первым без смены логики |
| RAG move вызывает import cycles | Medium | `git mv` + shims; без смены алгоритмов |
| Langfuse держит core non-optional | Medium | Не удалять сразу; wrap после стабильного E2E |
| E2E flakiness от real LLM | Medium | Отдельный fake-LLM fast path + opt-in real |
| Релокация `build_graph` закрепляет легаси | High | Не релоцировать; миграция #1535 (раздел 5.2) |
| `run_assistant_pipeline` дублирует `create_agent` | High | ADR-0019: procedural core — justified custom, не дубль. `create_agent` — adapter shell only. Обёртка не нужна. |
| Большой `telegram_bot/bot.py` | High | Shadow mode + render-тесты + rollback flag |

---

## 11. Нужные Решения

0. **(Решено в ADR-0019) Канонический текстовый путь — процедурный
   (`run_assistant_pipeline`).** `create_agent` — адаптер/conversational shell,
   не владелец core text RAG. См. `docs/adr/0019-core-text-path-procedural-runtime.md`.
   Фазы E/F могут продолжать.
1. Telegram переключать на core за feature flag или резать ветку сразу после
   зелёного E2E?
2. `src/api` — поддерживаемый adapter или явно optional до реального потребителя?
3. Минимальный live-E2E dependency set: Qdrant + BGE-M3 сервис + real LLM (opt-in) / или Qdrant + `local_bge_m3` (dev fallback) + fake LLM? **(Решено ADR-0020: production default = BGE-M3 сервис; `local_bge_m3` только dev/offline fallback.)**
4. Какие CRM actions нужны в первом `CrmAction` контракте?
5. Сколько держать легаси `telegram_bot.*` shims после миграции?

---

## 12. Definition Of Done

- `src.core.run_assistant_request()` выполняет реальный product path без
  статических/динамических импортов `telegram_bot`.
- `src.runtime` владеет classify/retrieval/generation/grounding/CRM proposal.
- `telegram_bot` — production adapter (receive → call core → render → HITL).
- `create_agent` остаётся SDK-native оркестрацией для adapter/conversational shell
  (Telegram, voice); **не** владеет core text RAG path (решено в ADR-0019).
  `build_graph` мигрирован/удалён по #1535, не релоцирован.
- `make e2e-core-live` (или принятый эквивалент) доказывает core path против
  подготовленных документов и Qdrant.
- Langfuse/OTel/voice/mini app/k8s — optional, не required proof.
- CRM writes — только за HITL.
- Documentation и contract tests enforce направление зависимостей.

---

## 13. Немедленный Следующий Шаг

После принятия этого документа стартовать с **`CORE-001` (Phase B: core contracts
split)** — самый низкорисковый code-PR, дающий стабильную цель остальным.

```text
Implement CORE-001 only. Extract assistant contracts into src/core/contracts.py,
add AssistantRequest, preserve src.core public imports and run_assistant_request()
behavior, update focused core tests if possible, and do not touch Telegram,
RAG pipeline, generation, Docker, or dependencies.
```

Рекомендуемая ветка: `simplification/core-001-core-contracts`.

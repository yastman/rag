# Контракт Единой Точки Входа Ассистента

Статус: предлагается
Дата: 2026-06-04
Этап плана: Этап 2 ([`product-simplification-e2e-plan.md`](product-simplification-e2e-plan.md))

## Назначение И Область Действия

Этот документ определяет контракт единой точки входа ядра ассистента — функции
или модуля, который принимает запрос пользователя и возвращает структурированный
результат, не требуя Telegram, HTTP API, голосового транспорта, Langfuse или OTel.

Контракт является дизайн-документом (архитектура / интерфейс). Изменения
поведения времени выполнения, переключение существующих путей на новую точку
входа и реализация E2E золотого пути выполняются в последующих задачах (#2336,
Этап 3 плана).

**Область действия:**

- Определить предлагаемую форму функции и тип результата.
- Указать, как существующие точки входа должны соотноситься с ядром.
- Зафиксировать повторное использование модулей и запрет параллельного
  RAG-конвейера.
- Описать поток данных и управления от E2E-вызова и Telegram-адаптера.
- Определить политику CRM/HITL.
- Определить требования к корреляции логов с `request_id` и `log_event`.
- Указать, что выходит за рамки этого контракта.
- Разделить решения, требующие утверждения Артёма, от решений разработчика.

**Не входит в область действия:**

- Реализация кода времени выполнения.
- Подключение Telegram к новой точке входа.
- Реализация E2E золотого пути (#2336).
- Записи в живую CRM, Langfuse/OTel как обязательный путь, новый HTTP-сервис,
  изменения Docker/k8s.
- Удаление старых точек входа или поверхностей.

## Текущие Точки Входа И Их Будущая Роль

Ниже перечислены все обнаруженные точки входа, которые получают пользовательский
текстовый запрос и доставляют ответ ассистента. Все они должны стать адаптерами
над единой точкой входа ядра или быть помечены как неосновные.

### Основные (должны стать адаптерами над ядром)

| Текущая точка входа | Модуль | Что делает сейчас | Будущая роль |
|---|---|---|---|
| `PropertyBot._handle_query_supervisor()` | `telegram_bot/bot.py:2209` | Главный обработчик текстовых сообщений Telegram. Классифицирует запрос, проверяет кэш, guard, запускает `run_client_pipeline()` или SDK-агента | **Telegram-адаптер**: вызывает `run_assistant_request()`, форматирует `AssistantResult` для отправки в чат |
| `run_client_pipeline()` | `telegram_bot/pipelines/client.py:187` | Детерминированный клиентский конвейер: classify → intent gate → `rag_pipeline()` → `generate_response()` → send | **Адаптер / внутренний путь**: вызывает ядро, добавляет Telegram-специфичную отправку сообщений |
| `POST /query` → `query()` → `_execute_query()` | `src/api/main.py:327` | HTTP API: `make_initial_state()` → `graph.ainvoke()` → `QueryResponse` | **Помечен как опциональный** (Этап 0, Решение 3). Может быть заменён адаптером, если нет реального потребителя |
| `RagApiClient.search_knowledge_base()` | `src/voice/rag_api_client.py:73` | Голосовой агент → HTTP POST /query → ответ | **Помечен как опциональный** (LiveKit). Может быть адаптером, если голосовой режим сохраняется |

### Внутренние конвейеры (переиспользуются ядром)

| Модуль | Что делает | Как переиспользовать |
|---|---|---|
| `rag_pipeline()` | `telegram_bot/agents/rag_pipeline.py:1008` | Поиск: cache → retrieve → grade → rerank → rewrite loop. Возвращает документы, не ответ. | **Переиспользовать как есть.** Ядро вызывает `rag_pipeline()`, затем генерирует ответ через `generate_response()` |
| `generate_response()` | `telegram_bot/services/generate_response.py:576` | Генерация: форматирует контекст, вызывает LLM (стриминг или нет), возвращает ответ | **Переиспользовать как есть.** Ядро вызывает после `rag_pipeline()`, если нет cache hit |
| `make_initial_state()` | `src/runtime/graph/state.py:108` | Фабрика начального состояния LangGraph | **Переиспользовать как есть** для пути LangGraph (если он сохраняется) |
| `GraphContext` | `src/runtime/graph/context.py:17` | TypedDict с cache, embeddings, sparse_embeddings, qdrant, reranker, llm, event_stream, guard_mode, classifier | **Переиспользовать как есть** как контейнер зависимостей |
| `classify_query()` | `telegram_bot/services/query_analyzer.py` | Классификация типа запроса (regex-only, ~0ms) | **Переиспользовать** как шаг классификации в ядре |
| `log_event()` | `src/utils/product_events.py:113` | Структурированное JSON-логирование (Stage 1, #2333) | **Использовать** как основной механизм логирования ядра |
| Эфемерный Qdrant helper | `tests/e2e_core/qdrant_helpers.py` | Создание/удаление изолированных коллекций (Stage 1, #2334) | **Использовать** в E2E-тестах (#2336) |

### Что НЕ переиспользуется (неосновное)

- Langfuse / `@observe` декораторы — не требуются для ядра (Решение 2 Этапа 0).
- OTel / `propagate_attributes` — не требуются для ядра (Решение 3 Этапа 0).
- `BotContext`, `BotResponse`, `PipelineResult` — Telegram-специфичные типы.
- `RagQueryRequest` / `RagApiClient` — HTTP-клиент для голосового режима.
- `QueryRequest` / `QueryResponse` (FastAPI) — HTTP-специфичные Pydantic-модели.
- `PipelineEventStream` (Redis streams) — остаётся в Telegram-пути, не в ядре.

**Важно:** Ядро не строит параллельный RAG-конвейер. Оно переиспользует
`rag_pipeline()` и `generate_response()` — те же функции, которые сегодня
вызывает Telegram. Это требование Этапа 2 плана упрощения.

## Предлагаемая Форма Функции

```python
async def run_assistant_request(
    query: str,
    *,
    collection: str,
    user_context: UserContext | None = None,
    request_id: str | None = None,
) -> AssistantResult:
    """Execute a single assistant request through the core pipeline.

    Args:
        query: User's natural-language query.
        collection: Qdrant collection name to search.
        user_context: Optional user/session context (role, session_id, etc.).
        request_id: Stable identifier for log correlation. Auto-generated
            from ``uuid4()`` if not provided.

    Returns:
        AssistantResult with response text, retrieved documents, timing,
        error info, and optional proposed CRM action.

    Raises:
        AssistantError: Wraps unrecoverable failures with structured error info.

    The function is the single entrypoint for:
      - Direct E2E calls (``make e2e-core-live``).
      - Telegram adapter (wraps Telegram Message, calls core, formats reply).
      - Future adapters (voice, mini-app) if those surfaces are kept.
    """
```

### `UserContext`

```python
@dataclass
class UserContext:
    """Minimal user/session context for core assistant.

    Deliberately minimal — no Telegram/LiveKit/FastAPI types.
    """

    user_id: str = ""
    session_id: str = ""
    role: str = "client"          # "client" | "manager"
    filters: dict[str, Any] | None = None  # Optional Qdrant search filters
    language: str = "ru"
```

### `AssistantResult`

```python
@dataclass
class AssistantResult:
    """Structured result from a single assistant request.

    All fields are populated by the core entrypoint. Fields needed by
    tests (#2336 golden cases) and adapters (Telegram, voice) are marked.
    """

    # ── Response ──
    response_text: str
    """Final answer text returned to the user (required by tests, adapters)."""

    # ── Routing ──
    route: str
    """Processing route: 'rag_search', 'chitchat', 'off_topic', 'guard_blocked',
    'cache_hit', 'agent_handoff', 'error'.
    Required for log correlation and test assertions (#2336)."""

    request_type: str
    """Request classification: 'GENERAL', 'APARTMENT_SEARCH', 'CHITCHAT',
    'MORTGAGE', 'OFF_TOPIC', etc. From ``classify_query()``."""

    # ── Retrieval ──
    retrieved_doc_ids: list[str]
    """Stable corpus/source document IDs for retrieved documents.

    These IDs are the values used by ``golden_cases.yaml`` checks
    (``must_retrieve`` / ``must_not_retrieve``), such as
    ``sunny_beach_studio`` or ``rules_hitl``. They are not Qdrant point IDs;
    adapters that need backend point identifiers should expose them through
    ``retrieved_sources`` metadata or a future separate field.
    """

    retrieved_sources: list[dict[str, str]]
    """Source metadata for each retrieved document: {'url': ..., 'title': ...}.
    Used by Telegram adapter for source footers."""

    documents_count: int
    """Number of documents retrieved."""

    # ── Timing ──
    latency_ms: float
    """Total wall-clock latency for the request (required by logs, tests)."""

    # ── Errors ──
    error_type: str | None
    """Machine-readable error type: 'recursion_limit', 'llm_timeout',
    'embedding_error', 'qdrant_unavailable', 'guard_blocked', etc.
    None on success (required by logs, tests)."""

    error_message: str | None
    """Human-readable error description for adapters (Telegram, voice)."""

    # ── CRM / HITL ──
    proposed_crm_action: CrmAction | None
    """If the assistant recommends a CRM action, it is returned here
    BEFORE any write. Adapters must obtain explicit confirmation before
    executing. Required by CRM/HITL tests (#2336)."""

    # ── Metadata ──
    request_id: str
    """Stable identifier for log correlation (same as input request_id or
    auto-generated). Required by log_event()."""

    cache_hit: bool
    llm_model: str | None
    llm_call_count: int
    rerank_applied: bool
```

### `AssistantError`

```python
class AssistantError(RuntimeError):
    """Unrecoverable error from the core assistant.

    Separate from ``AssistantResult.error_type`` — this is raised only
    when the core itself cannot produce a result (e.g., no Qdrant client
    configured, fatal config error). Recoverable errors (LLM timeout,
    embedding error) are returned as ``AssistantResult`` with ``error_type``
    set, not raised.
    """

    def __init__(self, message: str, *, error_type: str = "internal"):
        super().__init__(message)
        self.error_type = error_type
```

### `CrmAction`

```python
@dataclass
class CrmAction:
    """A CRM action proposed by the assistant, pending explicit confirmation.

    Must NOT be executed automatically. Adapters (Telegram) must present the
    action to the user and obtain confirmation before performing the write.
    In E2E, the mock CRM verifies that no write occurred before confirmation.
    """

    action_type: str  # 'create_lead', 'add_note', 'update_contact', etc.
    payload: dict[str, Any]  # CRM-specific payload
    summary: str  # Human-readable summary for confirmation UI
```

## Поток Данных И Управления

### Прямой E2E-вызов (#2336)

```text
E2E тест
  -> Qdrant helper: создать эфемерную коллекцию
  -> Docling/парсер: проиндексировать тестовые документы
  -> run_assistant_request(query, collection=..., user_context=...)
        -> classify_query(query)                         # тип запроса
        -> log_event("assistant_request_started", ...)    # начало
        -> rag_pipeline(query, ..., qdrant=..., ...)      # поиск
        -> log_event("search_completed", ...)             # поиск завершён
        -> generate_response(query, documents=...)        # генерация
        -> log_event("llm_completed", ...)                # LLM завершён
        -> собрать AssistantResult
  -> проверить AssistantResult по golden_cases.yaml
  -> Qdrant helper: удалить коллекцию
```

Прямой вызов не требует Telegram, HTTP, Langfuse, OTel или голосового режима.

### Telegram-адаптер (будущее состояние)

```text
Telegram Message
  -> PropertyBot.handle_query(message)                   # точка входа aiogram
        -> извлечь user_id, session_id, role
        -> создать UserContext
        -> run_assistant_request(query, ..., user_context=...)
        -> если AssistantResult.error_type:
             -> отправить error_message пользователю
        -> если AssistantResult.proposed_crm_action:
             -> показать подтверждение (инлайн-клавиатура)
             -> при подтверждении: выполнить CrmAction
        -> отправить AssistantResult.response_text в чат
        -> если AssistantResult.retrieved_sources:
             -> отправить источники
```

Telegram-адаптер не должен сам запускать `rag_pipeline()` или
`generate_response()` — только вызывать ядро и отображать результат.

## Политика CRM/HITL

1. **Предложение перед записью.** Ядро ассистента может предложить CRM-действие
   через `AssistantResult.proposed_crm_action`, но НЕ выполняет запись
   самостоятельно.

2. **Адаптер получает подтверждение.** Telegram-адаптер показывает пользователю
   предложенное действие (кнопка подтверждения) и выполняет запись только
   после явного согласия.

3. **E2E использует мок CRM.** Живые E2E-тесты (#2336) не трогают реальные
   пути записи в CRM. Мок CRM проверяет:
   - Действие предложено, но не выполнено до подтверждения.
   - После подтверждения выполнен ровно один вызов мока CRM.
   - Нет записей без предварительного предложения.

4. **Не в E2E:** Telegram-специфичные сценарии CRM, живые записи, голосовой
   режим CRM.

Это соответствует Решению 5 Этапа 0.

## Корреляция Логов

### Требования

- Каждый вызов `run_assistant_request()` получает стабильный `request_id`.
- E2E-тесты (#2336) передают явный `request_id` (например,
  `"e2e-beach-under-120k"`), чтобы связать логи и артефакты.
- Если `request_id` не передан, ядро генерирует `uuid4()`.
- Все продуктовые события пишутся через `log_event()` из Stage 1 (#2333).

### Обязательные события ядра

| Событие | Когда | Обязательные поля |
|---|---|---|
| `assistant_request_started` | Начало обработки запроса | `request_id`, `route` |
| `search_completed` | Завершение поиска в Qdrant | `request_id`, `retrieved_doc_ids`, `latency_ms`, `error_type` |
| `llm_completed` | Завершение генерации LLM | `request_id`, `llm_model`, `input_tokens`, `output_tokens`, `latency_ms`, `error_type` |
| `crm_action_proposed` | Предложено CRM-действие | `request_id`, `route` |
| `crm_action_confirmed` | CRM-действие подтверждено | `request_id`, `route` |
| `dependency_failed` | Отказ зависимости | `request_id`, `error_type`, `route` |
| `assistant_request_completed` | Завершение всего запроса | `request_id`, `route`, `latency_ms`, `error_type` |

### Обязательные поля `log_event`

Из [`product-simplification-e2e-plan.md`](product-simplification-e2e-plan.md) и
реализации `src/utils/product_events.py`:

- `event` — машинно-читаемое имя события;
- `request_id` — стабильный идентификатор;
- `route` или `request_type`;
- `latency_ms` для завершённых этапов;
- `error_type` для ошибок;
- `retrieved_doc_ids` для событий поиска;
- `llm_model`, `input_tokens`, `output_tokens` для LLM-событий.

`action_type` остаётся полем `CrmAction`, но не является обязательным полем
`log_event()` Stage 1: текущий helper фильтрует произвольные поля и пропускает
только перечисленный выше whitelist. Если будущая реализация должна писать
`action_type` в продуктовые события, сначала нужно расширить контракт
`src/utils/product_events.py`.

### Формат

JSON-строки через `ProductEventsFormatter`, одна строка на событие. Без
зависимости от Langfuse или OTel.

## Повторное Использование Существующих Модулей

Ядро **не создаёт параллельный RAG-конвейер**. Все функции ниже уже существуют
и используются Telegram-путём. Ядро вызывает их напрямую:

```text
run_assistant_request()
  ├── classify_query(query)                    # telegram_bot/services/query_analyzer.py
  ├── log_event(...)                           # src/utils/product_events.py
  ├── rag_pipeline(query, ...)                # telegram_bot/agents/rag_pipeline.py
  │     ├── _cache_check(...)                 # semantic cache (опционально)
  │     ├── _hybrid_retrieve(...)             # Qdrant поиск
  │     ├── _grade_documents(...)             # проверка релевантности
  │     ├── _rerank(...)                      # ColBERT / cross-encoder
  │     └── _rewrite_query(...)               # LLM-переформулировка
  ├── generate_response(query, documents=...) # telegram_bot/services/generate_response.py
  └── сборка AssistantResult
```

Зависимости ядра (инжектируются при создании):

- `QdrantService` (`src/runtime/services/qdrant.py`) — клиент Qdrant;
- `BGEM3HybridEmbeddings` / `BGEM3SparseEmbeddings` — эмбеддинги;
- `CacheLayerManager` — опциональный семантический кэш;
- `AsyncOpenAI` (или LiteLLM-обёртка) — LLM-клиент;
- Reranker (опционально).

Эти зависимости уже инициализируются в `PropertyBot.__init__()` и могут быть
переданы в ядро без изменений.

## Влияние На E2E (#2336)

Задача #2336 (Этап 3 плана) реализует первый живой E2E золотого пути поверх
этого контракта:

```python
# tests/e2e_core/test_live_ingest_answer.py (псевдокод)

async def test_golden_beach_under_120k(e2e_qdrant_collection, core_assistant):
    """Golden case: find a beach apartment under 120k."""
    # Дано: тестовые документы уже проиндексированы в e2e_qdrant_collection
    result = await core_assistant.run_assistant_request(
        query="Найди квартиру у моря до 120000",
        collection=e2e_qdrant_collection.name,
        request_id="e2e-beach-under-120k",
    )

    assert result.route == "rag_search"
    assert "sunny_beach_studio" in result.retrieved_doc_ids
    assert "Sunny Beach" in result.response_text
    assert "110000" in result.response_text
    assert "Mountain View Villa" not in result.response_text
    assert result.error_type is None
```

Поля `AssistantResult`, критичные для E2E:

| Поле | Использование в golden_cases.yaml |
|---|---|
| `response_text` | `must_contain`, `must_not_contain` |
| `route` | Проверка, что выбран правильный путь |
| `retrieved_doc_ids` | `must_retrieve`, `must_not_retrieve` |
| `documents_count` | Проверка количества документов |
| `error_type` | Проверка обработки ошибок |
| `proposed_crm_action` | CRM/HITL-сценарии |
| `latency_ms` | Опциональная проверка производительности |

## Решения, Требующие Утверждения Артёма

Эти вопросы зафиксированы здесь, но требуют явного решения Артёма:

1. **Расположение модуля ядра.** Где разместить `run_assistant_request()`:
   - `src/core/assistant.py` (новый модуль в `src/core/`);
   - `src/runtime/core.py` (рядом с существующим `GraphContext`);
   - `src/api/assistant.py` (рядом с `_execute_query`, но без HTTP-зависимости).

2. **Инжектирование зависимостей.** Как передавать Qdrant, embeddings, LLM:
   - Через явные параметры функции (текущее предложение);
   - Через объект-контейнер (`CoreDependencies` dataclass);
   - Через глобальный синглтон / реестр.

3. **Судьба пути LangGraph `graph.ainvoke()`.** Сохраняется ли
   `src/api/main.py:_execute_query()` → `app.state.graph.ainvoke()` как
   опциональный путь, или он полностью заменяется `run_assistant_request()`?

4. **Судьба `RagApiClient` и голосового режима.** Если голосовой режим
   сохраняется, должен ли он вызывать ядро напрямую (без HTTP) или через
   адаптер?

5. **Кэширование.** Должен ли семантический кэш быть частью ядра или
   опциональным слоем, который адаптеры (Telegram) включают самостоятельно?

## Решения Разработчика

Эти решения приняты на уровне дизайна и не требуют утверждения Артёма:

1. **Форма результата — dataclass.** `AssistantResult` — это `@dataclass`,
   а не Pydantic-модель. Зависимости: только стандартная библиотека Python.
   Pydantic используется только в HTTP-слое (FastAPI), который не является
   частью ядра.

2. **Ошибки возвращаются, а не выбрасываются.** Восстановимые ошибки
   (LLM timeout, embedding error, пустой результат поиска) возвращаются
   как `AssistantResult` с заполненным `error_type`. Только невосстановимые
   ошибки (нет Qdrant-клиента, фатальная ошибка конфигурации) выбрасываются
   как `AssistantError`.

3. **Асинхронная функция.** `async def` — все нижележащие зависимости
   (Qdrant, эмбеддинги, LLM) асинхронны.

4. **Поле `route` основано на реальных путях.** Значения `route` отражают
   текущие пути в `run_client_pipeline()` и `_handle_query_supervisor()`:
   `rag_search`, `chitchat`, `off_topic`, `guard_blocked`, `cache_hit`,
   `agent_handoff`, `error`.

5. **`UserContext` минимален.** Только поля, нужные ядру: `user_id`,
   `session_id`, `role`, `filters`, `language`. Никаких Telegram- или
   HTTP-специфичных полей.

6. **`CrmAction` — это данные, не поведение.** Ядро производит `CrmAction`
   как структуру данных. Выполнение всегда остаётся за адаптером.

7. **`log_event` используется, а не `PipelineEventStream`.** Ядро пишет
   продуктовые события через `log_event()` из Stage 1 (#2333), а не через
   Redis `PipelineEventStream`. Redis-стримы остаются в Telegram-пути.

## Последующие Задачи Реализации

После утверждения этого контракта:

| Задача | Описание | Зависит от |
|---|---|---|
| #2336 | Реализовать один живой E2E золотого пути: индексация → `run_assistant_request()` → проверка ответа | Этот контракт, Stage 1 fixtures |
| Создание модуля ядра | Реализовать `src/core/assistant.py` с `run_assistant_request()` | Решение Артёма о расположении |
| Подключение Telegram | Адаптировать `PropertyBot._handle_query_supervisor()` к вызову ядра | Работающее ядро, #2336 |
| CRM/HITL E2E | Добавить тест CRM/HITL к #2336 | Этот контракт, мок CRM |
| Удаление старых путей | Убрать `run_client_pipeline()` и SDK-агент из обязательного пути | Стабильный E2E золотого пути |

## Связанные Документы

- [`product-simplification-e2e-plan.md`](product-simplification-e2e-plan.md) —
  полный план упрощения (8 этапов). Этап 2: «Создать Единую Точку Входа Ядра».
- [`product-simplification-stage-0-decisions.md`](product-simplification-stage-0-decisions.md) —
  фиксация решений Этапа 0: монолитное ядро, Langfuse опционален, Telegram как
  продакшен-адаптер.
- [`yaroslav-simplification-workflow.md`](yaroslav-simplification-workflow.md) —
  процесс работы и модель веток.

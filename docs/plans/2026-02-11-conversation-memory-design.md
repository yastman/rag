# Conversation Memory — Design Document

**Date:** 2026-02-11
**Status:** Partially Implemented (see note below)
**Issue:** #239
**Scope:** Хранение истории переписки с клиентом + семантический поиск

> **2026-02-17 Alignment Note (#243):**
> - **Qdrant `conversation_history`** — IMPLEMENTED in `telegram_bot/services/history_service.py`.
> - **PostgresSaver** — NOT IMPLEMENTED, superseded by Redis checkpointer (already in use).
> - **LangMem** — deferred to future phase.
> - Canonical architecture: see `telegram_bot/agents/` (#240) and `telegram_bot/services/history_service.py` (#239).

## Проблема

Текущее состояние:
- История в Redis LIST: `conversation:{user_id}`, max 20 сообщений, TTL 2 часа
- `MemorySaver` — in-memory, теряется при рестарте
- Нет семантического поиска по истории
- Нет persistent thread state
- Менеджер не может искать по переписке с клиентом

## Архитектура

```
                        User Message
                             │
                     ┌───────┴───────┐
                     ▼               ▼
              PostgresSaver    Qdrant: conversation_history
              (thread state)   (Q&A пары, hybrid search)
              replaces         BGE-M3 dense 1024 + sparse
              MemorySaver      multi-tenant: user_id
                     │               │
                     │         ┌─────┴──────────┐
                     │         ▼                ▼
                     │    Bot auto-recall   Manager search
                     │    (top-3 контекст)  (full results)
                     │
                     ▼
              LangMem (background)
              - извлечение фактов из диалога
              - summarization старых сессий
              - → PostgresStore (user profile)
```

## Компоненты

### 1. PostgresSaver — persistent thread state

**Заменяет:** `MemorySaver` (in-memory, теряется при рестарте)

**Что делает:**
- Сохраняет состояние LangGraph графа между сообщениями в треде
- Persistent across restarts
- Thread-scoped (текущий диалог)

**Пакеты:**
```
langgraph-checkpoint-postgres
psycopg[binary,pool]
```

**Код:**
```python
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

DB_URI = "postgresql://postgres:postgres@localhost:5432/conversation_db"

async with AsyncPostgresSaver.from_conn_string(DB_URI) as checkpointer:
    graph = builder.compile(checkpointer=checkpointer)

    config = {
        "configurable": {
            "thread_id": f"tg_{chat_id}_{date}",
            "user_id": str(user_id),
        }
    }
    result = await graph.ainvoke(state, config)
```

**База данных:** Новая БД `conversation` в существующем PostgreSQL (pgvector:pg17).
Добавить в `docker/postgres/init-databases.sh`:
```sql
CREATE DATABASE conversation;
```

### 2. Qdrant collection — хранение Q&A + hybrid search

**Заменяет:** Redis LIST conversation (20 msg, 2h TTL, без поиска)

**Что делает:**
- Хранит все Q&A пары (вопрос + ответ как единица)
- Hybrid search: dense + sparse (BGE-M3) + ColBERT rerank
- Multi-tenant: изоляция по user_id
- Два потребителя: бот (auto-recall) и менеджер (поиск)

**Коллекция:**
```python
from qdrant_client.models import (
    VectorParams, SparseVectorParams, Distance,
    HnswConfigDiff, KeywordIndexParams, KeywordIndexType,
    PayloadSchemaType,
)

# Создание коллекции
client.create_collection(
    collection_name="conversation_history",
    vectors_config={
        "dense": VectorParams(
            size=1024,                    # BGE-M3
            distance=Distance.COSINE,
            hnsw_config=HnswConfigDiff(m=16, ef_construct=128),
            on_disk=True,
        ),
    },
    sparse_vectors_config={
        "sparse": SparseVectorParams(),
    },
)

# Tenant index для multi-tenancy
client.create_payload_index(
    collection_name="conversation_history",
    field_name="user_id",
    field_schema=KeywordIndexParams(
        type=KeywordIndexType.KEYWORD,
        is_tenant=True,                   # Qdrant v1.11+ co-location
    ),
)

# Timestamp index для хронологических запросов
client.create_payload_index(
    collection_name="conversation_history",
    field_name="timestamp",
    field_schema=PayloadSchemaType.INTEGER,
)
```

**Payload структура (Q&A пара):**
```json
{
    "id": "uuid-v4",
    "vectors": {
        "dense": [1024 dims],
        "sparse": {"indices": [...], "values": [...]}
    },
    "payload": {
        "user_id": "tg_123456",
        "query": "Какие налоги в Болгарии для нерезидентов?",
        "response": "В Болгарии действует плоская ставка ДДФЛ 10%...",
        "session_id": "chat-a1b2c3d4-20260211",
        "timestamp": 1739280000,
        "query_type": "STRUCTURED",
        "message_pair_index": 3
    }
}
```

**Эмбеддинг стратегия:**
- Эмбеддить конкатенацию `f"{query}\n{response}"` — поиск работает и по вопросу, и по ответу
- Использовать BGE-M3 `/encode/hybrid` endpoint (один вызов → dense + sparse)

**Поиск:**
```python
# Bot auto-recall: top-3 релевантных Q&A из истории юзера
results = await qdrant.hybrid_search_rrf(
    collection_name="conversation_history",
    query_dense=query_embedding,
    query_sparse=sparse_embedding,
    query_filter=Filter(must=[
        FieldCondition(key="user_id", match=MatchValue(value=f"tg_{user_id}")),
    ]),
    limit=3,
)

# Manager search: полные результаты с хронологией
results = await qdrant.hybrid_search_rrf(
    collection_name="conversation_history",
    query_dense=query_embedding,
    query_sparse=sparse_embedding,
    query_filter=Filter(must=[
        FieldCondition(key="user_id", match=MatchValue(value=f"tg_{client_id}")),
        FieldCondition(key="timestamp", range=Range(gte=start_ts, lte=end_ts)),
    ]),
    limit=20,
)
```

### 3. LangMem — background memory formation

**Что делает:**
- Извлекает факты из диалогов (preferences, interests, entities)
- Суммаризирует старые сессии
- Пишет в PostgresStore (user profile)
- Background job — латентность 60s OK

**Пакет:** `langmem`

**Типы памяти:**

| Тип | Пример | Хранилище |
|-----|--------|-----------|
| Semantic | "Пользователь интересуется 2-к квартирами в Софии" | PostgresStore |
| Episodic | "2 февраля обсуждали налоги — доволен ответом" | PostgresStore |
| Procedural | "Этому юзеру нужны короткие ответы на русском" | PostgresStore |

**Код (background worker):**
```python
from langmem import create_memory_manager

manager = create_memory_manager(
    "anthropic:claude-haiku-4-5-20251001",
    instructions="Извлекай факты о пользователе: интересы, предпочтения, "
                 "ключевые обсуждённые темы. Язык: русский.",
)

# После каждого диалога (async, background)
memories = await manager.ainvoke(
    {"messages": conversation_messages}
)

# Сохранить в PostgresStore
for memory in memories:
    await store.aput(
        ("user_profiles", str(user_id)),
        str(uuid4()),
        {"fact": memory.content, "timestamp": now(), "source": "extraction"},
    )
```

### 4. PostgresStore — user profile (long-term facts)

**Что делает:**
- Хранит извлечённые факты о юзере (от LangMem)
- Semantic search по фактам (pgvector)
- Cross-thread, cross-session
- Инжектится в ноды графа автоматически

**Код:**
```python
from langgraph.store.postgres.aio import AsyncPostgresStore

async with AsyncPostgresStore.from_conn_string(
    DB_URI,
    index={
        "dims": 1024,
        "embed": bge_m3_embeddings,     # наш BGE-M3 класс
        "fields": ["fact"],
    },
) as store:
    graph = builder.compile(
        checkpointer=checkpointer,
        store=store,
    )
```

**Использование в ноде:**
```python
async def generate_node(state, config, *, store: BaseStore):
    user_id = config["configurable"]["user_id"]

    # Подтянуть профиль юзера
    user_facts = await store.asearch(
        ("user_profiles", str(user_id)),
        query=state["messages"][-1].content,
        limit=5,
    )

    facts_text = "\n".join(f"- {f.value['fact']}" for f in user_facts)
    system_prompt = f"User context:\n{facts_text}\n\n{base_prompt}"
```

## Интеграция с существующим pipeline

### Изменения в LangGraph графе

```
БЫЛО (9 нод):
classify → cache_check → retrieve → grade → rerank → generate → cache_store → respond

СТАЛО (11 нод):
classify → history_recall → cache_check → retrieve → grade → rerank → generate → cache_store → history_store → respond
                                                                                                        ↓
                                                                                              LangMem (background)
```

**Новые ноды:**

1. **`history_recall_node`** — после classify, перед cache_check
   - Ищет в Qdrant conversation_history top-3 релевантных Q&A
   - Добавляет в state как дополнительный контекст
   - Пропускается для CHITCHAT / OFF_TOPIC

2. **`history_store_node`** — после cache_store, перед respond
   - Сохраняет текущую Q&A пару в Qdrant
   - Эмбеддит concat(query, response) через BGE-M3
   - Запускает LangMem extraction в background

### Изменения в RAGState

```python
class RAGState(TypedDict):
    # ... существующие поля ...

    # Новые поля для conversation memory
    history_context: list[dict]       # Релевантные прошлые Q&A (от history_recall)
    history_stored: bool              # Q&A сохранена в Qdrant
```

### Изменения в bot.py

```python
# БЫЛО
from langgraph.checkpoint.memory import MemorySaver
checkpointer = MemorySaver()

# СТАЛО
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
checkpointer = AsyncPostgresSaver.from_conn_string(DB_URI)
await checkpointer.setup()
```

## Data Lifecycle

```
Свежие (0-7 дней):
  - Qdrant: полные Q&A пары (verbatim)
  - PostgresSaver: thread state
  - PostgresStore: extracted facts

Средние (7-30 дней):
  - Qdrant: Q&A пары остаются
  - LangMem: суммаризация сессий → сжатые записи
  - PostgresSaver: thread state можно чистить

Старые (30-90 дней):
  - Qdrant: Q&A пары остаются (поиск менеджера)
  - PostgresStore: только ключевые факты

Архив (90+ дней):
  - Опционально: удалить из Qdrant
  - PostgresStore: факты сохраняются навсегда
```

**Retention job (pg_cron или celery):**
```python
# Ежедневно: суммаризировать сессии старше 7 дней
# Еженедельно: чистить thread state старше 30 дней
# Ежемесячно: опционально архивировать Q&A старше 90 дней
```

## Отклонённые варианты

| Вариант | Причина отклонения |
|---------|-------------------|
| **Supabase** | 15 контейнеров, 4GB RAM, overkill для одной таблицы |
| **Mem0** | Свой embedding pipeline, не работает с нашим Qdrant/BGE-M3 |
| **Zep** | Требует Neo4j, тяжёлый дополнительный сервис |
| **pgvector для поиска** | Dense-only cosine — слабее Qdrant hybrid RRF |
| **PostgresStore для поиска** | То же pgvector dense-only, без sparse/ColBERT |
| **Только Redis** | Нет семантического поиска, TTL 2h, max 20 msg |

## Новые зависимости

```toml
# pyproject.toml
[project.dependencies]
langgraph-checkpoint-postgres = ">=2.0.0"
psycopg = {extras = ["binary", "pool"], version = ">=3.2"}
langmem = ">=0.1.0"
```

## Новая инфраструктура

| Что | Где | Описание |
|-----|-----|----------|
| БД `conversation` | Существующий PostgreSQL | `docker/postgres/init-databases.sh` |
| Коллекция `conversation_history` | Существующий Qdrant | Init script при старте бота |
| LangMem background worker | В контейнере бота | Async task после каждого диалога |

**Новых контейнеров: 0**

## Env переменные

```bash
# Новые
CONVERSATION_DB_URI=postgresql://postgres:postgres@postgres:5432/conversation
CONVERSATION_COLLECTION=conversation_history
LANGMEM_MODEL=anthropic:claude-haiku-4-5-20251001  # для extraction
HISTORY_RECALL_LIMIT=3                              # top-K для auto-recall
HISTORY_RETENTION_DAYS=90                           # retention period

# Существующие (без изменений)
BGE_M3_URL=http://bge-m3:8000
QDRANT_URL=http://qdrant:6333
```

## Оценка трудозатрат

| Этап | Описание | Оценка |
|------|----------|--------|
| 1 | PostgresSaver замена MemorySaver | 2-3 часа |
| 2 | Qdrant collection + store/recall ноды | 4-6 часов |
| 3 | LangMem integration (background) | 3-4 часа |
| 4 | PostgresStore + user profile injection | 2-3 часа |
| 5 | Retention jobs | 2-3 часа |
| 6 | Manager search API/команда | 3-4 часа |
| 7 | Тесты | 4-6 часов |
| **Итого** | | **20-29 часов** |

## Риски

| Риск | Митигация |
|------|-----------|
| LangMem latency 60s | Background job, не блокирует pipeline |
| PostgreSQL перегрузка (5 БД) | Мониторинг, connection pooling |
| Qdrant объём растёт | Retention policy, snapshots |
| BGE-M3 доп. нагрузка (embed Q&A) | Async, batch embedding |
| LangMem API costs (Haiku) | Rate limiting, batch processing |

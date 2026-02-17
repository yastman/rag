# PostgresSaver for LangGraph Persistence — Implementation Plan

> **2026-02-17 Alignment Note (#243):**
> This plan was NOT implemented. Redis checkpointer is used for thread state.
> Conversation history is stored in Qdrant (`conversation_history` collection) via `HistoryService` (#239).
> PostgresSaver is no longer planned. See `telegram_bot/services/history_service.py`.

**Issue:** [#74](https://github.com/yastman/rag/issues/74) feat: enable PostgresSaver for LangGraph persistence
**Priority:** ~~P0~~ Superseded | **Effort:** Low (~30 min)
**Milestone:** ~~Deferred: Post-Baseline~~ Not Implemented

## Goal

Заменить MemorySaver (in-memory, теряет состояние при рестарте) на AsyncPostgresSaver
(persistent, checkpoint в PostgreSQL). Зависимость `langgraph-checkpoint-postgres>=2.0`
уже установлена в pyproject.toml:47.

## Текущее состояние

| Компонент | Файл | Строка | Статус |
|-----------|------|--------|--------|
| MemorySaver singleton | `telegram_bot/integrations/memory.py` | :13 | `checkpointer = MemorySaver()` |
| build_graph() принимает checkpointer | `telegram_bot/graph/graph.py` | :26 | `checkpointer: Any \| None = None` |
| bot.py НЕ передаёт checkpointer | `telegram_bot/bot.py` | :251 | `build_graph(cache=..., ...)` — нет checkpointer= |
| Postgres в docker-compose | `docker-compose.dev.yml` | :17 | `dev-postgres:5432`, user/pass: postgres/postgres |
| Init-скрипт создаёт БД | `docker/postgres/init/00-init-databases.sql` | — | langfuse, mlflow, litellm — нет БД для langgraph |
| Bot depends_on | `docker-compose.dev.yml` | :559 | redis, qdrant, bge-m3, user-base, litellm — нет postgres |
| BotConfig | `telegram_bot/config.py` | — | Нет DATABASE_URL / postgres_url |

## Архитектурное решение

**AsyncPostgresSaver** (async вариант) — бот полностью async (aiogram + LangGraph ainvoke).
Используем `from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver`.

**Connection:** `postgresql://postgres:postgres@postgres:5432/langgraph` — отдельная БД для
чистого разделения (langfuse, mlflow, litellm — свои БД).

**Lifecycle:** Создать checkpointer при старте бота (`PropertyBot.start()`), передавать
в `build_graph()`. Закрыть при `PropertyBot.stop()`.

## Шаги реализации

### Step 1: Создать БД `langgraph` в Postgres init-скрипте (2 мин)

**Файл:** `docker/postgres/init/00-init-databases.sql`
**Изменение:** Добавить после строки 16:

    -- Database for LangGraph checkpointer (conversation persistence)
    CREATE DATABASE langgraph;
    GRANT ALL PRIVILEGES ON DATABASE langgraph TO postgres;

**Примечание:** init-скрипт выполняется только при первом запуске PostgreSQL.
Для существующих инсталляций — выполнить вручную:

    docker exec dev-postgres psql -U postgres -c "CREATE DATABASE langgraph;"

### Step 2: Добавить LANGGRAPH_POSTGRES_URL в BotConfig (3 мин)

**Файл:** `telegram_bot/config.py`
**Изменение:** Добавить поле в класс BotConfig:

    langgraph_postgres_url: str = Field(
        default="",
        validation_alias=AliasChoices("LANGGRAPH_POSTGRES_URL", "langgraph_postgres_url"),
    )

Пустая строка по умолчанию = fallback на MemorySaver (graceful degradation).

### Step 3: Переписать memory.py — AsyncPostgresSaver + fallback (5 мин)

**Файл:** `telegram_bot/integrations/memory.py` (полная перезапись, 13 строк → ~35 строк)
**Изменение:**

    """LangGraph checkpointer — PostgresSaver (production) or MemorySaver (dev fallback)."""

    from __future__ import annotations

    import logging
    from contextlib import asynccontextmanager
    from typing import AsyncIterator

    from langgraph.checkpoint.base import BaseCheckpointSaver
    from langgraph.checkpoint.memory import MemorySaver

    logger = logging.getLogger(__name__)


    @asynccontextmanager
    async def create_checkpointer(postgres_url: str = "") -> AsyncIterator[BaseCheckpointSaver]:
        """Create checkpointer: AsyncPostgresSaver if URL provided, else MemorySaver.

        Args:
            postgres_url: PostgreSQL connection string. Empty = MemorySaver fallback.

        Yields:
            Configured checkpointer instance.
        """
        if not postgres_url:
            logger.info("Using MemorySaver (no LANGGRAPH_POSTGRES_URL)")
            yield MemorySaver()
            return

        from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

        async with AsyncPostgresSaver.from_conn_string(postgres_url) as saver:
            await saver.setup()  # создаёт таблицы если их нет
            logger.info("Using AsyncPostgresSaver (PostgreSQL)")
            yield saver

**Ключевые моменты:**
- `asynccontextmanager` — управление lifecycle (connection pool)
- `saver.setup()` — автоматическая миграция (создаёт таблицы checkpoints, writes)
- Fallback на MemorySaver — zero-config для dev без Postgres
- Удалить старый singleton `checkpointer = MemorySaver()`

### Step 4: Интегрировать checkpointer в PropertyBot (5 мин)

**Файл:** `telegram_bot/bot.py`

**4a.** Добавить import (после строки 21):

    from .integrations.memory import create_checkpointer

**4b.** Добавить атрибут в `__init__` (после строки 143, `self._cache_initialized`):

    self._checkpointer = None
    self._checkpointer_cm = None  # context manager для cleanup

**4c.** Инициализировать в `start()` (перед `check_dependencies`, ~строка 294):

    # Initialize LangGraph checkpointer (Postgres or MemorySaver fallback)
    self._checkpointer_cm = create_checkpointer(self.config.langgraph_postgres_url)
    self._checkpointer = await self._checkpointer_cm.__aenter__()

**4d.** Передать в `build_graph()` (строка 251):

    graph = build_graph(
        cache=self._cache,
        embeddings=self._embeddings,
        sparse_embeddings=self._sparse,
        qdrant=self._qdrant,
        reranker=self._reranker,
        llm=self._llm,
        message=message,
        checkpointer=self._checkpointer,  # <-- добавить
    )

**4e.** Закрыть в `stop()` (перед `self.bot.session.close()`, ~строка 316):

    if self._checkpointer_cm:
        await self._checkpointer_cm.__aexit__(None, None, None)

### Step 5: Добавить env var в docker-compose.dev.yml (2 мин)

**Файл:** `docker-compose.dev.yml`

**5a.** Добавить env var в bot service (после строки 558):

    # LangGraph persistence (PostgresSaver)
    LANGGRAPH_POSTGRES_URL: postgresql://postgres:postgres@postgres:5432/langgraph

**5b.** Добавить depends_on postgres (после строки 559):

    postgres:
      condition: service_healthy

### Step 6: Добавить env var в docker-compose.vps.yml (2 мин)

**Файл:** `docker-compose.vps.yml`
**Изменение:** Аналогично Step 5 — добавить LANGGRAPH_POSTGRES_URL и depends_on postgres
в секцию bot.

### Step 7: thread_id для graph.ainvoke() (3 мин)

**Файл:** `telegram_bot/bot.py`, метод `handle_query` (~строка 262)
**Изменение:** Передать config с thread_id при вызове:

    config = {"configurable": {"thread_id": str(message.chat.id)}}
    result = await graph.ainvoke(state, config=config)

`thread_id = chat_id` — каждый чат = отдельный thread. Это позволяет
LangGraph восстанавливать состояние между вызовами.

**Внимание:** Текущий RAGState — это TypedDict без MessagesState. Checkpointer
сохраняет полный state между вызовами. Для текущей архитектуры (каждый запрос =
новый make_initial_state) checkpointer фактически сохраняет snapshot последнего
запроса, а не историю сообщений. Полноценная conversation memory потребует
отдельного issue (расширение RAGState для messages history).

### Step 8: Обновить .env.example (1 мин)

**Файл:** `.env.example`
**Изменение:** Добавить:

    # LangGraph persistence (optional, fallback: in-memory)
    # LANGGRAPH_POSTGRES_URL=postgresql://postgres:postgres@localhost:5432/langgraph

## Test Strategy

### Unit тесты

| Тест | Файл | Что проверяем |
|------|------|---------------|
| MemorySaver fallback | `tests/unit/test_memory.py` | `create_checkpointer("")` yields MemorySaver |
| Config field | `tests/unit/test_config.py` | BotConfig с/без LANGGRAPH_POSTGRES_URL |

### Integration тесты

| Тест | Как запустить | Что проверяем |
|------|---------------|---------------|
| PostgresSaver setup | `make docker-up && pytest tests/integration/test_postgres_saver.py` | Подключение + setup() + checkpoint round-trip |
| Graph with checkpointer | `pytest tests/integration/test_graph_paths.py` | Существующие graph path тесты проходят с checkpointer=MemorySaver() |

### Manual тесты

1. `make docker-bot-up` — бот стартует без ошибок
2. Отправить 2 сообщения в Telegram → проверить логи "Using AsyncPostgresSaver"
3. `docker restart dev-bot` → отправить 3-е сообщение → state сохранён
4. Убрать `LANGGRAPH_POSTGRES_URL` → бот стартует с MemorySaver (graceful degradation)

## Acceptance Criteria

- [ ] `MemorySaver` заменён на `AsyncPostgresSaver` при наличии `LANGGRAPH_POSTGRES_URL`
- [ ] Graceful fallback на `MemorySaver` без URL (dev mode, тесты)
- [ ] БД `langgraph` создаётся автоматически через init-скрипт
- [ ] Bot depends_on postgres в docker-compose
- [ ] `thread_id` передаётся в `graph.ainvoke()`
- [ ] Существующие тесты проходят (`make test-unit`)
- [ ] Бот стартует и обрабатывает запросы (manual smoke test)

## Risks & Notes

1. **Init-скрипт не переиграется** на существующей инсталляции — нужна ручная
   команда `CREATE DATABASE langgraph` или пересоздание volume
2. **RAGState ≠ MessagesState** — checkpointer сохраняет state, но conversation
   history управляется через Redis CacheLayerManager (semantic cache). PostgresSaver
   даёт persistence для LangGraph state, не для chat history
3. **Connection pool** — `AsyncPostgresSaver.from_conn_string()` создаёт
   `psycopg_pool.AsyncConnectionPool` автоматически. Default pool size достаточен
   для single-bot deployment
4. **VPS:** Postgres уже работает для CocoIndex — достаточно добавить БД и env var

## Effort Estimate

| Step | Время |
|------|-------|
| 1. Init SQL | 2 мин |
| 2. BotConfig | 3 мин |
| 3. memory.py | 5 мин |
| 4. bot.py integration | 5 мин |
| 5-6. docker-compose | 4 мин |
| 7. thread_id | 3 мин |
| 8. .env.example | 1 мин |
| Unit test | 5 мин |
| **Total** | **~28 мин** |

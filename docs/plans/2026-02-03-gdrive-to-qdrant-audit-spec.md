# Аудит и ТЗ: GDrive → Qdrant Pipeline

> **Режим:** Только аудит + спецификация. Без правок кода/инфры.
>
> **Дата:** 2026-02-03
>
> **Ветка:** `audit/gdrive-to-qdrant-pipeline-spec`

---

## 0. Текущее рабочее дерево

```
 M docs/plans/2026-02-03-unified-ingestion-pipeline-impl-v3.2.md
 M scripts/monitor-workers.sh
 M src/ingestion/unified/flow.py
 M telegram_bot/test_openai.py
```

Незакоммиченные изменения от предыдущих итераций. Перед реализацией рекомендуется проверить `git status` и при необходимости откатить/сташить.

---

## 1. Целевая архитектура (как должно работать)

```
Google Drive
     ↓ (rclone sync, systemd timer 5min)
GDRIVE_SYNC_DIR (/data/drive-sync или ~/drive-sync)
     ↓ (CocoIndex sources.LocalFile, poll 60s)
CocoIndex Flow
     ├─ Detects: new / modified / deleted files
     ├─ Computes: file_id = sha256(relative_path)[:16]
     └─ Exports to: QdrantHybridTarget (custom connector)
                         ↓
              ┌─────────────────────────────────┐
              │ QdrantHybridTargetConnector     │
              │ (mutate method)                 │
              ├─────────────────────────────────┤
              │ 1. DoclingClient.chunk_file()   │
              │ 2. VoyageService.embed_docs()   │
              │ 3. FastEmbed BM42 sparse        │
              │ 4. Qdrant: DELETE + UPSERT      │
              │ 5. Postgres: state + DLQ        │
              └─────────────────────────────────┘
                         ↓
Telegram Bot читает через:
  - telegram_bot/services/qdrant.py (hybrid_search_rrf)
  - telegram_bot/services/small_to_big.py (expand_context)
```

---

## 2. Что уже реализовано (по v3.2.1)

| Компонент | Файл | Статус |
|-----------|------|--------|
| UnifiedConfig | `src/ingestion/unified/config.py` | ✅ Готов |
| UnifiedStateManager | `src/ingestion/unified/state_manager.py` | ✅ Готов |
| QdrantHybridWriter | `src/ingestion/unified/qdrant_writer.py` | ✅ Готов |
| QdrantHybridTargetSpec | `src/ingestion/unified/targets/qdrant_hybrid_target.py` | ✅ Готов |
| QdrantHybridTargetConnector | `src/ingestion/unified/targets/qdrant_hybrid_target.py` | ⚠️ Есть проблема P0.5 |
| CocoIndex Flow | `src/ingestion/unified/flow.py` | ⚠️ Есть проблемы P0.1-P0.4 |
| CLI | `src/ingestion/unified/cli.py` | ✅ Готов |
| Docker service | `docker-compose.dev.yml` | ✅ Готов |
| Makefile targets | `Makefile` | ✅ Готов |
| Postgres migration | `docker/postgres/init/03-unified-ingestion-alter.sql` | ✅ Готов |
| E2E tests | `tests/integration/test_unified_ingestion_e2e.py` | ✅ Готов |
| Payload contract tests | `tests/unit/ingestion/test_payload_contract.py` | ✅ Готов |

---

## 3. P0 блокеры (критические)

### P0.1 ❌ ИСПРАВЛЕНО: DataSlice.transform() и обычные Python-функции

**Симптом (был):**
```
ValueError: transform() can only be called on a CocoIndex function
```

**Причина:** CocoIndex 0.3.28 требует функции, зарегистрированные через `@cocoindex.op.function()`.

**Текущий статус:** ✅ **ИСПРАВЛЕНО** в `flow.py:53-70`

```python
@cocoindex_function()
def file_id_from_filename(filename: str) -> str:
    return compute_file_id(filename)

@cocoindex_function()
def mime_type_from_filename(filename: str) -> str:
    return get_mime_type(filename)
# ...
```

---

### P0.2 ❌ ИСПРАВЛЕНО: LocalFile row schema — путь через `_key`

**Симптом (был):**
```
Exception: field path not found
```

**Причина:** LocalFile возвращает:
- `_key` (ключ KTable) = полный путь файла
- `filename` (field) = относительный путь от корня
- `content` (field) = содержимое файла

**Текущий статус:** ✅ **ИСПРАВЛЕНО** в `flow.py:148`

```python
collector.collect(
    file_id=f["file_id"],
    abs_path=f["_key"],           # ← Используется _key для абсолютного пути
    source_path=f["filename"],    # ← filename = относительный путь
    # ...
)
```

**Документация CocoIndex:**
> LocalFile output schema:
> - `filename` (*Str*, key): the filename of the file, including the path, relative to the root directory
> - `content` (*Str* or *Bytes*): the content of the file

---

### P0.3 ⚠️ Инициализация CocoIndex и database settings

**Симптом:**
```
Database is required for this operation… set COCOINDEX_DATABASE_URL
```
или
```
init() не принимает database_url= аргумент
```

**Текущий код (`flow.py:93-98`):**
```python
cocoindex.init(
    setting.Settings(
        database=setting.DatabaseConnectionSpec(url=config.database_url),
        app_namespace=_app_namespace_for(config),
    )
)
```

**Статус:** ⚠️ **ТРЕБУЕТ ВЕРИФИКАЦИИ**

Код выглядит правильно по CocoIndex 0.3.28 API, но нужно проверить:
1. Что `config.database_url` действительно передаётся (env var `INGESTION_DATABASE_URL`)
2. Что init() вызывается до `open_flow()`

**Критерий приёмки:**
- `make ingest-unified` не падает на `cocoindex.init()`
- `cocoindex.setup_all_flows()` не требует env var `COCOINDEX_DATABASE_URL`

---

### P0.4 ✅ ИСПРАВЛЕНО: Namespace ограничения CocoIndex

**Симптом (был):**
```
NamingError: App namespace name ... must start with a letter or underscore
```

**Причина:** `app_namespace` должен соответствовать `[A-Za-z_][A-Za-z0-9_]*`

**Текущий статус:** ✅ **ИСПРАВЛЕНО** в `flow.py:78-84`

```python
def _app_namespace_for(config: UnifiedConfig) -> str:
    raw = f"unified__{config.collection_name}"
    cleaned = "".join(ch if (ch.isalnum() or ch == "_") else "_" for ch in raw)
    if not (cleaned[0].isalpha() or cleaned[0] == "_"):
        cleaned = f"_{cleaned}"
    return cleaned
```

---

### P0.5 ⚠️ asyncio.run() внутри mutate — риск блокировок

**Проблемный код (`qdrant_hybrid_target.py:186-198`):**
```python
@staticmethod
def mutate(
    *all_mutations: tuple[QdrantHybridTargetSpec, dict[str, QdrantHybridTargetValues | None]],
) -> None:
    for spec, mutations in all_mutations:
        for file_id, mutation in mutations.items():
            try:
                if mutation is None:
                    asyncio.run(QdrantHybridTargetConnector._handle_delete(spec, file_id))
                else:
                    asyncio.run(QdrantHybridTargetConnector._handle_upsert(spec, file_id, mutation))
```

**Проблема:**
1. `asyncio.run()` создаёт новый event loop на каждую мутацию
2. Если CocoIndex вызывает `mutate()` из async context — будет конфликт loops
3. В Docker/prod может вызывать зависания и флейки

**Варианты решения:**

| Подход | Плюсы | Минусы |
|--------|-------|--------|
| A) Sync клиенты везде | Простота | Переписывать VoyageService, DoclingClient |
| B) Shared event loop | Работает с async | Сложнее, нужен run_until_complete |
| C) ThreadPoolExecutor | Изоляция | Накладные расходы |
| D) nest_asyncio | Минимальные изменения | Хак, не production-grade |

**Рекомендация:** Вариант **B** — получить или создать event loop один раз в `prepare()`, использовать `loop.run_until_complete()` в `mutate()`.

**Статус:** ⚠️ **ТРЕБУЕТ РЕФАКТОРИНГА**

---

## 4. P1 улучшения (желательно)

### P1.1 Не трогать Qdrant, если уже настроен

**Текущее состояние:** Скрипты `setup_scalar_collection.py` / `setup_binary_collection.py` пересоздают коллекции.

**Рекомендация:** Добавить режим `--verify-only`:
1. Проверить существование коллекции
2. Проверить наличие payload indexes:
   - Keyword: `file_id`, `metadata.file_id`, `metadata.doc_id`, `metadata.source`
   - Integer: `metadata.order`, `metadata.chunk_order`
3. Если всё есть — ничего не делать
4. Если чего-то нет — предупредить, но не пересоздавать без `--force`

---

### P1.2 Наблюдаемость

**Минимум для production:**

| Метрика | Источник | Алерт |
|---------|----------|-------|
| files processed/min | Лог `Indexed: {source}` | < 0 за 30 мин |
| files failed/min | Лог `Upsert failed` | > 3 за 15 мин |
| DLQ count | Postgres `ingestion_dead_letter` | > 5 |
| docling latency p95 | Лог или metrics | > 60s |
| voyage 429 rate | Лог `429` или `rate limit` | > 1 за 5 мин |

**Текущее состояние:** Есть `docker/monitoring/rules/ingestion.yaml` с LogQL правилами — покрывает большинство.

---

## 5. Payload Contract (обязательный)

Все точки в Qdrant ДОЛЖНЫ иметь:

```python
{
    "page_content": str,       # Текст чанка (обязателен для retrieval)
    "metadata": {
        "file_id": str,        # sha256(relative_path)[:16]
        "doc_id": str,         # = file_id (для small-to-big)
        "order": int,          # Порядок чанка в документе
        "chunk_order": int,    # Alias для совместимости
        "source": str,         # Относительный путь (для citations)
        "file_name": str,
        "mime_type": str,
        "content_hash": str,
        "modified_time": str,
        "headings": list[str],
        "chunk_location": str,
        "page_range": list[int] | None,
    },
    "file_id": str,            # Flat копия для быстрого DELETE
}
```

**Критичные поля для small-to-big:**
- `metadata.doc_id` — группировка по документу
- `metadata.order` — сортировка чанков

**Текущий статус:** ✅ Реализовано в `QdrantHybridWriter.build_payload()`

---

## 6. End-to-End Acceptance Test

### Сценарий

1. Загрузить файл в Google Drive
2. `rclone sync` (≤5 мин) → файл появляется в `GDRIVE_SYNC_DIR`
3. CocoIndex детектит изменение (≤1-2 мин)
4. В Qdrant появляются точки

### Критерии приёмки

| Проверка | Команда | Ожидание |
|----------|---------|----------|
| Точки существуют | `scroll` с filter `metadata.file_id` | count > 0 |
| payload.page_content | Проверить поле | Не пустой |
| payload.metadata.doc_id | Проверить поле | = file_id |
| payload.metadata.order | Проверить поле | integer >= 0 |
| payload.metadata.source | Проверить поле | Относительный путь |
| Flat file_id | Проверить payload.file_id | = metadata.file_id |

### Delete сценарий

1. Удалить файл из Google Drive
2. `rclone sync` → файл исчезает локально
3. CocoIndex детектит удаление
4. Точки удаляются из Qdrant

### Существующие тесты

```bash
# Unit тесты payload contract
uv run pytest tests/unit/ingestion/test_payload_contract.py -v

# E2E тесты (требует Docker)
RUN_INTEGRATION_TESTS=1 uv run pytest tests/integration/test_unified_ingestion_e2e.py -v
```

---

## 7. Runbook (операционный)

### 7.1 Проверка состояния

```bash
# Статус из Postgres
make ingest-unified-status

# Логи ingestion контейнера
docker logs dev-ingestion -f --tail 100

# Проверка Qdrant collection
docker exec dev-qdrant curl -s localhost:6333/collections/gdrive_documents_scalar | jq '.result.points_count'
```

### 7.2 Ручной запуск

```bash
# Один проход
make ingest-unified

# Continuous mode
make ingest-unified-watch

# Через Docker
docker compose -f docker-compose.dev.yml up -d ingestion
```

### 7.3 Проверка точек в Qdrant

```bash
# Scroll с фильтром по file_id
docker exec dev-qdrant curl -s -X POST localhost:6333/collections/gdrive_documents_scalar/points/scroll \
  -H "Content-Type: application/json" \
  -d '{
    "filter": {"must": [{"key": "metadata.file_id", "match": {"value": "YOUR_FILE_ID"}}]},
    "limit": 5,
    "with_payload": true
  }' | jq '.result.points[0].payload'
```

### 7.4 Reprocess ошибок

```bash
# Все ошибки
make ingest-unified-reprocess

# Конкретный файл
uv run python -m src.ingestion.unified.cli reprocess --file-id abc123
```

### 7.5 DLQ

```bash
# Количество в DLQ
docker exec dev-postgres psql -U postgres -d cocoindex -c "SELECT COUNT(*) FROM ingestion_dead_letter"

# Просмотр DLQ
docker exec dev-postgres psql -U postgres -d cocoindex -c "SELECT file_id, error_type, created_at FROM ingestion_dead_letter ORDER BY created_at DESC LIMIT 10"
```

---

## 8. Резюме

### Что работает ✅

1. Структура модулей `src/ingestion/unified/`
2. Config, StateManager, QdrantHybridWriter
3. Payload contract в writer
4. CocoIndex функции через `@cocoindex.op.function()`
5. Использование `_key` для абсолютного пути
6. Нормализация app_namespace
7. CLI, Makefile, Docker service
8. E2E тесты

### Что требует внимания ⚠️

| ID | Проблема | Приоритет | Сложность |
|----|----------|-----------|-----------|
| P0.3 | Верификация init() с database settings | P0 | Низкая |
| P0.5 | asyncio.run() в mutate() | P0 | Средняя |
| P1.1 | Qdrant verify-only mode | P1 | Низкая |
| P1.2 | Расширенные метрики | P1 | Низкая |

### Следующие шаги

1. **Верифицировать P0.3:** Запустить `make ingest-unified` и проверить, что init() работает
2. **Исправить P0.5:** Рефакторинг mutate() для корректной работы с async
3. **E2E тест:** Пройти сценарий "файл в GDrive → точки в Qdrant" руками
4. **Документировать:** Обновить `docs/INGESTION.md` после стабилизации

---

## 9. Файлы для изучения

| Файл | Описание |
|------|----------|
| `src/ingestion/unified/flow.py` | CocoIndex flow definition |
| `src/ingestion/unified/targets/qdrant_hybrid_target.py` | Custom target connector |
| `src/ingestion/unified/qdrant_writer.py` | Payload contract, write logic |
| `src/ingestion/unified/state_manager.py` | Postgres state tracking |
| `tests/integration/test_unified_ingestion_e2e.py` | E2E tests |
| `telegram_bot/services/small_to_big.py` | Consumer: uses doc_id/order |

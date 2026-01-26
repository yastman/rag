***REMOVED*** Prompt для новой сессии: Phase 1 - VoyageService Refactoring

***REMOVED******REMOVED*** Копируй этот промпт в новую сессию Claude Code:

---

```
/superpowers:executing-plans docs/plans/2026-01-22-phase1-voyage-service-refactor.md
```

***REMOVED******REMOVED*** Контекст проекта

**Проект:** RAG Telegram Bot для поиска недвижимости в Болгарии
**Ветка:** `feat/redis-stack-vector-search`
**Цель:** Консолидация Voyage AI сервисов в единый `VoyageService`

***REMOVED******REMOVED*** Текущее состояние

```
telegram_bot/services/
├── voyage_client.py      ***REMOVED*** Singleton + tenacity (УДАЛИТЬ)
├── voyage_embeddings.py  ***REMOVED*** Embed service (УДАЛИТЬ)
├── voyage_reranker.py    ***REMOVED*** Rerank service (УДАЛИТЬ)
└── voyage.py             ***REMOVED*** СОЗДАТЬ (unified)
```

**Текущие модели:** voyage-3-large, rerank-2
**Целевые модели:** voyage-4-large/lite, rerank-2.5

***REMOVED******REMOVED*** План выполнения

Файл: `docs/plans/2026-01-22-phase1-voyage-service-refactor.md`

***REMOVED******REMOVED******REMOVED*** Tasks:

| ***REMOVED*** | Описание | Файлы |
|---|----------|-------|
| 1 | Написать failing тесты (TDD) | `tests/test_voyage_service.py` |
| 2 | Реализовать VoyageService | `telegram_bot/services/voyage.py` |
| 3 | Обновить __init__.py | `telegram_bot/services/__init__.py` |
| 4 | Добавить тесты совместимости | `tests/test_voyage_service.py` |
| 5 | Запустить полный test suite | - |
| 6 | (опционально) Обновить bot.py | `telegram_bot/bot.py` |

***REMOVED******REMOVED*** Ключевые фичи VoyageService

```python
class VoyageService:
    BATCH_SIZE = 128

    def __init__(self, api_key, model_docs="voyage-4-large",
                 model_queries="voyage-4-lite", model_rerank="rerank-2.5"):
        ...

    async def embed_documents(texts) -> List[List[float]]  ***REMOVED*** batching + tenacity
    async def embed_query(text) -> List[float]             ***REMOVED*** asymmetric retrieval
    async def rerank(query, documents) -> List[dict]       ***REMOVED*** 32K context
```

***REMOVED******REMOVED*** Команды

```bash
***REMOVED*** Перед началом
make docker-up
pytest tests/test_voyage*.py -v

***REMOVED*** После каждого Task
pytest tests/test_voyage_service.py -v
make check

***REMOVED*** После завершения
pytest tests/ -v --tb=short
```

***REMOVED******REMOVED*** Важно

1. **TDD:** Сначала тесты, потом код
2. **Коммиты:** После каждого Task
3. **tenacity:** 6 попыток, `wait_random_exponential(multiplier=1, max=60)` - официальная рекомендация Voyage AI
4. **asyncio.to_thread:** Для non-blocking async вызовов sync SDK
5. **Asymmetric retrieval:** `model_docs` ≠ `model_queries` (shared embedding space)

***REMOVED******REMOVED*** Дизайн-документ

Полная архитектура: `docs/plans/2026-01-22-native-services-migration.md`

---

***REMOVED******REMOVED*** Альтернативный короткий промпт:

```
Выполни план из docs/plans/2026-01-22-phase1-voyage-service-refactor.md

Используй /superpowers:executing-plans

TDD: сначала тесты, потом код.
Коммиты после каждого Task.
Tenacity: 6 попыток, wait_random_exponential(1, 60).
```

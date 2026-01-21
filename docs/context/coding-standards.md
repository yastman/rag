# Стандарты кода

---

## Python Style

- **Линтер:** Ruff
- **Длина строки:** 100 символов
- **Кавычки:** Двойные
- **Type hints:** Обязательны
- **Docstrings:** Google style

```python
from typing import Optional

async def search(
    query: str,
    top_k: int = 10,
    filters: Optional[dict] = None
) -> list[SearchResult]:
    """Search for documents.

    Args:
        query: Search query
        top_k: Number of results
        filters: Optional filters

    Returns:
        List of search results
    """
    pass
```

---

## Commits

**Формат:** Conventional Commits

```
<type>(<scope>): <description>
```

**Типы:**
- `feat` — новая функция
- `fix` — исправление бага
- `docs` — документация
- `refactor` — рефакторинг
- `test` — тесты
- `chore` — обслуживание

**Примеры:**
```bash
feat(search): add ColBERT reranking
fix(cache): resolve race condition
docs(readme): update installation guide
```

---

## Git Workflow

1. Работай в feature branch
2. Пиши тесты
3. Запусти `ruff check` и `pytest`
4. Создай PR
5. После merge — удали branch

---

## Файловые операции

1. **Read** файл перед редактированием
2. **Edit** для существующих файлов
3. **Write** только для новых файлов
4. Обновляй документацию при изменениях

---

**Последнее обновление:** 2026-01-21

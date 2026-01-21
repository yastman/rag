# Первый поиск за 5 минут

> Пошаговое руководство для быстрого старта

---

## Шаг 1: Запуск сервисов

```bash
# Клонируй репозиторий
git clone https://github.com/yastman/rag.git
cd rag

# Запусти Docker сервисы
docker compose -f docker-compose.local.yml up -d

# Проверь что всё работает
curl http://localhost:6333/health  ***REMOVED***
curl http://localhost:6379/ping    # Redis (через docker exec)
```

---

## Шаг 2: Установка зависимостей

```bash
# Создай виртуальное окружение
python3.12 -m venv venv
source venv/bin/activate

# Установи зависимости
pip install -e ".[dev]"

# Скопируй конфигурацию
cp .env.example .env
# Отредактируй .env — добавь API ключи
```

---

## Шаг 3: Первый поиск

```python
# test_search.py
import asyncio
from src.core.pipeline import RAGPipeline

async def main():
    pipeline = RAGPipeline()

    result = await pipeline.search(
        query="Що таке крадіжка?",
        top_k=5
    )

    for doc in result.results:
        print(f"Score: {doc['score']:.3f}")
        print(f"Text: {doc['text'][:200]}...")
        print("---")

asyncio.run(main())
```

```bash
python test_search.py
```

---

## Ожидаемый результат

```
Score: 0.956
Text: Стаття 185. Крадіжка. Таємне викрадення чужого майна (крадіжка)...
---
Score: 0.923
Text: Стаття 186. Грабіж. Відкрите викрадення чужого майна...
---
```

---

## Что дальше?

- [Добавление документов](adding-documents.md)
- [Настройка локально](../how-to/setup-local.md)
- [API Reference](../reference/api.md)

---

**Время:** ~5 минут

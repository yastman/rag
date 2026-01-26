***REMOVED*** Первый поиск за 5 минут

> Пошаговое руководство для быстрого старта

---

***REMOVED******REMOVED*** Шаг 1: Запуск сервисов

```bash
***REMOVED*** Клонируй репозиторий
git clone https://github.com/yastman/rag.git
cd rag

***REMOVED*** Запусти Docker сервисы
docker compose -f docker-compose.local.yml up -d

***REMOVED*** Проверь что всё работает
curl http://localhost:6333/health  ***REMOVED*** Qdrant
curl http://localhost:6379/ping    ***REMOVED*** Redis (через docker exec)
```

---

***REMOVED******REMOVED*** Шаг 2: Установка зависимостей

```bash
***REMOVED*** Создай виртуальное окружение
python3.12 -m venv venv
source venv/bin/activate

***REMOVED*** Установи зависимости
pip install -e ".[dev]"

***REMOVED*** Скопируй конфигурацию
cp .env.example .env
***REMOVED*** Отредактируй .env — добавь API ключи
```

---

***REMOVED******REMOVED*** Шаг 3: Первый поиск

```python
***REMOVED*** test_search.py
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

***REMOVED******REMOVED*** Ожидаемый результат

```
Score: 0.956
Text: Стаття 185. Крадіжка. Таємне викрадення чужого майна (крадіжка)...
---
Score: 0.923
Text: Стаття 186. Грабіж. Відкрите викрадення чужого майна...
---
```

---

***REMOVED******REMOVED*** Что дальше?

- [Добавление документов](adding-documents.md)
- [Настройка локально](../how-to/setup-local.md)
- [API Reference](../reference/api.md)

---

**Время:** ~5 минут

***REMOVED*** 🚀 QUICK START - Contextual RAG

> **Пошаговая инструкция для быстрого начала работы**

***REMOVED******REMOVED*** 5 минут до первого поиска

***REMOVED******REMOVED******REMOVED*** Шаг 1: Установка (2 минуты)

```bash
***REMOVED*** 1. Клонирование репозитория
git clone https://github.com/yastman/rag.git
cd rag

***REMOVED*** 2. Создание виртуального окружения
python3.9 -m venv venv
source venv/bin/activate  ***REMOVED*** На Windows: venv\Scripts\activate

***REMOVED*** 3. Установка зависимостей
pip install -e .

***REMOVED*** 4. Копирование конфигурации
cp .env.example .env
```

***REMOVED******REMOVED******REMOVED*** Шаг 2: Конфигурация (1 минута)

**Отредактировать `.env`:**

```env
***REMOVED*** Anthropic Claude API (основной)
ANTHROPIC_API_KEY=[REDACTED-ANTHROPIC-KEY]

***REMOVED*** Qdrant Vector Database
QDRANT_URL=http://localhost:6333
QDRANT_API_KEY=  ***REMOVED*** Если требуется

***REMOVED*** OpenAI (опционально)
OPENAI_API_KEY=[REDACTED-OPENAI-KEY]

***REMOVED*** Groq (опционально)
GROQ_API_KEY=[REDACTED-GROQ-KEY]

***REMOVED*** Z.AI (опционально)
Z_AI_API_KEY=...
```

***REMOVED******REMOVED******REMOVED*** Шаг 3: Запуск Qdrant (1 минута)

```bash
***REMOVED*** Вариант A: Docker Compose (рекомендуется)
docker compose up -d qdrant

***REMOVED*** Вариант B: Docker (если нет compose)
docker run -d --name qdrant \
  -p 6333:6333 -p 6334:6334 \
  qdrant/qdrant:latest

***REMOVED*** Проверка
curl http://localhost:6333/health
```

***REMOVED******REMOVED******REMOVED*** Шаг 4: Создание коллекции (1 минута)

```bash
***REMOVED*** Создание коллекции с индексами
python create_collection_enhanced.py
```

**Вывод:**
```
✓ Collection 'legal_documents' created
✓ Indexes created successfully
✓ Ready for ingestion
```

***REMOVED******REMOVED******REMOVED*** Шаг 5: Загрузка документов (1 минута)

```bash
***REMOVED*** Загрузка PDF документов из docs/documents/
python ingestion_contextual_kg_fast.py \
  --pdf-path docs/documents/ \
  --collection legal_documents \
  --batch-size 10

***REMOVED*** Или для одного файла
python ingestion_contextual_kg_fast.py \
  --pdf-file docs/documents/Конституція_України.pdf \
  --collection legal_documents
```

**Вывод:**
```
Loading documents...
✓ 1245 chunks processed
✓ Embeddings created (BGE-M3)
✓ Indexed in Qdrant
```

---

***REMOVED******REMOVED*** Первый поиск (2 минуты)

***REMOVED******REMOVED******REMOVED*** Вариант A: Python скрипт

**test_api_quick.py:**
```bash
python test_api_quick.py
```

**Или самостоятельно:**

```python
from qdrant_client import QdrantClient
from config import QDRANT_URL, COLLECTION_NAME

***REMOVED*** Подключение к Qdrant
client = QdrantClient(QDRANT_URL)

***REMOVED*** Поиск
query = "Які права мають громадяни України?"
results = client.search(
    collection_name=COLLECTION_NAME,
    query_vector=[0.1, 0.2, ...],  ***REMOVED*** Embedding запроса
    limit=5
)

for result in results:
    print(f"Тема: {result.payload['title']}")
    print(f"Текст: {result.payload['text'][:200]}...")
    print(f"Рейтинг: {result.score}\n")
```

***REMOVED******REMOVED******REMOVED*** Вариант B: CLI команда

```bash
python example_search.py \
  --query "Які права мають громадяни України?" \
  --top-k 5
```

**Ожидаемый результат:**
```
Результаты поиска (DBSF):
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

1. [0.9636] Розділ II. Права і свободи людини і громадянина
   Конституція України, ст. 28-68

2. [0.9402] Основні права громадян
   Цивільний кодекс, ст. 1-10

3. [0.9187] Защита прав громадян
   Кримінальний кодекс, ст. 100-150
```

---

***REMOVED******REMOVED*** Тестирование (2 минуты)

***REMOVED******REMOVED******REMOVED*** Smoke тест

```bash
***REMOVED*** Быстрая проверка всех компонентов
python evaluation/smoke_test.py

***REMOVED*** Результат
✓ Qdrant connection OK
✓ Claude API OK
✓ Embeddings OK
✓ Search OK
```

***REMOVED******REMOVED******REMOVED*** A/B тестирование

```bash
***REMOVED*** Запуск A/B теста (логирование в MLflow)
python evaluation/run_ab_test.py \
  --queries evaluation/data/test_queries.txt \
  --baseline baseline \
  --challenger dbsf

***REMOVED*** Результаты
BASELINE:  Recall@1=91.3%, NDCG@10=0.9619
DBSF:      Recall@1=94.0%, NDCG@10=0.9711
IMPROVEMENT: +2.9% Recall, +1.0% NDCG
```

---

***REMOVED******REMOVED*** Мониторинг (опционально)

***REMOVED******REMOVED******REMOVED*** MLflow Dashboard

```bash
***REMOVED*** Запуск MLflow сервера
docker compose --profile ml up -d mlflow

***REMOVED*** Открыть в браузере
open http://localhost:5000
```

**Что видить:**
- Все запущенные эксперименты
- Метрики (Recall, NDCG, Latency)
- Сравнение между runs
- Параметры конфигурации

***REMOVED******REMOVED******REMOVED*** Langfuse Dashboard

```bash
***REMOVED*** Запуск Langfuse
docker compose --profile ml up -d langfuse

***REMOVED*** Открыть в браузере
open http://localhost:3001
```

**Что видить:**
- Все LLM запросы и ответы
- Latency и token count
- Ошибки и exceptions
- Аналитика использования

---

***REMOVED******REMOVED*** Частые вопросы

***REMOVED******REMOVED******REMOVED*** Q: Как добавить новые документы?

```bash
***REMOVED*** Просто добавьте PDF в docs/documents/
cp my_document.pdf docs/documents/

***REMOVED*** И снова запустите ingestion
python ingestion_contextual_kg_fast.py \
  --pdf-path docs/documents/ \
  --collection legal_documents
```

***REMOVED******REMOVED******REMOVED*** Q: Как выбрать другой LLM (OpenAI, Groq)?

**Вариант 1: Через config.py**
```python
API_PROVIDER = 'openai'  ***REMOVED*** Или 'groq', 'zai'
MODEL_NAME = 'gpt-4-turbo-preview'
```

**Вариант 2: Через переменную окружения**
```bash
export API_PROVIDER=groq
python test_api_quick.py
```

***REMOVED******REMOVED******REMOVED*** Q: Как улучшить качество поиска?

1. **Используйте DBSF вместо базового поиска**
   ```python
   from evaluation.search_engines import DBSFSearchEngine
   engine = DBSFSearchEngine()
   ```

2. **Увеличьте контекст документов**
   ```python
   ***REMOVED*** В config.py
   CHUNK_SIZE = 1024  ***REMOVED*** Вместо 512
   ```

3. **Добавьте больше документов**
   ```bash
   python ingestion_contextual_kg_fast.py --pdf-path /more/docs
   ```

***REMOVED******REMOVED******REMOVED*** Q: Как запустить на production сервере?

```bash
***REMOVED*** 1. Используйте production конфигурацию
export ENV=production
export QDRANT_URL=https://qdrant.example.com
export QDRANT_API_KEY=your-secure-key

***REMOVED*** 2. Используйте WSGI сервер (Gunicorn)
pip install gunicorn
gunicorn -w 4 -b 0.0.0.0:8000 app:application

***REMOVED*** 3. Используйте SSL сертификат
***REMOVED*** Настройте nginx/reverse proxy
```

***REMOVED******REMOVED******REMOVED*** Q: Как очистить данные?

```bash
***REMOVED*** Удалить коллекцию Qdrant
python -c "
from qdrant_client import QdrantClient
from config import QDRANT_URL, COLLECTION_NAME

client = QdrantClient(QDRANT_URL)
client.delete_collection(COLLECTION_NAME)
"

***REMOVED*** Или просто перезагрузить Qdrant
docker compose down qdrant
docker compose up -d qdrant
```

---

***REMOVED******REMOVED*** Типовые ошибки и решения

| Ошибка | Причина | Решение |
|--------|---------|---------|
| `ConnectionError: localhost:6333` | Qdrant не запущен | `docker compose up -d qdrant` |
| `APIError: invalid_request_error` | Неверный API ключ | Проверьте `.env` ANTHROPIC_API_KEY |
| `ModuleNotFoundError: qdrant_client` | Зависимости не установлены | `pip install -e .` |
| `TimeoutError` при загрузке | PDF слишком большой | Используйте `--batch-size 5` |
| Низкие метрики поиска | Документы не индексированы | Запустите ingestion заново |

---

***REMOVED******REMOVED*** Следующие шаги

1. **Прочитайте PROJECT_STRUCTURE.md** - Полное описание всех модулей
2. **Изучите ARCHITECTURE.md** - Архитектура системы
3. **Запустите evaluation/run_ab_test.py** - A/B тестирование
4. **Попробуйте разные LLM** - OpenAI, Groq, Z.AI
5. **Мониторьте метрики** - MLflow и Langfuse dashboards

---

***REMOVED******REMOVED*** Чеклист готовности к production

- [ ] Все API ключи настроены в `.env`
- [ ] Qdrant запущен и доступен
- [ ] Документы загружены и проиндексированы
- [ ] Smoke тест пройден (`evaluation/smoke_test.py`)
- [ ] A/B тест показывает ожидаемые метрики
- [ ] MLflow/Langfuse настроены для мониторинга
- [ ] SSL сертификат установлен (для production)
- [ ] Резервные копии данных настроены
- [ ] Документация обновлена для вашего команды

---

***REMOVED******REMOVED*** Полезные команды

```bash
***REMOVED*** Информация о проекте
python list_available_models.py          ***REMOVED*** Список доступных моделей
python check_sparse_vectors.py           ***REMOVED*** Проверка sparse vectors

***REMOVED*** Тестирование
python test_api_quick.py                 ***REMOVED*** Smoke test
python test_api_safe.py                  ***REMOVED*** Безопасный тест
python evaluation/smoke_test.py          ***REMOVED*** Полный smoke test

***REMOVED*** Оценка
python evaluation/run_ab_test.py         ***REMOVED*** A/B тест с логированием
python evaluation/evaluate_with_ragas.py ***REMOVED*** RAGAS оценка

***REMOVED*** Разработка
ruff check .                             ***REMOVED*** Lint проверка
ruff format .                            ***REMOVED*** Форматирование
mypy . --ignore-missing-imports          ***REMOVED*** Type checking
python -m pytest tests/                  ***REMOVED*** Unit тесты (если есть)
```

---

**Last Updated**: 2024-10-29
**Version**: 2.0.1
**Repository**: https://github.com/yastman/rag

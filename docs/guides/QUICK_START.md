# 🚀 QUICK START - Contextual RAG

> **Пошаговая инструкция для быстрого начала работы**

## 5 минут до первого поиска

### Шаг 1: Установка (2 минуты)

```bash
# 1. Клонирование репозитория
git clone <your-repo-url>
cd contextual_rag

# 2. Создание виртуального окружения
python3.9 -m venv venv
source venv/bin/activate  # На Windows: venv\Scripts\activate

# 3. Установка зависимостей
pip install -e .

# 4. Копирование конфигурации
cp .env.example .env
```

### Шаг 2: Конфигурация (1 минута)

**Отредактировать `.env`:**

```env
# Anthropic Claude API (основной)
ANTHROPIC_API_KEY=sk-ant-...

# Qdrant Vector Database
QDRANT_URL=http://localhost:6333
QDRANT_API_KEY=  # Если требуется

# OpenAI (опционально)
OPENAI_API_KEY=sk-...

# Groq (опционально)
GROQ_API_KEY=gsk_...

# Z.AI (опционально)
Z_AI_API_KEY=...
```

### Шаг 3: Запуск Qdrant (1 минута)

```bash
# Вариант A: Docker Compose (рекомендуется)
docker compose up -d qdrant

# Вариант B: Docker (если нет compose)
docker run -d --name qdrant \
  -p 6333:6333 -p 6334:6334 \
  qdrant/qdrant:latest

# Проверка
curl http://localhost:6333/health
```

### Шаг 4: Создание коллекции (1 минута)

```bash
# Создание коллекции с индексами
python create_collection_enhanced.py
```

**Вывод:**
```
✓ Collection 'legal_documents' created
✓ Indexes created successfully
✓ Ready for ingestion
```

### Шаг 5: Загрузка документов (1 минута)

```bash
# Загрузка PDF документов из docs/documents/
python ingestion_contextual_kg_fast.py \
  --pdf-path docs/documents/ \
  --collection legal_documents \
  --batch-size 10

# Или для одного файла
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

## Первый поиск (2 минуты)

### Вариант A: Python скрипт

**test_api_quick.py:**
```bash
python test_api_quick.py
```

**Или самостоятельно:**

```python
from qdrant_client import QdrantClient
from config import QDRANT_URL, COLLECTION_NAME

# Подключение к Qdrant
client = QdrantClient(QDRANT_URL)

# Поиск
query = "Які права мають громадяни України?"
results = client.search(
    collection_name=COLLECTION_NAME,
    query_vector=[0.1, 0.2, ...],  # Embedding запроса
    limit=5
)

for result in results:
    print(f"Тема: {result.payload['title']}")
    print(f"Текст: {result.payload['text'][:200]}...")
    print(f"Рейтинг: {result.score}\n")
```

### Вариант B: CLI команда

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

## Тестирование (2 минуты)

### Smoke тест

```bash
# Быстрая проверка всех компонентов
python evaluation/smoke_test.py

# Результат
✓ Qdrant connection OK
✓ Claude API OK
✓ Embeddings OK
✓ Search OK
```

### A/B тестирование

```bash
# Запуск A/B теста (логирование в MLflow)
python evaluation/run_ab_test.py \
  --queries evaluation/data/test_queries.txt \
  --baseline baseline \
  --challenger dbsf

# Результаты
BASELINE:  Recall@1=91.3%, NDCG@10=0.9619
DBSF:      Recall@1=94.0%, NDCG@10=0.9711
IMPROVEMENT: +2.9% Recall, +1.0% NDCG
```

---

## Мониторинг (опционально)

### MLflow Dashboard

```bash
# Запуск MLflow сервера
docker compose --profile ml up -d mlflow

# Открыть в браузере
open http://localhost:5000
```

**Что видить:**
- Все запущенные эксперименты
- Метрики (Recall, NDCG, Latency)
- Сравнение между runs
- Параметры конфигурации

### Langfuse Dashboard

```bash
# Запуск Langfuse
docker compose --profile ml up -d langfuse

# Открыть в браузере
open http://localhost:3001
```

**Что видить:**
- Все LLM запросы и ответы
- Latency и token count
- Ошибки и exceptions
- Аналитика использования

---

## Частые вопросы

### Q: Как добавить новые документы?

```bash
# Просто добавьте PDF в docs/documents/
cp my_document.pdf docs/documents/

# И снова запустите ingestion
python ingestion_contextual_kg_fast.py \
  --pdf-path docs/documents/ \
  --collection legal_documents
```

### Q: Как выбрать другой LLM (OpenAI, Groq)?

**Вариант 1: Через config.py**
```python
API_PROVIDER = 'openai'  # Или 'groq', 'zai'
MODEL_NAME = 'gpt-4-turbo-preview'
```

**Вариант 2: Через переменную окружения**
```bash
export API_PROVIDER=groq
python test_api_quick.py
```

### Q: Как улучшить качество поиска?

1. **Используйте DBSF вместо базового поиска**
   ```python
   from evaluation.search_engines import DBSFSearchEngine
   engine = DBSFSearchEngine()
   ```

2. **Увеличьте контекст документов**
   ```python
   # В config.py
   CHUNK_SIZE = 1024  # Вместо 512
   ```

3. **Добавьте больше документов**
   ```bash
   python ingestion_contextual_kg_fast.py --pdf-path /more/docs
   ```

### Q: Как запустить на production сервере?

```bash
# 1. Используйте production конфигурацию
export ENV=production
export QDRANT_URL=https://qdrant.example.com
export QDRANT_API_KEY=your-secure-key

# 2. Используйте WSGI сервер (Gunicorn)
pip install gunicorn
gunicorn -w 4 -b 0.0.0.0:8000 app:application

# 3. Используйте SSL сертификат
# Настройте nginx/reverse proxy
```

### Q: Как очистить данные?

```bash
# Удалить коллекцию Qdrant
python -c "
from qdrant_client import QdrantClient
from config import QDRANT_URL, COLLECTION_NAME

client = QdrantClient(QDRANT_URL)
client.delete_collection(COLLECTION_NAME)
"

# Или просто перезагрузить Qdrant
docker compose down qdrant
docker compose up -d qdrant
```

---

## Типовые ошибки и решения

| Ошибка | Причина | Решение |
|--------|---------|---------|
| `ConnectionError: localhost:6333` | Qdrant не запущен | `docker compose up -d qdrant` |
| `APIError: invalid_request_error` | Неверный API ключ | Проверьте `.env` ANTHROPIC_API_KEY |
| `ModuleNotFoundError: qdrant_client` | Зависимости не установлены | `pip install -e .` |
| `TimeoutError` при загрузке | PDF слишком большой | Используйте `--batch-size 5` |
| Низкие метрики поиска | Документы не индексированы | Запустите ingestion заново |

---

## Следующие шаги

1. **Прочитайте PROJECT_STRUCTURE.md** - Полное описание всех модулей
2. **Изучите ARCHITECTURE.md** - Архитектура системы
3. **Запустите evaluation/run_ab_test.py** - A/B тестирование
4. **Попробуйте разные LLM** - OpenAI, Groq, Z.AI
5. **Мониторьте метрики** - MLflow и Langfuse dashboards

---

## Чеклист готовности к production

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

## Полезные команды

```bash
# Информация о проекте
python list_available_models.py          # Список доступных моделей
python check_sparse_vectors.py           # Проверка sparse vectors

# Тестирование
python test_api_quick.py                 # Smoke test
python test_api_safe.py                  # Безопасный тест
python evaluation/smoke_test.py          # Полный smoke test

# Оценка
python evaluation/run_ab_test.py         # A/B тест с логированием
python evaluation/evaluate_with_ragas.py # RAGAS оценка

# Разработка
ruff check .                             # Lint проверка
ruff format .                            # Форматирование
mypy . --ignore-missing-imports          # Type checking
python -m pytest tests/                  # Unit тесты (если есть)
```

---

**Last Updated**: 2025-10-29
**Version**: 2.0.1

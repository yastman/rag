***REMOVED*** Telegram RAG Bot для недвижимости в Болгарии

Бот на основе RAG (Retrieval-Augmented Generation) для поиска квартир в Болгарии через Telegram.

***REMOVED******REMOVED*** 🏗️ Архитектура

```
User Query → Filter Extraction → BGE-M3 Embedding → Qdrant Search → LLM Answer → Telegram
```

***REMOVED******REMOVED*** 🚀 Быстрый старт

***REMOVED******REMOVED******REMOVED*** 1. Установка зависимостей

```bash
cd telegram_bot
pip install -r requirements.txt
```

***REMOVED******REMOVED******REMOVED*** 2. Настройка .env

Скопируй `.env.example` в `.env` и заполни:

```bash
cp .env.example .env
nano .env
```

**Обязательно:**
- `TELEGRAM_BOT_TOKEN` - токен от @BotFather
- `OPENAI_API_KEY` - API ключ OpenAI (или другого LLM)

**Опционально (если не localhost):**
- `BGE_M3_URL` - URL BGE-M3 API
- `QDRANT_URL` - URL Qdrant
- `QDRANT_COLLECTION` - название коллекции

***REMOVED******REMOVED******REMOVED*** 3. Создание бота в Telegram

1. Открой @BotFather в Telegram
2. Отправь `/newbot`
3. Укажи имя и username бота
4. Скопируй токен в `.env`

***REMOVED******REMOVED******REMOVED*** 4. Запуск бота

```bash
python -m telegram_bot.main
```

Или из корня проекта:

```bash
cd /srv/rag-fresh
python -m telegram_bot.main
```

***REMOVED******REMOVED*** 📝 Примеры запросов

**По цене:**
- Дешевле 100 000 евро
- От 80к до 150к
- Не дороже 100000

**По комнатам:**
- 3-комнатные квартиры
- Студия
- Двухкомнатная

**По городу:**
- В Солнечный берег
- Несебр

**Комбинированные:**
- Трехкомнатная в Солнечный берег до 120к
- Студия дешевле 60000 евро

***REMOVED******REMOVED*** 🛠️ Компоненты

***REMOVED******REMOVED******REMOVED*** Services

- **EmbeddingService** - генерация embeddings через BGE-M3 API
- **RetrieverService** - поиск в Qdrant с фильтрами
- **generate_response()** - каноничный runtime-путь генерации ответов
- **CacheService** - 4-уровневое кеширование (semantic, embeddings, analyzer, search)
- **QueryAnalyzer** - анализ запросов и извлечение фильтров через LLM
- **UserContextService** - управление контекстом пользователя (CESC)
- **CESCPersonalizer** - персонализация кешированных ответов (CESC)

***REMOVED******REMOVED******REMOVED*** Фильтры

Автоматически извлекаются:
- Цена (lt, gt, range)
- Количество комнат
- Город
- Площадь

***REMOVED******REMOVED*** 📊 Логи

Логи выводятся в stdout с уровнем INFO:

```
14:23:45 - telegram_bot.bot - INFO - Query from 123456789: покажи студии
14:23:45 - telegram_bot.bot - INFO - Extracted filters: {'rooms': 1}
14:23:46 - telegram_bot.bot - INFO - Generated embedding: 1024-dim
14:23:46 - telegram_bot.bot - INFO - Found 2 results
```

***REMOVED******REMOVED*** 🔧 Конфигурация

Все параметры в `config.py`:

```python
top_k: int = 5  ***REMOVED*** Количество результатов из Qdrant
min_score: float = 0.5  ***REMOVED*** Минимальный score релевантности
```

***REMOVED******REMOVED*** 🐛 Отладка

1. Проверь, что сервисы запущены:
```bash
curl http://localhost:8001/health  ***REMOVED*** BGE-M3
curl http://localhost:6333  ***REMOVED*** Qdrant
```

2. Проверь коллекцию Qdrant:
```bash
python test_filtering.py
```

3. Логи бота:
```bash
python -m telegram_bot.main 2>&1 | tee bot.log
```

***REMOVED******REMOVED*** 📦 Структура проекта

```
telegram_bot/
├── __init__.py
├── main.py              ***REMOVED*** Точка входа
├── bot.py               ***REMOVED*** Основная логика бота
├── config.py            ***REMOVED*** Конфигурация
├── middlewares.py       ***REMOVED*** Throttling, error handling
├── services/
│   ├── __init__.py      ***REMOVED*** Exports
│   ├── embeddings.py    ***REMOVED*** BGE-M3 API
│   ├── retriever.py     ***REMOVED*** Qdrant поиск
│   ├── llm.py           ***REMOVED*** LLM генерация (streaming)
│   ├── cache.py         ***REMOVED*** 4-tier caching
│   ├── query_analyzer.py    ***REMOVED*** Query analysis via LLM
│   ├── user_context.py  ***REMOVED*** CESC: User preferences (NEW)
│   └── cesc.py          ***REMOVED*** CESC: Personalization (NEW)
├── requirements.txt
└── README.md
```

***REMOVED******REMOVED*** 🔐 Безопасность

- Никогда не коммить `.env` файл
- Используй `.env.example` как шаблон
- API ключи хранятся только локально
- Бот работает через Telegram API (зашифровано)

***REMOVED******REMOVED*** 🚀 Production

Для production используй:

1. **Systemd service:**
```bash
sudo systemctl enable telegram-bot
sudo systemctl start telegram-bot
```

2. **Docker:**
```bash
docker build -t telegram-bot .
docker run -d --env-file .env telegram-bot
```

3. **Webhook mode** (вместо polling):
Измени `bot.py` для использования webhook вместо long polling.

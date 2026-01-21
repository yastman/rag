***REMOVED*** Настройка локального окружения

---

***REMOVED******REMOVED*** Требования

- Python 3.12+
- Docker + Docker Compose
- Git
- 8GB RAM (минимум)

---

***REMOVED******REMOVED*** Установка

***REMOVED******REMOVED******REMOVED*** 1. Клонирование

```bash
git clone https://github.com/yastman/rag.git
cd rag
```

***REMOVED******REMOVED******REMOVED*** 2. Python окружение

```bash
python3.12 -m venv venv
source venv/bin/activate  ***REMOVED*** Linux/Mac
***REMOVED*** или: venv\Scripts\activate  ***REMOVED*** Windows

pip install -e ".[dev]"
```

***REMOVED******REMOVED******REMOVED*** 3. Конфигурация

```bash
cp .env.example .env
```

Отредактируй `.env`:

```env
***REMOVED*** Обязательно
QDRANT_URL=http://localhost:6333
QDRANT_API_KEY=your_key

***REMOVED*** Один из LLM провайдеров
ANTHROPIC_API_KEY=[REDACTED-ANTHROPIC-KEY]
***REMOVED*** или
OPENAI_API_KEY=[REDACTED-OPENAI-KEY]
***REMOVED*** или
GROQ_API_KEY=[REDACTED-GROQ-KEY]
```

***REMOVED******REMOVED******REMOVED*** 4. Docker сервисы

```bash
docker compose -f docker-compose.local.yml up -d
```

***REMOVED******REMOVED******REMOVED*** 5. Проверка

```bash
***REMOVED*** Qdrant
curl http://localhost:6333/health

***REMOVED*** Redis
docker exec ai-redis-secure redis-cli PING

***REMOVED*** BGE-M3
curl http://localhost:8000/health
```

---

***REMOVED******REMOVED*** Ежедневный workflow

```bash
***REMOVED*** Запуск сервисов
docker compose -f docker-compose.local.yml up -d

***REMOVED*** Активация venv
source venv/bin/activate

***REMOVED*** Разработка...

***REMOVED*** Линтинг
make lint

***REMOVED*** Тесты
make test
```

---

***REMOVED******REMOVED*** Проблемы?

См. [troubleshooting.md](troubleshooting.md)

---

**Время:** ~15 минут

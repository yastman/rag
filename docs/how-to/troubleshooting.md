***REMOVED*** Решение проблем

---

***REMOVED******REMOVED*** Qdrant

***REMOVED******REMOVED******REMOVED*** "Connection refused localhost:6333"

```bash
***REMOVED*** Проверь что контейнер запущен
docker ps | grep qdrant

***REMOVED*** Если нет — запусти
docker compose -f docker-compose.local.yml up -d qdrant
```

***REMOVED******REMOVED******REMOVED*** "Unauthorized" ошибка

```bash
***REMOVED*** Проверь API key в .env
cat .env | grep QDRANT_API_KEY

***REMOVED*** Должен совпадать с docker-compose
```

---

***REMOVED******REMOVED*** Redis

***REMOVED******REMOVED******REMOVED*** "Connection refused localhost:6379"

```bash
docker compose -f docker-compose.local.yml up -d redis
```

***REMOVED******REMOVED******REMOVED*** "NOAUTH Authentication required"

```bash
***REMOVED*** Проверь пароль в .env
REDIS_PASSWORD=your_password
```

---

***REMOVED******REMOVED*** BGE-M3

***REMOVED******REMOVED******REMOVED*** "Model not loaded"

```bash
***REMOVED*** Первый запуск скачивает модель (~7GB)
***REMOVED*** Подожди 5-10 минут

***REMOVED*** Проверь логи
docker logs ai-bge-m3-api
```

***REMOVED******REMOVED******REMOVED*** Out of Memory

```bash
***REMOVED*** BGE-M3 требует ~4GB RAM
***REMOVED*** Проверь доступную память
free -h
```

---

***REMOVED******REMOVED*** Python

***REMOVED******REMOVED******REMOVED*** "ModuleNotFoundError"

```bash
***REMOVED*** Переустанови зависимости
pip install -e ".[dev]"
```

***REMOVED******REMOVED******REMOVED*** "ImportError: cannot import name"

```bash
***REMOVED*** Возможно конфликт версий
pip install --upgrade -e ".[dev]"
```

---

***REMOVED******REMOVED*** Telegram Bot

***REMOVED******REMOVED******REMOVED*** Bot не отвечает

```bash
***REMOVED*** Проверь токен в .env
TELEGRAM_BOT_TOKEN=[REDACTED-TELEGRAM-TOKEN]

***REMOVED*** Проверь логи
python telegram_bot/main.py
```

---

***REMOVED******REMOVED*** Общие советы

1. **Проверь Docker**: `docker ps`
2. **Проверь логи**: `docker logs <container>`
3. **Проверь .env**: все ключи заполнены?
4. **Перезапусти**: `docker compose restart`

---

**Последнее обновление:** 2026-01-21

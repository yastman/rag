# Решение проблем

---

## Qdrant

### "Connection refused localhost:6333"

```bash
# Проверь что контейнер запущен
docker ps | grep qdrant

# Если нет — запусти
docker compose -f docker-compose.local.yml up -d qdrant
```

### "Unauthorized" ошибка

```bash
# Проверь API key в .env
cat .env | grep QDRANT_API_KEY

# Должен совпадать с docker-compose
```

---

## Redis

### "Connection refused localhost:6379"

```bash
docker compose -f docker-compose.local.yml up -d redis
```

### "NOAUTH Authentication required"

```bash
# Проверь пароль в .env
REDIS_PASSWORD=your_password
```

---

## BGE-M3

### "Model not loaded"

```bash
# Первый запуск скачивает модель (~7GB)
# Подожди 5-10 минут

# Проверь логи
docker logs ai-bge-m3-api
```

### Out of Memory

```bash
# BGE-M3 требует ~4GB RAM
# Проверь доступную память
free -h
```

---

## Python

### "ModuleNotFoundError"

```bash
# Переустанови зависимости
pip install -e ".[dev]"
```

### "ImportError: cannot import name"

```bash
# Возможно конфликт версий
pip install --upgrade -e ".[dev]"
```

---

## Telegram Bot

### Bot не отвечает

```bash
# Проверь токен в .env
TELEGRAM_BOT_TOKEN=...

# Проверь логи
python telegram_bot/main.py
```

---

## Общие советы

1. **Проверь Docker**: `docker ps`
2. **Проверь логи**: `docker logs <container>`
3. **Проверь .env**: все ключи заполнены?
4. **Перезапусти**: `docker compose restart`

---

**Последнее обновление:** 2026-01-21

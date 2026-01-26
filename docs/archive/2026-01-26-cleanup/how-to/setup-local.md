# Настройка локального окружения

---

## Требования

- Python 3.12+
- Docker + Docker Compose
- Git
- 8GB RAM (минимум)

---

## Установка

### 1. Клонирование

```bash
git clone https://github.com/yastman/rag.git
cd rag
```

### 2. Python окружение

```bash
python3.12 -m venv venv
source venv/bin/activate  # Linux/Mac
# или: venv\Scripts\activate  # Windows

pip install -e ".[dev]"
```

### 3. Конфигурация

```bash
cp .env.example .env
```

Отредактируй `.env`:

```env
# Обязательно
QDRANT_URL=http://localhost:6333
QDRANT_API_KEY=your_key

# Один из LLM провайдеров
ANTHROPIC_API_KEY=sk-ant-...
# или
OPENAI_API_KEY=sk-...
# или
GROQ_API_KEY=gsk_...
```

### 4. Docker сервисы

```bash
docker compose -f docker-compose.local.yml up -d
```

### 5. Проверка

```bash
***REMOVED***
curl http://localhost:6333/health

# Redis
docker exec ai-redis-secure redis-cli PING

# BGE-M3
curl http://localhost:8000/health
```

---

## Ежедневный workflow

```bash
# Запуск сервисов
docker compose -f docker-compose.local.yml up -d

# Активация venv
source venv/bin/activate

# Разработка...

# Линтинг
make lint

# Тесты
make test
```

---

## Проблемы?

См. [troubleshooting.md](troubleshooting.md)

---

**Время:** ~15 минут

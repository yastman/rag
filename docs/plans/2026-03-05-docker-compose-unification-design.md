# Docker Compose Unification: Dev/VPS Bridge

**Дата:** 2026-03-05
**Статус:** Draft
**Цель:** Единый source of truth для всех Docker-сервисов, тонкие override'ы для dev/vps

## Проблема

Два отдельных compose-файла (~814 + ~521 строк) с дублированием определений сервисов.
Добавление/изменение сервиса требует правки в двух местах — конфиги неизбежно дрейфуют.

## Решение: Compose Merge (нативный механизм Docker)

### Структура файлов

```
compose.yml          # Base — все сервисы, общая конфигурация (~650 строк)
compose.dev.yml      # Dev override — порты, colbert, мягкие defaults (~50 строк)
compose.vps.yml      # VPS override — memory limits, RERANK=none (~30 строк)
```

### Переключение окружения через .env

```bash
# Локалка (.env)
COMPOSE_PROJECT_NAME=dev
COMPOSE_FILE=compose.yml:compose.dev.yml

# VPS (.env)
COMPOSE_PROJECT_NAME=vps
COMPOSE_FILE=compose.yml:compose.vps.yml
```

Запуск везде одинаковый: `docker compose up -d` — без `-f` флагов.
`COMPOSE_PROJECT_NAME` автоматически даёт prefix контейнерам (`dev-postgres`, `vps-postgres`).

## Дизайн Base (compose.yml)

### Принципы

1. **Строгие env** — `${VAR:?required}` для обязательных переменных
2. **Без портов** — по умолчанию ничего не проброшено наружу (безопаснее)
3. **Все сервисы** — включая dev-only (loki, mlflow, voice) за profiles
4. **Дефолтные лимиты** — production-safe значения (меньше = безопаснее)
5. **Без container_name** — `COMPOSE_PROJECT_NAME` делает это автоматически

### Profiles (сохраняются как есть)

| Profile | Сервисы |
|---------|---------|
| (none)  | postgres, redis, qdrant, docling, bge-m3, user-base |
| bot     | litellm, bot |
| ml      | clickhouse, minio, redis-langfuse, langfuse-worker, langfuse, mlflow |
| obs     | loki, promtail, alertmanager |
| ingest  | ingestion |
| voice   | rag-api, livekit-server, livekit-sip, voice-agent |
| full    | все сервисы |

### Что убирается из base

- `container_name:` — удаляется полностью (COMPOSE_PROJECT_NAME)
- `ports:` — удаляются (переносятся в compose.dev.yml)
- Все env defaults типа `${VAR:-dev_value}` — заменяются на `${VAR:?required}` или `${VAR:-prod_safe_value}`

## Дизайн Dev Override (compose.dev.yml)

```yaml
# compose.dev.yml — Development overrides
services:
  postgres:
    ports:
      - "127.0.0.1:5432:5432"
    environment:
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD:-postgres}

  redis:
    ports:
      - "127.0.0.1:6379:6379"
    environment:
      REDIS_PASSWORD: ${REDIS_PASSWORD:-dev_redis_pass}
    command: >
      redis-server
      --requirepass ${REDIS_PASSWORD:-dev_redis_pass}
      --maxmemory 512mb
      --maxmemory-policy volatile-lfu
      --maxmemory-samples 10

  qdrant:
    ports:
      - "127.0.0.1:6333:6333"
      - "127.0.0.1:6334:6334"

  docling:
    ports:
      - "127.0.0.1:5001:5001"

  bge-m3:
    ports:
      - "127.0.0.1:8000:8000"

  user-base:
    ports:
      - "127.0.0.1:8003:8000"

  litellm:
    ports:
      - "127.0.0.1:4000:4000"

  bot:
    environment:
      RERANK_PROVIDER: colbert
      RERANK_CANDIDATES_MAX: "${RERANK_CANDIDATES_MAX:-10}"
      COLBERT_TIMEOUT: "${COLBERT_TIMEOUT:-120}"

  langfuse:
    ports:
      - "127.0.0.1:3001:3000"

  clickhouse:
    ports:
      - "127.0.0.1:8123:8123"

  minio:
    ports:
      - "127.0.0.1:9090:9090"
      - "127.0.0.1:9091:9091"

  rag-api:
    ports:
      - "127.0.0.1:8080:8080"

  mlflow:
    ports:
      - "127.0.0.1:5000:5000"

  loki:
    ports:
      - "127.0.0.1:3100:3100"
```

## Дизайн VPS Override (compose.vps.yml)

```yaml
# compose.vps.yml — VPS production overrides
services:
  redis:
    command: >
      redis-server
      --requirepass ${REDIS_PASSWORD:?REDIS_PASSWORD is required}
      --maxmemory 256mb
      --maxmemory-policy volatile-lfu
      --maxmemory-samples 10

  postgres:
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U postgres"]
      interval: 10s
      timeout: 5s
      retries: 5
      start_period: 30s

  bot:
    environment:
      RERANK_PROVIDER: "none"
      RERANK_CANDIDATES_MAX: "5"

  langfuse:
    ports:
      - "127.0.0.1:3001:3000"
```

## Что меняется в инфраструктуре

### Makefile

```makefile
# Было:
COMPOSE_CMD := docker compose --compatibility -f docker-compose.dev.yml

# Стало (COMPOSE_FILE из .env делает всё сам):
COMPOSE_CMD := docker compose --compatibility
```

### CI/CD (.github/workflows/ci.yml)

```yaml
# Было:
docker compose -f docker-compose.vps.yml build bot

# Стало (на VPS уже есть .env с COMPOSE_FILE):
docker compose build bot
```

### scripts/deploy-vps.sh

```bash
# Было:
COMPOSE_FILE="docker-compose.vps.yml"

# Стало:
# Ничего — VPS .env уже содержит COMPOSE_FILE=compose.yml:compose.vps.yml
```

### .env.example

Добавить:
```bash
# Environment selection (pick ONE):
# Local dev:  COMPOSE_FILE=compose.yml:compose.dev.yml
# VPS prod:   COMPOSE_FILE=compose.yml:compose.vps.yml
COMPOSE_FILE=compose.yml:compose.dev.yml
COMPOSE_PROJECT_NAME=dev
```

## Миграция (что удаляется)

| Файл | Действие |
|------|----------|
| `docker-compose.dev.yml` (814 строк) | Удаляется |
| `docker-compose.vps.yml` (521 строк) | Удаляется |
| `compose.yml` | Создаётся (база из dev, без портов/container_name) |
| `compose.dev.yml` | Создаётся (~50 строк) |
| `compose.vps.yml` | Создаётся (~30 строк) |

## Валидация

```bash
# Проверить merged config для dev:
COMPOSE_FILE=compose.yml:compose.dev.yml docker compose config > /dev/null

# Проверить merged config для vps:
COMPOSE_FILE=compose.yml:compose.vps.yml docker compose config > /dev/null

# Сравнить с текущим dev:
diff <(docker compose -f docker-compose.dev.yml config) \
     <(COMPOSE_FILE=compose.yml:compose.dev.yml docker compose config)

# Сравнить с текущим vps:
diff <(docker compose -f docker-compose.vps.yml config) \
     <(COMPOSE_FILE=compose.yml:compose.vps.yml docker compose config)
```

## Риски и митигация

| Риск | Митигация |
|------|-----------|
| Сломать текущий деплой VPS | diff валидация перед удалением старых файлов |
| Забыть проставить COMPOSE_FILE на VPS | deploy-vps.sh проверяет .env перед деплоем |
| Merge порядок — override не применился | `docker compose config` показывает итоговый merged результат |

## Не в скоупе

- Registry (GHCR) — не нужен для соло-разработчика
- k3s миграция — отдельный проект
- Новые сервисы — только унификация существующих

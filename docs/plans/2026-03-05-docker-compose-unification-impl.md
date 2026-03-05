# Docker Compose Unification Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Заменить два дублирующихся compose-файла (1333 строки) на один base + два тонких override (~720 строк).

**Architecture:** Нативный Docker Compose merge — `compose.yml` (base, все сервисы) + `compose.dev.yml` (порты, colbert) + `compose.vps.yml` (memory limits, RERANK=none). Переключение через `COMPOSE_FILE` в `.env`.

**Tech Stack:** Docker Compose v2.20+, Makefile, bash, GitHub Actions

**Design doc:** `docs/plans/2026-03-05-docker-compose-unification-design.md`

---

### Task 1: Создать compose.yml (base)

**Files:**
- Create: `compose.yml`
- Reference: `docker-compose.dev.yml` (как исходник для всех сервисов)
- Reference: `docker-compose.vps.yml` (для VPS-специфичных лимитов)

**Step 1: Скопировать dev compose как основу**

```bash
cp docker-compose.dev.yml compose.yml
```

**Step 2: Убрать из compose.yml все различия dev/vps**

Применить следующие изменения к `compose.yml`:

1. Удалить ВСЕ `container_name:` строки — `COMPOSE_PROJECT_NAME` сделает prefix автоматически
2. Удалить ВСЕ `ports:` секции — порты будут только в override'ах
3. Заменить мягкие env defaults на строгие (где нужно):
   - `${POSTGRES_PASSWORD:-postgres}` → `${POSTGRES_PASSWORD:?POSTGRES_PASSWORD is required}`
   - `${REDIS_PASSWORD:-dev_redis_pass}` → `${REDIS_PASSWORD:?REDIS_PASSWORD is required}`
   - `${LITELLM_MASTER_KEY:-sk-litellm}` → `${LITELLM_MASTER_KEY:?LITELLM_MASTER_KEY is required}`
   - `${TELEGRAM_BOT_TOKEN:?...}` — уже строгий, оставить
4. Для bot сервиса:
   - Удалить `RERANK_PROVIDER: colbert` — будет в override
   - Удалить `COLBERT_TIMEOUT` — будет в dev override
   - Оставить `RERANK_CANDIDATES_MAX: "${RERANK_CANDIDATES_MAX:-10}"` — dev default
5. Redis command — использовать VPS-safe defaults:
   ```yaml
   command: >
     redis-server
     --requirepass ${REDIS_PASSWORD:?REDIS_PASSWORD is required}
     --maxmemory ${REDIS_MAXMEMORY:-256mb}
     --maxmemory-policy volatile-lfu
     --maxmemory-samples 10
   ```
6. Healthcheck postgres — `start_period: 30s` (VPS-safe)
7. Комментарий в начале файла:
   ```yaml
   # Base configuration — all services, no ports exposed.
   # Use with override: COMPOSE_FILE=compose.yml:compose.dev.yml
   # See docs/plans/2026-03-05-docker-compose-unification-design.md
   ```

**Step 3: Валидация базового файла**

```bash
COMPOSE_FILE=compose.yml docker compose config > /dev/null
```

Expected: успех (0 exit code). Если ошибки в env — временно задать через export.

**Step 4: Commit**

```bash
git add compose.yml
git commit -m "feat(docker): create unified compose.yml base from dev"
```

---

### Task 2: Создать compose.dev.yml (dev override)

**Files:**
- Create: `compose.dev.yml`

**Step 1: Создать файл с dev-specific override'ами**

```yaml
# compose.dev.yml — Development overrides: ports, colbert reranking, relaxed defaults.
# Usage: COMPOSE_FILE=compose.yml:compose.dev.yml docker compose up -d

services:
  postgres:
    ports:
      - "127.0.0.1:5432:5432"
    environment:
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD:-postgres}
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U postgres"]
      interval: 10s
      timeout: 5s
      retries: 5
      start_period: 10s

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

  bge-m3:
    ports:
      - "127.0.0.1:8000:8000"

  user-base:
    ports:
      - "127.0.0.1:8003:8000"

  docling:
    ports:
      - "127.0.0.1:5001:5001"

  litellm:
    ports:
      - "127.0.0.1:4000:4000"

  bot:
    environment:
      RERANK_PROVIDER: colbert
      RERANK_CANDIDATES_MAX: "${RERANK_CANDIDATES_MAX:-10}"
      COLBERT_TIMEOUT: "${COLBERT_TIMEOUT:-120}"

  clickhouse:
    ports:
      - "127.0.0.1:8123:8123"

  minio:
    ports:
      - "127.0.0.1:9090:9090"
      - "127.0.0.1:9091:9091"

  langfuse:
    ports:
      - "127.0.0.1:3001:3000"

  mlflow:
    ports:
      - "127.0.0.1:5000:5000"

  loki:
    ports:
      - "127.0.0.1:3100:3100"

  rag-api:
    ports:
      - "127.0.0.1:8080:8080"
```

**Step 2: Валидация merged dev config**

```bash
COMPOSE_FILE=compose.yml:compose.dev.yml docker compose config > /tmp/new-dev.yml
docker compose -f docker-compose.dev.yml config > /tmp/old-dev.yml
diff /tmp/old-dev.yml /tmp/new-dev.yml
```

Expected: отличия только в `container_name` (отсутствует) и порядке ключей. Функционально эквивалентно.

**Step 3: Commit**

```bash
git add compose.dev.yml
git commit -m "feat(docker): create compose.dev.yml override — ports, colbert, relaxed defaults"
```

---

### Task 3: Создать compose.vps.yml (VPS override)

**Files:**
- Create: `compose.vps.yml`

**Step 1: Создать файл с VPS-specific override'ами**

```yaml
# compose.vps.yml — VPS production overrides: memory limits, no colbert reranking.
# Usage: COMPOSE_FILE=compose.yml:compose.vps.yml docker compose up -d

services:
  bot:
    environment:
      RERANK_PROVIDER: "none"
      RERANK_CANDIDATES_MAX: "5"

  langfuse:
    ports:
      - "127.0.0.1:3001:3000"
```

Примечание: memory limits, security_opt, healthchecks уже в base (compose.yml) с VPS-safe значениями. Redis maxmemory через `${REDIS_MAXMEMORY:-256mb}` в base. VPS .env не переопределяет — получает 256mb default. Dev override задаёт 512mb.

**Step 2: Валидация merged VPS config**

```bash
COMPOSE_FILE=compose.yml:compose.vps.yml docker compose config > /tmp/new-vps.yml
docker compose -f docker-compose.vps.yml config > /tmp/old-vps.yml
diff /tmp/old-vps.yml /tmp/new-vps.yml
```

Expected: отличия только в `container_name` и dev-only сервисах (mlflow, loki, promtail, alertmanager, livekit, voice — присутствуют в base за profiles, не запускаются без `--profile`).

**Step 3: Commit**

```bash
git add compose.vps.yml
git commit -m "feat(docker): create compose.vps.yml override — RERANK=none, langfuse port"
```

---

### Task 4: Обновить .env.example

**Files:**
- Modify: `.env.example`

**Step 1: Добавить COMPOSE_FILE и COMPOSE_PROJECT_NAME в начало файла**

Добавить после первого комментария:

```bash
# =============================================================================
# Docker Compose environment selection
# =============================================================================
# Local dev (default):
COMPOSE_FILE=compose.yml:compose.dev.yml
COMPOSE_PROJECT_NAME=dev
# VPS production (set on VPS):
# COMPOSE_FILE=compose.yml:compose.vps.yml
# COMPOSE_PROJECT_NAME=vps
```

**Step 2: Добавить REDIS_MAXMEMORY**

В секцию Redis:

```bash
REDIS_MAXMEMORY=512mb  # dev: 512mb, VPS: 256mb (default in compose.yml)
```

**Step 3: Commit**

```bash
git add .env.example
git commit -m "feat(docker): add COMPOSE_FILE and COMPOSE_PROJECT_NAME to .env.example"
```

---

### Task 5: Обновить Makefile

**Files:**
- Modify: `Makefile:365` (COMPOSE_CMD) и `Makefile:520-521` (deploy-bot)

**Step 1: Изменить COMPOSE_CMD**

```makefile
# Было:
COMPOSE_CMD := docker compose --compatibility -f docker-compose.dev.yml

# Стало (COMPOSE_FILE из .env):
COMPOSE_CMD := docker compose --compatibility
```

**Step 2: Изменить deploy-bot target**

```makefile
# Было:
deploy-bot:
	...
	docker compose -f docker-compose.vps.yml build bot && \
	docker compose --compatibility -f docker-compose.vps.yml up -d --force-recreate bot"

# Стало:
deploy-bot:
	...
	docker compose build bot && \
	docker compose --compatibility up -d --force-recreate bot"
```

**Step 3: Обновить комментарий**

```makefile
# Было:
# Local Development (single docker-compose.dev.yml)

# Стало:
# Local Development (compose.yml + compose.dev.yml via COMPOSE_FILE env)
```

**Step 4: Тест — проверить что make targets парсятся**

```bash
make -n docker-core-up
make -n docker-bot-up
make -n deploy-bot
```

Expected: команды выводятся без `-f docker-compose.dev.yml`.

**Step 5: Commit**

```bash
git add Makefile
git commit -m "feat(docker): update Makefile to use COMPOSE_FILE env instead of -f flag"
```

---

### Task 6: Обновить scripts/deploy-vps.sh

**Files:**
- Modify: `scripts/deploy-vps.sh:34` (COMPOSE_FILE), строки с `-f ${COMPOSE_FILE}`

**Step 1: Убрать COMPOSE_FILE переменную и -f флаги**

```bash
# Было (строка 34):
COMPOSE_FILE="docker-compose.vps.yml"

# Стало: удалить эту строку полностью.
# VPS .env уже содержит COMPOSE_FILE=compose.yml:compose.vps.yml
```

**Step 2: Упростить команды**

```bash
# Было:
ssh_cmd "cd ${VPS_DIR} && docker compose -f ${COMPOSE_FILE} down -v"
ssh_cmd "cd ${VPS_DIR} && docker compose -f ${COMPOSE_FILE} build"
ssh_cmd "cd ${VPS_DIR} && docker compose --compatibility -f ${COMPOSE_FILE} up -d"

# Стало:
ssh_cmd "cd ${VPS_DIR} && docker compose down -v"
ssh_cmd "cd ${VPS_DIR} && docker compose build"
ssh_cmd "cd ${VPS_DIR} && docker compose --compatibility up -d"
```

**Step 3: Добавить проверку .env на VPS**

После секции "Pre-flight checks", добавить:

```bash
# Verify VPS has COMPOSE_FILE in .env
log "Checking VPS .env for COMPOSE_FILE..."
if ! ssh_cmd "grep -q '^COMPOSE_FILE=' ${VPS_DIR}/.env 2>/dev/null"; then
    error "VPS .env missing COMPOSE_FILE. Add: COMPOSE_FILE=compose.yml:compose.vps.yml"
    exit 1
fi
```

**Step 4: Commit**

```bash
git add scripts/deploy-vps.sh
git commit -m "feat(docker): simplify deploy-vps.sh — use COMPOSE_FILE from VPS .env"
```

---

### Task 7: Обновить CI/CD

**Files:**
- Modify: `.github/workflows/ci.yml` (deploy job)

**Step 1: Убрать -f флаги из SSH script**

```yaml
# Было:
script: |
  set -e
  cd /opt/rag-fresh
  echo "=== Pull latest code ==="
  git pull origin main
  echo "=== Rebuild bot image ==="
  docker compose -f docker-compose.vps.yml build bot
  echo "=== Restart bot ==="
  docker compose --compatibility -f docker-compose.vps.yml up -d --force-recreate bot
  echo "=== Wait for startup ==="
  sleep 15
  echo "=== Health check ==="
  docker ps --format '{{.Names}} {{.Status}}' | grep vps-bot
  echo "=== Deploy complete $(date -Iseconds) ==="

# Стало:
script: |
  set -e
  cd /opt/rag-fresh
  echo "=== Pull latest code ==="
  git pull origin main
  echo "=== Rebuild bot image ==="
  docker compose build bot
  echo "=== Restart bot ==="
  docker compose --compatibility up -d --force-recreate bot
  echo "=== Wait for startup ==="
  sleep 15
  echo "=== Health check ==="
  docker ps --format '{{.Names}} {{.Status}}' | grep vps-bot
  echo "=== Deploy complete $(date -Iseconds) ==="
```

**Step 2: Commit**

```bash
git add .github/workflows/ci.yml
git commit -m "feat(ci): use COMPOSE_FILE from VPS .env instead of -f flag"
```

---

### Task 8: Обновить локальный .env

**Files:**
- Modify: `.env` (локальный, gitignored)

**Step 1: Добавить COMPOSE_FILE и COMPOSE_PROJECT_NAME**

```bash
# Добавить в начало .env:
COMPOSE_FILE=compose.yml:compose.dev.yml
COMPOSE_PROJECT_NAME=dev
```

Также добавить `REDIS_MAXMEMORY=512mb` если отсутствует.

**Step 2: Валидация**

```bash
docker compose config --services
```

Expected: список всех сервисов (postgres, redis, qdrant, ...).

**Step 3: Не коммитить** (.env в .gitignore)

---

### Task 9: Полная валидация — diff старого и нового

**Files:** Нет изменений, только проверка.

**Step 1: Сравнить dev config**

```bash
COMPOSE_FILE=compose.yml:compose.dev.yml docker compose config > /tmp/new-dev-full.yml
docker compose -f docker-compose.dev.yml config > /tmp/old-dev-full.yml
diff /tmp/old-dev-full.yml /tmp/new-dev-full.yml | head -100
```

Expected: отличия только в:
- `container_name` отсутствует (заменяется на project name prefix)
- Порядок ключей (cosmetic)

**Step 2: Сравнить VPS config**

```bash
COMPOSE_FILE=compose.yml:compose.vps.yml docker compose config > /tmp/new-vps-full.yml
docker compose -f docker-compose.vps.yml config > /tmp/old-vps-full.yml
diff /tmp/old-vps-full.yml /tmp/new-vps-full.yml | head -100
```

Expected: отличия только в:
- `container_name` отсутствует
- Dev-only сервисы появляются (за profiles, не запустятся)

**Step 3: Функциональный тест — запустить core**

```bash
docker compose down  # Остановить текущие контейнеры
docker compose up -d  # Запустить через новый compose
docker compose ps     # Проверить что всё поднялось
```

Expected: core сервисы работают, имена с prefix `dev-`.

**Step 4: Если всё ОК — остановить для чистоты**

```bash
docker compose down
```

---

### Task 10: Удалить старые файлы и финальный коммит

**Files:**
- Delete: `docker-compose.dev.yml`
- Delete: `docker-compose.vps.yml`

**Step 1: Удалить старые compose файлы**

```bash
git rm docker-compose.dev.yml docker-compose.vps.yml
```

**Step 2: Обновить CLAUDE.md**

В секции Commands заменить:

```bash
# Было:
make docker-full-up        # All services (23 containers)

# Стало (добавить пояснение):
make docker-full-up        # All services (23 containers, COMPOSE_FILE from .env)
```

**Step 3: Финальный коммит**

```bash
git add -u
git commit -m "feat(docker): remove old compose files — unification complete

BREAKING: docker-compose.dev.yml and docker-compose.vps.yml replaced by:
- compose.yml (base, all services)
- compose.dev.yml (dev override: ports, colbert)
- compose.vps.yml (VPS override: RERANK=none)

Switching: COMPOSE_FILE in .env controls environment.
"
```

---

### Task 11: Обновить VPS .env (remote)

**Files:** VPS `/opt/rag-fresh/.env` (remote)

**Step 1: Добавить COMPOSE_FILE на VPS**

```bash
ssh vps "grep -q '^COMPOSE_FILE=' /opt/rag-fresh/.env || \
  sed -i '1i COMPOSE_FILE=compose.yml:compose.vps.yml\nCOMPOSE_PROJECT_NAME=vps' /opt/rag-fresh/.env"
```

**Step 2: Проверить**

```bash
ssh vps "head -3 /opt/rag-fresh/.env"
```

Expected: первые строки содержат `COMPOSE_FILE=compose.yml:compose.vps.yml`.

**Step 3: Деплой и smoke test**

```bash
make deploy-bot
# Или: ./scripts/deploy-vps.sh --skip-checks
```

Expected: бот перезапускается на VPS, health check проходит.

---

## Порядок выполнения и зависимости

```
Task 1 (base) → Task 2 (dev) → Task 3 (vps) → Task 4 (.env.example)
                                                       ↓
Task 5 (Makefile) + Task 6 (deploy-vps.sh) + Task 7 (CI/CD)  ← параллельно
                                                       ↓
Task 8 (local .env) → Task 9 (валидация) → Task 10 (cleanup) → Task 11 (VPS)
```

Tasks 5, 6, 7 независимы и могут выполняться параллельно.

## Rollback

Если что-то пошло не так после Task 10:

```bash
git revert HEAD  # Вернёт docker-compose.dev.yml и docker-compose.vps.yml
# Или: git stash && git checkout HEAD~1 -- docker-compose.dev.yml docker-compose.vps.yml
```

На VPS: убрать COMPOSE_FILE из .env, вернуть `-f docker-compose.vps.yml` в deploy скрипт.

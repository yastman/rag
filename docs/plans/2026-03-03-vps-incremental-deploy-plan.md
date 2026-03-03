# VPS Incremental Deploy — Implementation Plan

> **Dispatch:** `/tmux-swarm-orchestration` — 2 Sonnet workers + координатор

**Goal:** Синхронизировать 29 новых коммитов на VPS, пересобрать bot image, восстановить bot + bge-m3, верифицировать.

**Design:** `docs/plans/2026-03-03-vps-incremental-deploy-design.md`

**VPS:** `ssh vps` → `admin@95.111.252.29:1654` | Path: `/opt/rag-fresh`

---

## Граф зависимостей

```
Task 1 (rsync) ─────→ Task 2 (rebuild bot) ──→ Task 4 (verify)
                                                     ↑
Task 3 (fix bge-m3 + litellm) ─────────────────────┘

Task 5 (post-deploy) ← Task 4
```

**Параллельные worker'ы:**
- Worker A: Task 1 → Task 2 → Task 4 → Task 5
- Worker B: Task 3 (независимо, параллельно с Task 1+2)

---

## Pre-flight (координатор, перед dispatch)

```bash
make check
PYTEST_ADDOPTS='-n auto --dist=worksteal' make test-unit
```

---

# Task 1: rsync code to VPS

**Worker:** A | **Зависимости:** нет | **Время:** ~30с
**Тип:** infra (SSH commands, no code changes)

### Что сделать

Синхронизировать код из main (29 новых коммитов) на VPS с обновлёнными rsync excludes.

### Команды

```bash
# rsync с оптимизированными excludes (экономия ~28MB)
rsync -avz --delete \
    --exclude '.git' --exclude '.venv' --exclude '__pycache__' \
    --exclude 'node_modules' --exclude '.mypy_cache' --exclude '.ruff_cache' \
    --exclude '.pytest_cache' --exclude '.cache' --exclude '.deepeval' \
    --exclude '.env' --exclude '.env.local' --exclude '.env.server' \
    --exclude 'logs/' --exclude 'data/' --exclude '.claude' \
    --exclude 'tests/' --exclude 'evaluation/' --exclude 'coverage*' \
    --exclude 'test_*.py' --exclude 'test_output*.txt' \
    --exclude 'docs/' --exclude 'k8s/' --exclude 'legacy/' --exclude 'deploy/' \
    --exclude '.planning/' --exclude '.signals/' --exclude '*.session' \
    --exclude 'requirements*.txt' \
    -e "ssh -i ~/.ssh/vps_access_key -p 1654 -o IdentitiesOnly=yes" \
    /home/user/projects/rag-fresh/ admin@95.111.252.29:/opt/rag-fresh/
```

### Верификация

```bash
# Проверить что docker-compose.vps.yml обновлён (без COLBERT_TIMEOUT)
ssh vps "grep -c COLBERT_TIMEOUT /opt/rag-fresh/docker-compose.vps.yml"
# Expected: 0
```

### Done criteria

- rsync завершён без ошибок
- `COLBERT_TIMEOUT` отсутствует в docker-compose.vps.yml на VPS

---

# Task 2: Rebuild and restart bot

**Worker:** A | **Зависимости:** Task 1 | **Время:** ~5 мин
**Тип:** infra (SSH + Docker commands)

### Что сделать

Пересобрать bot image с новым кодом (welcome redesign, viewing fixes, streaming) и запустить.

### Команды

```bash
# 1. Rebuild bot image (BuildKit cache для deps — только код layer пересобирается)
ssh vps "cd /opt/rag-fresh && docker compose -f docker-compose.vps.yml build bot"

# 2. Restart bot с новым image
ssh vps "cd /opt/rag-fresh && docker compose --compatibility -f docker-compose.vps.yml up -d bot"

# 3. Подождать startup + preflight (~15 сек)
sleep 20

# 4. Проверить логи
ssh vps "docker logs vps-bot --tail 30 2>&1"
```

### Верификация

```bash
ssh vps "docker ps --format '{{.Names}} {{.Status}}' | grep bot"
# Expected: vps-bot Up XX seconds (healthy) или (health: starting)
```

### Done criteria

- Bot image rebuilt successfully
- `vps-bot` контейнер running
- Логи: `Preflight: all dependencies OK`, `Start polling`

---

# Task 3: Fix unhealthy services (bge-m3 + litellm monitor)

**Worker:** B | **Зависимости:** нет | **Время:** ~5 мин
**Тип:** infra + debug (SSH commands)

### Что сделать

1. Диагностировать и перезапустить bge-m3 (unhealthy 25ч)
2. Проверить litellm memory (92.85% — near OOM limit)

### Команды

```bash
# 1. Диагностика bge-m3
ssh vps "docker logs vps-bge-m3 --tail 20 2>&1"
ssh vps "docker inspect vps-bge-m3 --format '{{json .State.Health}}' 2>/dev/null | python3 -m json.tool"

# 2. Restart bge-m3
ssh vps "docker restart vps-bge-m3"

# 3. Проверить litellm memory
ssh vps "docker stats --no-stream --format '{{.Name}} {{.MemUsage}} {{.MemPerc}}' | grep litellm"
# Если > 95%: рекомендовать увеличение limit до 768M

# 4. Ждать bge-m3 healthy (start_period: 180s)
echo "Waiting 180s for bge-m3 model loading..."
sleep 180

# 5. Верификация bge-m3
ssh vps "docker ps --format '{{.Names}} {{.Status}}' | grep bge"
```

### Решение по litellm

Если `MemPerc > 95%`:
```bash
# На VPS — увеличить memory limit
ssh vps "cd /opt/rag-fresh && sed -i 's/memory: 512M/memory: 768M/' docker-compose.vps.yml && docker compose --compatibility -f docker-compose.vps.yml up -d litellm"
```

### Done criteria

- bge-m3 status: `(healthy)`
- litellm memory: < 95% (или limit увеличен)
- Причина unhealthy задокументирована

---

# Task 4: Full verification

**Worker:** A | **Зависимости:** Task 2, Task 3 | **Время:** ~2 мин
**Тип:** verification

### Что сделать

Проверить что все контейнеры healthy, бот работает, ресурсы в норме.

### Команды

```bash
# 1. Все контейнеры
ssh vps "docker ps --format 'table {{.Names}}\t{{.Status}}\t{{.Image}}' | grep vps"
# Expected: 8/8 healthy (или 9/9 с ingestion)

# 2. Memory usage
ssh vps "docker stats --no-stream --format 'table {{.Name}}\t{{.MemUsage}}\t{{.MemPerc}}' | grep vps"
# Expected: total < 8 GB

# 3. Bot logs — no errors
ssh vps "docker logs vps-bot --tail 10 2>&1"
# Expected: polling active, no errors

# 4. Disk
ssh vps "df -h / | tail -1"
# Expected: > 40 GB free
```

### Smoke test

Отправить сообщение боту в Telegram (`@test_nika_homes_bot`).
Expected: бот отвечает, welcome message с новым дизайном.

### Done criteria

- Все контейнеры healthy
- Bot polling + отвечает в Telegram
- Memory < 8 GB total
- Нет ошибок в логах

---

# Task 5: Post-deploy cleanup

**Worker:** A | **Зависимости:** Task 4 | **Время:** ~1 мин
**Тип:** docs + git

### Что сделать

Обновить issue, закоммитить план и exclude изменения.

### Команды

```bash
# 1. Comment on issue #713
gh issue comment 713 --body "Incremental deploy complete (2026-03-03):
- 29 commits synced (welcome redesign, viewing fixes, streaming)
- Bot rebuilt and running
- bge-m3 restarted (healthy)
- rsync excludes optimized (-28MB transfer savings)
- All containers healthy"

# 2. Commit changes (координатор делает после merge)
git add scripts/deploy-vps.sh docker-compose.vps.yml \
    docs/plans/2026-03-03-vps-incremental-deploy-design.md \
    docs/plans/2026-03-03-vps-incremental-deploy-plan.md
git commit -m "feat(vps): incremental deploy + rsync exclude cleanup

- Add 16 rsync excludes (tests, docs, k8s, legacy) saving ~28MB
- Remove unused COLBERT_TIMEOUT from bot env
- Deploy 29 commits to VPS (welcome, viewing, streaming)

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

### Done criteria

- Issue #713 updated
- Changes committed to main

---

## Worker Assignment Summary

| Worker | Tasks | Время | Модель |
|--------|-------|-------|--------|
| **A** (deploy) | 1 → 2 → 4 → 5 | ~8 мин | Sonnet |
| **B** (fix) | 3 | ~5 мин | Sonnet |
| **Orch** (координатор) | pre-flight, merge, review | ~2 мин | Opus |

**Total wall-clock:** ~10 мин (tasks 2 и 3 параллельно)

## Контекст для workers

### Что изменилось в 29 коммитах

| Область | Коммиты | Файлы |
|---------|---------|-------|
| Welcome redesign | 7 коммитов | keyboards, locales (ru/uk/en), handlers |
| Viewing fixes | 3 коммита | dialogs/viewing.py, phone_collector |
| Streaming | 4 коммита | generate.py, generate_response.py |
| Langfuse docs | 2 коммита | docs only (не попадут на VPS) |
| Skills/swarm | 3 коммита | .claude only (не попадут на VPS) |

### VPS текущее состояние

- 8 containers running + bot Exited(137)
- bge-m3: unhealthy (25ч uptime)
- litellm: 92.85% RAM (475/512MB)
- Qdrant: 60 points, healthy
- Ingestion: just started (healthy)
- Disk: 50 GB free, RAM: 6.5 GB available

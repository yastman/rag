# VPS Deployment Implementation Plan

> **For Claude:** REQUIRED SKILL: `/tmux-swarm-orchestration` для Phase 0 (параллельная оптимизация Dockerfiles), затем `/executing-plans` для Phase 1 (последовательный deployment).

**Goal:** Задеплоить RAG чат-бот на VPS с локальными embeddings (BGE-M3) и Google Drive синхронизацией.

**Architecture:** Docker Compose стек из 9 сервисов (postgres, redis, qdrant, docling, bge-m3, user-base, bm42, litellm, bot) + опциональный `ingestion` (profile `ingest`). rclone синхронизирует Google Drive → локальная папка → CocoIndex индексирует в Qdrant.

**Tech Stack:** Docker Compose, rclone, BGE-M3, Qdrant, LiteLLM, Telegram Bot

---

# PHASE 0: Docker Optimization (tmux-swarm)

## Swarm Setup

### Структура воркеров

| Worker | Window | Worktree | Task | Files |
|--------|--------|----------|------|-------|
| W-BGE | `W-BGE` | `.worktrees/opt-bge` | Task 0.1 | `services/bge-m3-api/Dockerfile` |
| W-USER | `W-USER` | `.worktrees/opt-user` | Task 0.2 | `services/user-base/Dockerfile` |
| W-BM42 | `W-BM42` | `.worktrees/opt-bm42` | Task 0.3 | `services/bm42/Dockerfile` |
| W-BOT | `W-BOT` | `.worktrees/opt-bot` | Task 0.4 | `telegram_bot/Dockerfile` |
| W-DOC | `W-DOC` | `.worktrees/opt-docling` | Task 0.5 | `services/docling/Dockerfile` (create) |

### Pre-flight (оркестратор)

```bash
# 1. Проверить tmux
echo $TMUX

# 2. Создать директории
mkdir -p logs .worktrees

# 3. Создать worktrees
git worktree add .worktrees/opt-bge -b opt/bge-m3 main
git worktree add .worktrees/opt-user -b opt/user-base main
git worktree add .worktrees/opt-bm42 -b opt/bm42 main
git worktree add .worktrees/opt-bot -b opt/bot main
git worktree add .worktrees/opt-docling -b opt/docling main

# 4. Создать окна
tmux new-window -n "W-BGE" -c /home/user/projects/rag-fresh/.worktrees/opt-bge
tmux new-window -n "W-USER" -c /home/user/projects/rag-fresh/.worktrees/opt-user
tmux new-window -n "W-BM42" -c /home/user/projects/rag-fresh/.worktrees/opt-bm42
tmux new-window -n "W-BOT" -c /home/user/projects/rag-fresh/.worktrees/opt-bot
tmux new-window -n "W-DOC" -c /home/user/projects/rag-fresh/.worktrees/opt-docling
```

### Spawn Workers

**Worker W-BGE:**
```bash
tmux send-keys -t "W-BGE" "claude --dangerously-skip-permissions 'W-BGE: Оптимизировать BGE-M3 Dockerfile.

ПЛАН: /home/user/projects/rag-fresh/docs/plans/2026-02-05-vps-deployment-plan.md
ЗАДАЧА: Task 0.1

Оптимизации:
- Multi-stage build (builder + runtime)
- Cache mounts для pip
- Non-root user (appuser:1001)
- PYTHONDONTWRITEBYTECODE=1
- CPU-only torch via --index-url https://download.pytorch.org/whl/cpu

ТЕСТ: docker build -f services/bge-m3-api/Dockerfile services/bge-m3-api/ -t test-bge-opt

ЛОГИРОВАНИЕ в /home/user/projects/rag-fresh/logs/worker-bge.log:
[START] timestamp Task
[DONE] timestamp Task
[COMPLETE] timestamp Worker finished

НЕ делай git commit.'" Enter
```

**Worker W-USER:**
```bash
tmux send-keys -t "W-USER" "claude --dangerously-skip-permissions 'W-USER: Оптимизировать User-Base Dockerfile.

ПЛАН: /home/user/projects/rag-fresh/docs/plans/2026-02-05-vps-deployment-plan.md
ЗАДАЧА: Task 0.2

Оптимизации: multi-stage, cache mounts, non-root, PYTHONDONTWRITEBYTECODE=1

ТЕСТ: docker build -f services/user-base/Dockerfile services/user-base/ -t test-user-opt

ЛОГИРОВАНИЕ в /home/user/projects/rag-fresh/logs/worker-user.log:
[START] timestamp Task
[DONE] timestamp Task
[COMPLETE] timestamp Worker finished

НЕ делай git commit.'" Enter
```

**Worker W-BM42:**
```bash
tmux send-keys -t "W-BM42" "claude --dangerously-skip-permissions 'W-BM42: Оптимизировать BM42 Dockerfile.

ПЛАН: /home/user/projects/rag-fresh/docs/plans/2026-02-05-vps-deployment-plan.md
ЗАДАЧА: Task 0.3

Оптимизации: multi-stage, cache mounts, non-root, pre-download model в builder

ТЕСТ: docker build -f services/bm42/Dockerfile services/bm42/ -t test-bm42-opt

ЛОГИРОВАНИЕ в /home/user/projects/rag-fresh/logs/worker-bm42.log:
[START] timestamp Task
[DONE] timestamp Task
[COMPLETE] timestamp Worker finished

НЕ делай git commit.'" Enter
```

**Worker W-BOT:**
```bash
tmux send-keys -t "W-BOT" "claude --dangerously-skip-permissions 'W-BOT: Добавить cache mounts в Bot Dockerfile.

ПЛАН: /home/user/projects/rag-fresh/docs/plans/2026-02-05-vps-deployment-plan.md
ЗАДАЧА: Task 0.4

Изменение: заменить --no-cache-dir на --mount=type=cache,target=/root/.cache/pip

ТЕСТ: docker build -f telegram_bot/Dockerfile . -t test-bot-opt

ЛОГИРОВАНИЕ в /home/user/projects/rag-fresh/logs/worker-bot.log:
[START] timestamp Task
[DONE] timestamp Task
[COMPLETE] timestamp Worker finished

НЕ делай git commit.'" Enter
```

**Worker W-DOC:**
```bash
tmux send-keys -t "W-DOC" "claude --dangerously-skip-permissions 'W-DOC: Создать CPU-only Docling Dockerfile.

ПЛАН: /home/user/projects/rag-fresh/docs/plans/2026-02-05-vps-deployment-plan.md
ЗАДАЧА: Task 0.5

Создать services/docling/Dockerfile с:
- CPU-only PyTorch (--extra-index-url https://download.pytorch.org/whl/cpu)
- Multi-stage build
- Non-root user
- External model cache volume

ТЕСТ: docker build -f services/docling/Dockerfile services/docling/ -t test-docling-cpu

ЛОГИРОВАНИЕ в /home/user/projects/rag-fresh/logs/worker-docling.log:
[START] timestamp Task
[DONE] timestamp Task
[COMPLETE] timestamp Worker finished

НЕ делай git commit.'" Enter
```

### Auto-Monitor

Создать `scripts/monitor-workers.sh`:

```bash
#!/bin/bash
declare -A WINDOW_MAP=(
  ["worker-bge"]="W-BGE"
  ["worker-user"]="W-USER"
  ["worker-bm42"]="W-BM42"
  ["worker-bot"]="W-BOT"
  ["worker-docling"]="W-DOC"
)

while true; do
  for k in "${!WINDOW_MAP[@]}"; do
    grep -q '\[COMPLETE\]' "logs/${k}.log" 2>/dev/null && \
      tmux kill-window -t "${WINDOW_MAP[$k]}" 2>/dev/null
  done
  sleep 30
done
```

Запуск: `nohup ./scripts/monitor-workers.sh > logs/monitor.log 2>&1 &`

### Post-Swarm (оркестратор)

После всех `[COMPLETE]`:

```bash
# 1. Собрать изменения из worktrees
cd /home/user/projects/rag-fresh
git checkout main

# 2. Merge каждой ветки
for branch in opt/bge-m3 opt/user-base opt/bm42 opt/bot opt/docling; do
  git merge $branch --no-edit
done

# 3. Task 0.6: Локальный тест всех образов
docker compose -f docker-compose.vps.yml build --parallel
docker images --format "table {{.Repository}}\t{{.Tag}}\t{{.Size}}" | grep -E "vps|bge|user-base|bm42|bot|docling"

# 4. Cleanup worktrees
git worktree remove .worktrees/opt-bge
git worktree remove .worktrees/opt-user
git worktree remove .worktrees/opt-bm42
git worktree remove .worktrees/opt-bot
git worktree remove .worktrees/opt-docling

# 5. Commit
git add services/bge-m3-api/Dockerfile services/user-base/Dockerfile services/bm42/Dockerfile telegram_bot/Dockerfile services/docling/Dockerfile
git commit -m "perf(docker): optimize Dockerfiles for VPS deployment

- Multi-stage builds for bge-m3, user-base, bm42, docling
- Add cache mounts for pip (faster rebuilds)
- Add non-root users (security)
- CPU-only PyTorch for docling (-70% image size)

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

# PHASE 0 Details: Docker Optimization (Best Practices 2026)

> **Note:** Детали ниже — референс для воркеров. Оркестратор использует Swarm Setup выше.

## Task 0.1: Оптимизация BGE-M3 Dockerfile

**Files:**
- Modify: `services/bge-m3-api/Dockerfile`

**Оптимизации:**
- Multi-stage build (builder + runtime)
- Cache mounts для pip
- Non-root user
- PYTHONDONTWRITEBYTECODE=1

**Step 1: Заменить Dockerfile**

```dockerfile
# syntax=docker/dockerfile:1.4
# BGE-M3 Embedding Service - Optimized for VPS (2026 best practices)

# ====== BUILD STAGE ======
FROM python:3.12-slim AS builder

WORKDIR /app

# Install system dependencies for building
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgomp1 \
    && rm -rf /var/lib/apt/lists/*

# Create virtual environment
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Install CPU-only torch first (separate index)
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --upgrade pip && \
    pip install torch --index-url https://download.pytorch.org/whl/cpu

# Copy and install remaining requirements
COPY requirements.txt .
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install -r requirements.txt

# ====== RUNTIME STAGE ======
FROM python:3.12-slim AS runtime

# Install runtime dependencies only
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgomp1 \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user
RUN groupadd -g 1001 appgroup && \
    useradd -u 1001 -g appgroup -m -d /app -s /bin/false appuser

WORKDIR /app

# Copy virtual environment from builder
COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Environment for HF cache (will be mounted as volume)
ENV HF_HOME=/models/hf \
    TRANSFORMERS_CACHE=/models/hf \
    SENTENCE_TRANSFORMERS_HOME=/models/sentence-transformers \
    OMP_NUM_THREADS=2 \
    MKL_NUM_THREADS=2 \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# Copy application code
COPY --chown=appuser:appgroup config.py app.py ./

USER appuser

EXPOSE 8000

# Run with limited concurrency for VPS
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1", "--limit-concurrency", "4"]
```

**Step 2: Проверить синтаксис**

Run: `docker build -f services/bge-m3-api/Dockerfile services/bge-m3-api/ --target builder -t test-bge-builder`

Expected: `Successfully built`

**Step 3: Сравнить размер**

Run: `docker images | grep -E "bge|test"`

Expected: Размер runtime меньше чем был раньше

---

## Task 0.2: Оптимизация User-Base Dockerfile

**Files:**
- Modify: `services/user-base/Dockerfile`

**Step 1: Заменить Dockerfile**

```dockerfile
# syntax=docker/dockerfile:1.4
# USER-base Embedding Service - Optimized for VPS

# ====== BUILD STAGE ======
FROM python:3.12-slim AS builder

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    libgomp1 \
    && rm -rf /var/lib/apt/lists/*

RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# CPU-only torch
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --upgrade pip && \
    pip install torch --index-url https://download.pytorch.org/whl/cpu

COPY requirements.txt .
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install -r requirements.txt

# ====== RUNTIME STAGE ======
FROM python:3.12-slim AS runtime

RUN apt-get update && apt-get install -y --no-install-recommends \
    libgomp1 \
    && rm -rf /var/lib/apt/lists/*

RUN groupadd -g 1001 appgroup && \
    useradd -u 1001 -g appgroup -m -d /app -s /bin/false appuser

WORKDIR /app

COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

ENV HF_HOME=/models/hf \
    TRANSFORMERS_CACHE=/models/hf \
    SENTENCE_TRANSFORMERS_HOME=/models/sentence-transformers \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

COPY --chown=appuser:appgroup main.py .

USER appuser

EXPOSE 8000
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
```

**Step 2: Проверить билд**

Run: `docker build -f services/user-base/Dockerfile services/user-base/ -t test-user-base`

Expected: `Successfully built`

---

## Task 0.3: Оптимизация BM42 Dockerfile

**Files:**
- Modify: `services/bm42/Dockerfile`

**Step 1: Заменить Dockerfile**

```dockerfile
# syntax=docker/dockerfile:1.4
# BM42 Sparse Embedding Service - Optimized

# ====== BUILD STAGE ======
FROM python:3.12-slim AS builder

WORKDIR /app

RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Install dependencies with cache mount
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --upgrade pip && \
    pip install \
        fastapi>=0.115.0 \
        uvicorn>=0.32.0 \
        fastembed>=0.7.0 \
        pydantic>=2.0.0

# Pre-download model during build (cached in image)
RUN python -c "from fastembed import SparseTextEmbedding; SparseTextEmbedding('Qdrant/bm42-all-minilm-l6-v2-attentions')"

# ====== RUNTIME STAGE ======
FROM python:3.12-slim AS runtime

RUN groupadd -g 1001 appgroup && \
    useradd -u 1001 -g appgroup -m -d /app -s /bin/false appuser

WORKDIR /app

COPY --from=builder /opt/venv /opt/venv
#
# fastembed кеширует модель в ~/.cache/fastembed. В builder это /root/.cache/fastembed.
# В runtime HOME пользователя = /app, поэтому кладём кеш в /app/.cache/fastembed чтобы не было
# повторной загрузки на старте.
COPY --from=builder /root/.cache/fastembed /app/.cache/fastembed

ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

COPY --chown=appuser:appgroup main.py .

RUN chown -R appuser:appgroup /app/.cache

USER appuser

EXPOSE 8000
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
```

**Step 2: Проверить билд**

Run: `docker build -f services/bm42/Dockerfile services/bm42/ -t test-bm42`

Expected: `Successfully built`

---

## Task 0.4: Добавить cache mounts в Bot Dockerfile

**Files:**
- Modify: `telegram_bot/Dockerfile`

**Step 1: Добавить cache mount в builder stage**

Найти строку:
```dockerfile
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt
```

Заменить на:
```dockerfile
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --upgrade pip && \
    pip install -r requirements.txt
```

**Step 2: Проверить билд**

Run: `docker build -f telegram_bot/Dockerfile . -t test-bot`

Expected: `Successfully built`

---

## Task 0.5 (опционально): Оптимизация Docling Dockerfile (CPU-only)

**Files:**
- Create: `services/docling/Dockerfile`
- Modify: `docker-compose.vps.yml`

**Оптимизации:**
- CPU-only PyTorch (`--extra-index-url https://download.pytorch.org/whl/cpu`)
- Multi-stage build
- Non-root user
- External model cache volume

**Step 1: Создать Dockerfile в `services/docling/Dockerfile`**

Ключевые строки:
```dockerfile
# CPU-only PyTorch (critical!)
RUN pip install torch torchvision \
    --extra-index-url https://download.pytorch.org/whl/cpu

# Then docling-serve
RUN pip install "docling-serve[ui]" \
    --extra-index-url https://download.pytorch.org/whl/cpu
```

**Step 2: Проверить билд**

Run:
```bash
docker build -f services/docling/Dockerfile services/docling/ -t test-docling-cpu
```

Expected: `Successfully built` (5-10 минут первый раз)

**Step 3: Проверить размер**

Run: `docker images | grep docling`

Expected:
```
test-docling-cpu    latest    ...    ~2GB      ← наш оптимизированный
ghcr.io/.../cpu     ...       ...    ~6.9GB    ← официальный
```

**Экономия:** ~5GB на образе, ~70% меньше

---

## Task 0.6: Локальный тест всех образов

**Step 1: Билд всех образов**

Run:
```bash
docker compose -f docker-compose.vps.yml build --parallel
```

Expected: Все образы, которые собираются из репозитория, собраны без ошибок (обычно: `bge-m3`, `user-base`, `bm42`, `bot`; `ingestion` — только если включён профиль `ingest`; `docling` — только если выполнен Task 0.5)

**Step 2: Запустить локально для проверки**

Run:
```bash
docker compose --compatibility -f docker-compose.vps.yml up -d
docker compose -f docker-compose.vps.yml ps
```

Expected: Контейнеры стартуют, healthcheck проходит (учесть, что `docling` и `bge-m3` могут стартовать 5–10 минут из‑за загрузки моделей)

**Step 3: Проверить размеры образов**

Run:
```bash
docker images --format "table {{.Repository}}\t{{.Tag}}\t{{.Size}}" | grep -E "vps|bge|user-base|bm42|bot"
```

Expected: Образы меньше чем до оптимизации

**Step 4: Остановить тестовые контейнеры**

Run: `docker compose -f docker-compose.vps.yml down`

**Step 5: Commit оптимизированные Dockerfiles**

Run:
```bash
git add services/bge-m3-api/Dockerfile services/user-base/Dockerfile services/bm42/Dockerfile telegram_bot/Dockerfile
git commit -m "perf(docker): optimize Dockerfiles for VPS deployment

- Multi-stage builds for bge-m3, user-base, bm42
- Add cache mounts for pip (faster rebuilds)
- Add non-root users (security)
- Add PYTHONDONTWRITEBYTECODE=1 (smaller images)

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

# PHASE 1: Deployment (sequential, use /executing-plans)

> **For Claude:** После Phase 0 используй `/executing-plans` для последовательного выполнения Tasks 1-13. Эти задачи зависят друг от друга и не могут выполняться параллельно.

## Task 1: Подготовка .env файла локально

**Files:**
- Create: `/home/user/projects/rag-fresh/.env.vps`

**Step 1: Создать .env.vps с обязательными переменными**

```bash
cat > /home/user/projects/rag-fresh/.env.vps << 'EOF'
# === Обязательные ===
TELEGRAM_BOT_TOKEN=YOUR_BOT_TOKEN_HERE
LITELLM_MASTER_KEY=GENERATE_A_RANDOM_KEY

# === LLM провайдеры ===
CEREBRAS_API_KEY=YOUR_CEREBRAS_KEY_HERE
GROQ_API_KEY=YOUR_GROQ_KEY_HERE
OPENAI_API_KEY=YOUR_OPENAI_KEY_HERE

# === Host paths / compose vars ===
# ВАЖНО: docker compose не обязан разворачивать `~` в переменных. Используй абсолютный путь.
GDRIVE_SYNC_DIR=/opt/rag-fresh/drive-sync
# Коллекция, которую будет читать bot (по умолчанию: gdrive_documents_bge)
QDRANT_COLLECTION=gdrive_documents_bge
EOF
```

Подсказка для `LITELLM_MASTER_KEY`:
```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

**Step 2: Заполнить реальные ключи из текущего .env**

Run: `grep -E "TELEGRAM_BOT_TOKEN|CEREBRAS_API_KEY|GROQ_API_KEY|OPENAI_API_KEY" /home/user/projects/rag-fresh/.env`

Скопировать значения в `.env.vps`, а `LITELLM_MASTER_KEY` сгенерировать (см. подсказку выше).

**Step 3: Проверить файл**

Run: `cat /home/user/projects/rag-fresh/.env.vps | grep -v "^#" | grep -v "^$"`

Expected: 7-8 непустых строк с реальными значениями (не YOUR_*_HERE)

---

## Task 2: Проверить SSH доступ к VPS

**Step 1: Проверить алиас vps**

Run: `grep -A5 "Host vps" ~/.ssh/config || echo "No vps alias"`

Expected: Конфигурация с HostName, User, IdentityFile

**Step 2: Проверить подключение**

Run: `ssh vps "echo 'VPS OK: $(hostname)' && free -h | head -2"`

Expected:
```
VPS OK: <hostname>
              total        used        free
Mem:           15Gi        ...
```

**Step 3: Проверить Docker на VPS**

Run: `ssh vps "docker --version && docker compose version"`

Expected: Docker version 20+ и Docker Compose v2+

Если Docker не установлен → Task 2.1

---

## Task 2.1: Установка Docker на VPS (если нужно)

**Step 1: Установить Docker**

Run:
```bash
ssh vps "sudo apt update && sudo apt install -y docker.io docker-compose-v2 && sudo usermod -aG docker \$USER"
```

Expected: Installation complete, no errors

**Step 2: Переподключиться (для группы docker)**

Run: `ssh vps "docker ps"`

Expected: Пустой список контейнеров (не permission denied)

---

## Task 3: Установить rclone на VPS

**Step 1: Проверить rclone**

Run: `ssh vps "which rclone || echo 'not installed'"`

**Step 2: Установить rclone (если нужно)**

Run: `ssh vps "curl https://rclone.org/install.sh | sudo bash"`

Expected: `rclone v1.6x.x has finished installing`

**Step 3: Создать директорию конфига**

Run: `ssh vps "mkdir -p ~/.config/rclone"`

---

## Task 4: Скопировать rclone конфиг на VPS

**Step 1: Скопировать rclone.conf**

Run: `scp ~/.config/rclone/rclone.conf vps:~/.config/rclone/rclone.conf`

Expected: `rclone.conf   100%   ...`

**Step 2: Проверить конфиг на VPS**

Run: `ssh vps "rclone listremotes"`

Expected: `gdrive:`

**Step 3: Проверить доступ к Google Drive**

Run: `ssh vps "rclone lsd gdrive: | head -5"`

Expected: Список папок (включая `RAG`)

---

## Task 5: Клонировать репозиторий на VPS

**Step 1: Создать директорию**

Run: `ssh vps "sudo mkdir -p /opt/rag-fresh && sudo chown \$USER:\$USER /opt/rag-fresh"`

**Step 2: Клонировать репо**

Run: `ssh vps "git clone https://github.com/YOUR_USER/rag-fresh.git /opt/rag-fresh || (cd /opt/rag-fresh && git pull)"`

Expected: `Cloning into '/opt/rag-fresh'...` или `Already up to date.`

**Step 3: Проверить файлы**

Run: `ssh vps "ls /opt/rag-fresh/docker-compose.vps.yml"`

Expected: Путь к файлу без ошибок

---

## Task 6: Скопировать .env на VPS

**Step 1: Скопировать .env.vps**

Run: `scp /home/user/projects/rag-fresh/.env.vps vps:/opt/rag-fresh/.env`

Expected: `.env.vps   100%   ...`

**Step 2: Проверить переменные**

Run: `ssh vps "grep TELEGRAM_BOT_TOKEN /opt/rag-fresh/.env | cut -c1-30"`

Expected: `TELEGRAM_BOT_TOKEN=...` (начало токена)

---

## Task 7: Запустить Docker стек

**Step 1: Скачать внешние образы (только те, у кого есть `image:`)**

Run:
```bash
ssh vps "cd /opt/rag-fresh && docker compose -f docker-compose.vps.yml pull"
```

Expected: Pulling images... (может занять 5-10 минут)

**Step 2: Собрать сервисы из репозитория (те, у кого есть `build:`)**

Run:
```bash
ssh vps "cd /opt/rag-fresh && docker compose -f docker-compose.vps.yml build --parallel"
```

Expected: Сборка `bge-m3`, `user-base`, `bm42`, `bot` прошла без ошибок

**Step 3: Запустить контейнеры (с применением `deploy.resources` лимитов)**

Run:
```bash
ssh vps "cd /opt/rag-fresh && docker compose --compatibility -f docker-compose.vps.yml up -d"
```

Expected: `Creating vps-postgres ... done` (и остальные 8 контейнеров)

**Step 4: Проверить статус**

Run:
```bash
ssh vps "docker ps --format 'table {{.Names}}\t{{.Status}}' | grep vps"
```

Expected: 9 контейнеров, все `Up` или `Up (health: starting)`

---

## Task 8: Дождаться здоровья всех сервисов

**Step 1: Мониторить health (запустить несколько раз с интервалом 30 сек)**

Run:
```bash
ssh vps "docker ps --format 'table {{.Names}}\t{{.Status}}' | grep -E 'vps|NAMES'"
```

Expected через 5-10 минут:
```
NAMES           STATUS
vps-bot         Up X minutes (healthy)
vps-litellm     Up X minutes (healthy)
vps-docling     Up X minutes (healthy)  ← загрузка моделей парсинга
vps-bge-m3      Up X minutes (healthy)  ← загрузка BGE-M3 модели
vps-user-base   Up X minutes (healthy)
vps-bm42        Up X minutes (healthy)
vps-qdrant      Up X minutes (healthy)
vps-redis       Up X minutes (healthy)
vps-postgres    Up X minutes (healthy)
```

**Step 2: Проверить логи bge-m3 (если долго стартует)**

Run: `ssh vps "docker logs vps-bge-m3 --tail 20"`

Expected: `Downloading model...` или `Uvicorn running on http://0.0.0.0:8000`

---

## Task 9: Синхронизировать Google Drive

**Step 1: Создать директорию для синхронизации**

Run: `ssh vps "mkdir -p /opt/rag-fresh/drive-sync"`

**Step 2: Запустить первичную синхронизацию**

Run:
```bash
ssh vps "rclone sync gdrive:RAG /opt/rag-fresh/drive-sync/ --progress"
```

Expected:
```
Transferred:   XX KiB / XX KiB, 100%, 0 B/s, ETA -
Transferred:   XX files
```

**Step 3: Проверить файлы**

Run: `ssh vps "ls -la /opt/rag-fresh/drive-sync/"`

Expected: Папки `Test/`, `Procesed/`, файл `.xlsx`

---

## Task 10: Настроить cron для rclone

**Step 1: Создать cron задачу**

Run:
```bash
ssh vps 'echo "*/5 * * * * $USER rclone sync gdrive:RAG /opt/rag-fresh/drive-sync/ -q --log-file /tmp/rclone-sync.log" | sudo tee /etc/cron.d/rclone-sync'
```

Примечание: путь в cron должен совпадать с `GDRIVE_SYNC_DIR` из `/opt/rag-fresh/.env`.

**Step 2: Проверить cron**

Run: `ssh vps "cat /etc/cron.d/rclone-sync"`

Expected: Cron строка с `*/5 * * * *`

---

## Task 11: Создать коллекцию Qdrant

> Примечание: в `docker-compose.vps.yml` порты сервисов не публикуются на хост. Поэтому проверки через `curl localhost:...` на VPS **не сработают**. Используй `docker compose exec` внутри сети compose.

**Step 0: Открыть сессию на VPS**

Run:
```bash
ssh vps
cd /opt/rag-fresh
```

**Step 1: Проверить доступность Qdrant**

Run:
```bash
docker compose -f docker-compose.vps.yml exec -T bge-m3 python - <<'PY'
import json, urllib.request
print(json.load(urllib.request.urlopen('http://qdrant:6333/collections'))['result']['collections'])
PY
```

Expected: `[]` (пустой массив) или список существующих коллекций

**Step 2: Создать коллекцию gdrive_documents_bge**

Run:
```bash
docker compose -f docker-compose.vps.yml exec -T bge-m3 python - <<'PY'
import json
import urllib.request

url = 'http://qdrant:6333/collections/gdrive_documents_bge'
payload = {
  'vectors': {'dense': {'size': 1024, 'distance': 'Cosine'}},
  'sparse_vectors': {'bm42': {}},
}

req = urllib.request.Request(
  url,
  data=json.dumps(payload).encode('utf-8'),
  headers={'Content-Type': 'application/json'},
  method='PUT',
)
print(urllib.request.urlopen(req).read().decode('utf-8'))
PY
```

Expected: `{"result":true,"status":"ok"}`

**Step 3: Проверить коллекцию**

Run:
```bash
docker compose -f docker-compose.vps.yml exec -T bge-m3 python - <<'PY'
import json, urllib.request
print(json.load(urllib.request.urlopen('http://qdrant:6333/collections/gdrive_documents_bge'))['result']['status'])
PY
```

Expected: `"green"`

---

## Task 12: Запустить индексацию

**Step 1: Проверить Docling health**

Run:
```bash
docker compose -f docker-compose.vps.yml exec -T docling python -c "import urllib.request; print(urllib.request.urlopen('http://localhost:5001/health', timeout=5).read().decode())"
```

Expected: `{"status":"ok"}` или `200 OK`

**Step 2: Запустить ingestion контейнер**

Run:
```bash
docker compose --compatibility -f docker-compose.vps.yml --profile ingest up -d ingestion
```

Expected: `Creating vps-ingestion ... done`

**Step 3: Проверить логи ingestion**

Run: `docker logs vps-ingestion --tail 30`

Expected: `Processing files...`, `Indexed N chunks`

**Step 4: Проверить количество точек в Qdrant**

Run:
```bash
docker compose -f docker-compose.vps.yml exec -T bge-m3 python - <<'PY'
import json, urllib.request
print(json.load(urllib.request.urlopen('http://qdrant:6333/collections/gdrive_documents_bge'))['result']['points_count'])
PY
```

Expected: Число > 0 (зависит от количества файлов в `/opt/rag-fresh/drive-sync`)

**Step 5: Остановить ingestion (опционально)**

Run: `docker compose -f docker-compose.vps.yml --profile ingest stop ingestion`

Или оставить в watch mode для автоматического обновления

---

## Task 13: Финальная проверка

**Step 1: Статус всех сервисов**

Run:
```bash
docker ps --format 'table {{.Names}}\t{{.Status}}\t{{.Ports}}' | grep vps
```

Expected: Все 9 контейнеров healthy

**Step 2: Проверить RAM**

Run: `free -h`

Expected: Used < 12GB (из 16GB)

**Step 3: Проверить Qdrant**

Run:
```bash
docker compose -f docker-compose.vps.yml exec -T bge-m3 python - <<'PY'
import json, urllib.request
print(json.load(urllib.request.urlopen('http://qdrant:6333/collections/gdrive_documents_bge'))['result']['points_count'])
PY
```

Expected: `0` или число (если индексация прошла)

**Step 4: Проверить LiteLLM health**

Run:
```bash
docker compose -f docker-compose.vps.yml exec -T litellm python -c "import urllib.request; print(urllib.request.urlopen('http://localhost:4000/health/liveliness', timeout=5).read().decode())"
```

Expected: `"healthy"` или `{"status":"healthy"}`

---

## Execution Notes (2026-02-05)

**Отклонение от плана:** Вместо tmux-swarm локально, оптимизация выполнена напрямую на VPS:
1. rsync проекта на VPS (`/opt/rag-fresh/`)
2. Создание uv-оптимизированных Dockerfiles локально → scp на VPS
3. `docker compose build --parallel` на VPS
4. Фиксы по ходу: `transformers==4.44.2`, volume permissions, `--index-strategy unsafe-best-match`

**Образы на VPS:**
| Image | Size |
|-------|------|
| rag-fresh-docling | 3.52GB |
| rag-fresh-bge-m3 | 2.34GB |
| rag-fresh-user-base | 1.92GB |
| rag-fresh-bm42 | 964MB |
| rag-fresh-bot | 747MB |

---

## Execution Notes (2026-02-05, Session 2)

### Docling Container Fix

**Проблема 1:** RapidOCR скачивает модели в runtime в `/opt/venv/lib/python*/site-packages/rapidocr/models/`, но контейнер работает под non-root user.

**Fix:** Добавить в Dockerfile перед `USER appuser`:
```dockerfile
# RapidOCR downloads models at runtime to its package directory
RUN chmod -R a+rw /opt/venv/lib/python*/site-packages/rapidocr/ 2>/dev/null || true
```

**Проблема 2:** `libgl1-mesa-glx` переименован в `libgl1` в Debian Trixie (python:3.12-slim base).

**Fix:** Заменить `libgl1-mesa-glx` → `libgl1` в apt-get install.

### UserBaseVectorizer Fix (RedisVL 0.13.2)

**Проблема:** `SemanticCache(vectorizer=UserBaseVectorizer())` требует наследование от `redisvl.utils.vectorize.BaseVectorizer` (Pydantic model), не кастомный класс.

**Fix:** Переписать `telegram_bot/services/vectorizers.py`:
```python
from redisvl.utils.vectorize import BaseVectorizer

class UserBaseVectorizer(BaseVectorizer):
    model: str = "deepvk/USER2-base"
    dims: int = 768
    base_url: str = "http://localhost:8003"
    timeout: float = 5.0
    model_config = {"arbitrary_types_allowed": True}
    _sync_client: httpx.Client | None = None
    _async_client: httpx.AsyncClient | None = None
    # ... методы embed/aembed с httpx клиентами
```

### Redis Caching Verified

| Cache Type | Status | Index Pattern |
|------------|--------|---------------|
| SemanticCache | ✅ Working | `sem:v2:{vectorizer_id}` |
| EmbeddingsCache | ✅ Working | `emb:v2:{hash}` |
| MessageHistory | ✅ Working | `rag_conversations:v2:{vectorizer_id}` |
| SearchCache | ✅ Working | `search:v2:{index_ver}:{hash}` |
| RerankCache | ✅ Working | `rerank:v2:{hash}` |
| SparseCache | ✅ Working | `sparse:v2:{model}:{hash}` |

### Qdrant Collection Created

```bash
docker compose exec -T bge-m3 python - <<'PY'
# Created collection: gdrive_documents_bge
# Dense: 1024-dim (BGE-M3)
# Sparse: bm42 (FastEmbed)
PY
```

### rclone Configured

```bash
# Cron: every 5 minutes
*/5 * * * * user rclone sync gdrive:RAG /opt/rag-fresh/drive-sync/ -q --log-file /tmp/rclone-sync.log
```

### Final Status: 9/9 Containers Healthy

```
vps-postgres    healthy
vps-redis       healthy
vps-qdrant      healthy
vps-docling     healthy  ← fixed RapidOCR permissions
vps-bge-m3      healthy
vps-user-base   healthy
vps-bm42        healthy
vps-litellm     healthy
vps-bot         healthy
```

---

## Чеклист завершения

### Phase 0: Docker Optimization (uv, выполнено на VPS)
- [x] Dockerfiles оптимизированы с uv (2026-02-05)
- [x] Multi-stage builds для всех сервисов
- [x] Cache mounts (`--mount=type=cache,target=/root/.cache/uv`)
- [x] Non-root users (appuser:1001)
- [x] CPU-only PyTorch для docling/bge-m3
- [x] `docker compose build --parallel` на VPS успешно
- [x] FlagEmbedding fix: `transformers==4.44.2`
- [x] Docling fix: RapidOCR permissions + libgl1 (2026-02-05)
- [ ] Локальные worktrees удалены (cleanup needed)
- [ ] Commit с оптимизациями (на VPS, не в git)

### Phase 1: Deployment ✅ COMPLETE
- [x] SSH доступ работает (`vps` alias)
- [x] Docker установлен (v29.2.1)
- [x] rclone настроен, Google Drive доступен (2026-02-05)
- [x] Файлы скопированы на VPS (`/opt/rag-fresh/`)
- [x] .env скопирован с ключами (14 secrets)
- [x] **10/10 контейнеров healthy** (2026-02-05) — включая vps-ingestion
- [x] vps-docling healthy (RapidOCR fix applied)
- [x] Cron для rclone настроен (*/5 * * * *)
- [x] Коллекция Qdrant создана (`gdrive_documents_bge`) — 278 points
- [x] Redis caching verified (6 cache tiers)
- [x] UserBaseVectorizer fix для redisvl 0.13.2
- [x] Ingestion запущен, документы проиндексированы — 14/14 файлов, 278 points (2026-02-05, BGE_M3_TIMEOUT=600 + Semaphore(1))
- [x] Бот polling (`@test_nika_homes_bot`)

### Phase 2: Post-Deployment (Optional)
- [ ] Log rotation настроен (50MB max)
- [ ] Docker autostart включён
- [ ] Qdrant backup создан
- [ ] Мониторинг ресурсов настроен

### Phase 3: Future (Optional)
- [x] Миграция на uv — ВЫПОЛНЕНО (2026-02-05)

---

# PHASE 2: Post-Deployment Optimizations (Optional)

## Task 14: Настроить log rotation

**Зачем:** Логи Docker могут заполнить диск на VPS.

**Step 1: Проверить текущий размер логов**

Run:
```bash
docker system df -v | head -20
```

**Step 2: Добавить log rotation в docker daemon**

Run:
```bash
ssh vps 'sudo tee /etc/docker/daemon.json << EOF
{
  "log-driver": "json-file",
  "log-opts": {
    "max-size": "50m",
    "max-file": "3"
  }
}
EOF'
```

**Step 3: Перезапустить Docker**

Run: `ssh vps "sudo systemctl restart docker"`

**Step 4: Перезапустить контейнеры**

Run: `ssh vps "cd /opt/rag-fresh && docker compose --compatibility -f docker-compose.vps.yml up -d"`

---

## Task 15: Настроить автоматический restart

**Зачем:** Контейнеры должны подниматься после перезагрузки VPS.

**Step 1: Проверить restart policy**

Run: `ssh vps "docker inspect vps-bot --format '{{.HostConfig.RestartPolicy.Name}}'"`

Expected: `unless-stopped` (уже настроено в compose)

**Step 2: Включить Docker autostart**

Run: `ssh vps "sudo systemctl enable docker"`

---

## Task 16: Backup Qdrant данных

**Зачем:** Возможность восстановить коллекцию без переиндексации.

**Step 1: Создать snapshot**

Run:
```bash
ssh vps "docker compose -f /opt/rag-fresh/docker-compose.vps.yml exec -T qdrant \
  curl -X POST 'http://localhost:6333/collections/gdrive_documents_bge/snapshots'"
```

Expected: `{"result":{"name":"...-snapshot.snapshot"}}`

**Step 2: Скопировать snapshot локально (опционально)**

Run:
```bash
ssh vps "docker cp vps-qdrant:/qdrant/snapshots ./qdrant-backup-$(date +%Y%m%d)"
```

---

## Task 17: Мониторинг ресурсов (простой)

**Step 1: Проверить использование памяти контейнерами**

Run:
```bash
ssh vps "docker stats --no-stream --format 'table {{.Name}}\t{{.MemUsage}}\t{{.CPUPerc}}' | grep vps"
```

Expected: Все контейнеры в пределах лимитов

**Step 2: Настроить алерт на диск (опционально)**

Run:
```bash
ssh vps 'cat > /opt/rag-fresh/scripts/disk-alert.sh << "EOF"
#!/bin/bash
THRESHOLD=85
USAGE=$(df / | tail -1 | awk '{print $5}' | sed 's/%//')
if [ "$USAGE" -gt "$THRESHOLD" ]; then
  echo "Disk usage is ${USAGE}% on $(hostname)" | logger -t disk-alert
fi
EOF
chmod +x /opt/rag-fresh/scripts/disk-alert.sh
echo "0 * * * * root /opt/rag-fresh/scripts/disk-alert.sh" | sudo tee /etc/cron.d/disk-alert'
```

---

# PHASE 3: Future Optimizations (uv Migration)

## Task 18: Миграция на uv (10-100x быстрее pip)

**Зачем:** uv — современный менеджер пакетов на Rust, 10-100x быстрее pip.

**Когда делать:** После стабильной работы VPS, при следующем обновлении Dockerfiles.

**Pattern для Dockerfile с uv:**

```dockerfile
# syntax=docker/dockerfile:1.4
FROM python:3.12-slim AS builder

# Copy uv binary (no pip install needed!)
COPY --from=ghcr.io/astral-sh/uv:0.5.18 /uv /usr/local/bin/uv

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

WORKDIR /app

COPY requirements.txt .

# Install with cache mount (10-100x faster than pip)
RUN --mount=type=cache,target=/root/.cache/uv \
    uv pip install --system -r requirements.txt

FROM python:3.12-slim AS runtime
# ... copy site-packages from builder
```

**Сравнение скорости:**

| Метод | Cold Build | Warm Build |
|-------|------------|------------|
| pip (no cache) | 120s | 120s |
| pip + cache mount | 120s | 15s |
| **uv + cache mount** | **45s** | **3s** |

**Файлы для миграции:**
- `services/bge-m3-api/Dockerfile`
- `services/user-base/Dockerfile`
- `services/bm42/Dockerfile`
- `telegram_bot/Dockerfile`
- `services/docling/Dockerfile`

---

## Чеклист завершения

### Phase 0: Docker Optimization

| Оптимизация | До | После | Эффект |
|-------------|-----|-------|--------|
| **Multi-stage builds** | 1 stage | 2 stages | -30-50% размер образа |
| **Cache mounts** | `--no-cache-dir` | `--mount=type=cache` | 10x быстрее rebuild |
| **Non-root user** | root | appuser:1001 | Security hardening |
| **PYTHONDONTWRITEBYTECODE** | off | 1 | Меньше .pyc файлов |
| **Venv isolation** | system pip | /opt/venv | Чистый runtime stage |
| **CPU-only PyTorch** | default (CUDA) | `whl/cpu` index | **-82% размер (Docling)** |

### Размеры образов (ожидаемые)

| Образ | Официальный | Оптимизированный | Экономия |
|-------|-------------|------------------|----------|
| docling-serve-cpu | 6.9GB | ~2GB | -70% |
| bge-m3-api | ~4GB | ~2.5GB | -35% |
| user-base | ~3GB | ~2GB | -30% |
| bm42 | ~1.5GB | ~1GB | -30% |

### Источники (Exa 2026):
- CPU-only PyTorch: 9.74GB → 1.74GB (shekhargulati.com)
- Multi-stage builds: -50-75% image size (freecodecamp, medium)
- Cache mounts: 10x faster rebuilds (depot.dev, revsys)
- uv vs pip: 10-100x faster (astral.sh/uv, datacamp)
- Docker layer caching: oneuptime.com, northflank.com
- Docker best practices 2026: latestfromtechguy.com

---

## Security Checklist

| Аспект | Статус | Реализация |
|--------|--------|------------|
| Non-root containers | ✅ | `USER appuser` во всех Dockerfiles |
| No ports exposed to LAN | ✅ | Порты только в Docker network |
| Secrets in .env | ✅ | `${VAR:?required}` синтаксис |
| Memory limits | ✅ | `deploy.resources.limits` |
| Read-only volumes | ✅ | `:ro` для конфигов |
| Log rotation | Phase 2 | `/etc/docker/daemon.json` |
| Backup strategy | Phase 2 | Qdrant snapshots |

---

## Troubleshooting

| Проблема | Решение |
|----------|---------|
| Container OOM killed | Увеличить memory limit или убрать user-base |
| Docling slow startup | Нормально, загрузка моделей 2-5 мин |
| BGE-M3 slow startup | Нормально, загрузка модели 3-5 мин |
| rclone token expired | `rclone config reconnect gdrive:` |
| Bot не отвечает | `docker logs vps-bot`, проверить TELEGRAM_BOT_TOKEN |
| Qdrant unhealthy | Проверить disk space, `docker logs vps-qdrant` |
| Ingestion fails | Проверить DOCLING_URL, BGE_M3_URL в env |

---

## BUG (RESOLVED): Ingestion зависало после создания writer (2026-02-05)

**Симптомы (было):**
- Логи показывали `Getting writer...` и код зависал
- Логов `Got writer:` или `Getting docling...` не было

**Причина:** Race condition в class-level singleton `_writer` при параллельных вызовах `mutate()` от CocoIndex.

**Решение (применено на VPS):**
1. Добавлен `threading.Lock` для thread-safe singleton инициализации
2. Double-check locking pattern в `_get_writer()` и `_get_docling()`
3. Добавлены параметры `bm42_url`, `bge_m3_timeout`, `bge_m3_concurrency`

**Статус:** ✅ FIXED — логи теперь показывают полный flow:
```
Getting writer... → Got writer: <QdrantHybridWriter> → Getting docling... → Got writer and docling
```

---

## ISSUE (RESOLVED): BGE-M3 CPU inference медленный (2026-02-05)

**Симптомы (было):**
- Один батч (32 текста) занимает 8-50 секунд на CPU
- При 14 параллельных файлах запросы встают в очередь
- Timeout 300 сек недостаточен → массовые timeout ошибки

**Root Cause:** CocoIndex вызывает `mutate()` параллельно для всех файлов. На CPU-only VPS это создаёт очередь в BGE-M3, память растёт, timeouts.

**Решение (применено 2026-02-05):**

1. **Sequential processing** — добавлен `Semaphore(1)` в `qdrant_hybrid_target.py`:
```python
# src/ingestion/unified/targets/qdrant_hybrid_target.py
_process_semaphore = threading.Semaphore(1)

@classmethod
def mutate(cls, *all_mutations):
    with cls._process_semaphore:  # Один файл за раз
        # ... processing
```

2. **Timeout увеличен** — `BGE_M3_TIMEOUT=600` в `docker-compose.vps.yml`

**Преимущества sequential:**
- Предсказуемое время (файл = N секунд, не зависит от очереди)
- Стабильное потребление памяти (~2GB vs 8GB+ при параллельности)
- Никаких timeout — запрос завершается до следующего
- Проще дебажить (видно какой файл обрабатывается)

**Trade-off:** Общее время дольше (~2 мин/файл × 14 файлов = ~30 мин), но на CPU-only VPS это неизбежно.

**Почему НЕ платное API:**

| Провайдер | Русский | Dense | Sparse | ColBERT | Вердикт |
|-----------|---------|-------|--------|---------|---------|
| BGE-M3 (локально) | ✅ Отличный | ✅ | ✅ lexical_weights | ✅ | Все 3 вектора за 1 проход |
| Voyage/Jina/Cohere | ⚠️ Средний | ✅ | ❌ | ❌ | Только dense |

BGE-M3 уникален — генерирует **dense + sparse + ColBERT** за один проход. Критично для hybrid search + rerank

---

---

## ANOMALIES FOUND (2026-02-05, CPU Analysis)

### 1. Swap Overload — 3.16 GB / 4 GB

**Симптомы:**
- `kswapd0` процесс использует 8-9% CPU
- Load average: 6.99, 8.97, 8.47 (при ~4 vCPU — перегруз)

**Причина:** Суммарное потребление RAM всеми контейнерами превышает 12 GB физической памяти.

**Impact:** Замедление всех операций, особенно BGE-M3 inference.

**Решения:**
- [ ] Увеличить RAM на VPS (16GB → 24GB) — дорого
- [ ] Уменьшить лимиты контейнеров (bge-m3: 4GB → 3GB)
- [ ] Отключить user-base (семантический кеш) при ingestion
- [ ] Использовать swap на SSD (текущий конфиг ОК)

---

### 2. Zombie Processes — 226 штук

**Симптомы:**
```
Tasks: 458 total, 5 running, 227 sleeping, 0 stopped, 226 zombie
```

**Причина:** Docker/containerd не очищает завершённые процессы. Возможно утечка в entrypoint скриптах.

**Impact:** Минимальный на RAM, но показывает проблему с lifecycle.

**Диагностика:**
```bash
ps aux | grep -E 'Z|defunct' | head -20
```

**Решения:**
- [ ] Перезагрузить VPS (временно)
- [ ] Проверить entrypoint скрипты контейнеров на `exec` vs fork
- [ ] Добавить `tini` как init system в Dockerfiles

---

### 3. Ingestion Memory — 90% (464/512 MB)

**Симптомы:**
```
vps-ingestion   0.01%     463.8MiB / 512MiB   90.58%
```

**Причина:** Тяжёлые ML-зависимости (sentence-transformers, FlagEmbedding, docling) загружаются в память даже если не используются.

**Impact:** Риск OOM при обработке больших файлов.

**Решения:**
- [ ] Увеличить лимит до 768M-1G в docker-compose.vps.yml
- [ ] Создать slim версию ingestion без ML-библиотек (только HTTP клиенты)

---

### 4. Docker Image — 28 GB (anomaly)

**Симптомы:**
```
rag-fresh_ingestion:latest   28GB   9.51GB content
```

**Причина:** pyproject.toml включает тяжёлые ML-зависимости:

| Пакет | ~Размер | Нужен? |
|-------|---------|--------|
| sentence-transformers | 2 GB | ❌ (вызывает BGE-M3 по HTTP) |
| FlagEmbedding | 1.5 GB | ❌ (вызывает BGE-M3 по HTTP) |
| docling | 1.5 GB | ❌ (вызывает Docling по HTTP) |
| transformers | 1 GB | Частично |
| fastembed | 0.5 GB | ❌ (вызывает BM42 по HTTP) |
| mlflow/ragas/deepeval | 1 GB | ❌ (не используется в ingestion) |

**Impact:** Долгий build, больше места на диске.

**Решения:**
- [ ] Создать `pyproject.ingestion.toml` с минимальными зависимостями
- [ ] Или использовать optional deps: `[project.optional-dependencies] ingestion = [...]`
- [ ] Rebuild с slim dependencies → ожидаемый размер ~1-2 GB

---

### 5. VPS Disk — 94% Full (90/96 GB)

**Симптомы:**
```
/dev/sda1   96G   90G   6.2G  94% /
```

**Причина:** Docker images (28GB ingestion + другие) + build cache.

**Impact:** Риск "no space left on device" при следующем build.

**Решения:**
- [x] `docker builder prune -f` — освободили ~12 GB
- [x] `docker image prune -f` — очистили неиспользуемые
- [ ] Регулярный cleanup в cron
- [ ] Увеличить диск VPS (если часто)

---

### Summary Table

| Аномалия | Severity | Quick Fix | Long-term Fix |
|----------|----------|-----------|---------------|
| Swap overload | ⚠️ Medium | Reboot | More RAM / fewer services |
| 226 zombies | 🟡 Low | Reboot | Fix entrypoints + tini |
| Ingestion 90% RAM | ⚠️ Medium | Increase limit | Slim dependencies |
| 28GB image | 🟡 Low | Rebuild | Separate pyproject |
| 94% disk | 🔴 High | Prune | Bigger disk / cleanup cron |

---

# PHASE 4: Best Practices 2026 & Future Optimizations

> **Источники:** Exa MCP search + Context7 documentation (2026-02-05)

## Best Practices 2026: Что уже соответствует

| Практика | Статус | Реализация |
|----------|--------|------------|
| Hybrid retrieval (dense + sparse) | ✅ | BGE-M3 dense + BM42 sparse |
| RRF fusion | ✅ | `search_engines.py` |
| Rerank stage | ✅ | ColBERT MaxSim via BGE-M3 |
| Multi-stage builds | ✅ | Все Dockerfiles |
| Non-root containers | ✅ | `appuser:1001` |
| Memory limits | ✅ | `deploy.resources.limits` |
| LLM Gateway | ✅ | LiteLLM с fallback chain |
| Observability | ✅ | Langfuse tracing |

## Best Practices 2026: Что улучшить

### 1. Sparse слой: BM42 → BGE-M3 Lexical Weights

**Проблема:** BM42 (`all-MiniLM-L6-v2-attentions`) слабый для русского языка.

**Решение:** BGE-M3 уже умеет sparse (lexical weights) в одном проходе с dense.

**Профит:**
- Минус один сервис (vps-bm42)
- Меньше сетевых вызовов
- Лучше мультиязычность

**Как:** Изменить endpoint с `/encode/dense` на `/encode/hybrid`:
```python
# До
dense = await client.post("/encode/dense", json={"texts": texts})
sparse = await bm42_client.post("/embed_batch", json={"texts": texts})

# После
result = await client.post("/encode/hybrid", json={"texts": texts})
dense = result["dense_vecs"]
sparse = result["lexical_weights"]  # BGE-M3 sparse, не BM42
```

**Альтернатива (если нужен keyword-слой):** BM25 через FastEmbed (`Qdrant/bm25`) — проще и понятнее для русского.

### 2. LiteLLM: rc → main-stable

**Проблема:** Текущий образ `v1.81.3.rc.3` — release candidate.

**Решение:** В production использовать `main-stable` тег.

**Как:** В `docker-compose.vps.yml`:
```yaml
litellm:
  image: ghcr.io/berriai/litellm:main-stable  # Было: main-v1.81.3.rc.3
```

### 3. Rerank: Добавить Cross-Encoder

**Текущее:** ColBERT MaxSim (late interaction).

**Рекомендация 2026:** Cross-encoder на top-20/50, ColBERT как опциональный усилитель.

**Модель:** `BAAI/bge-reranker-v2-m3` — мультиязычный, trained on BGE-M3.

**Как:** Добавить endpoint в bge-m3-api:
```python
@app.post("/rerank/cross")
async def rerank_cross(query: str, documents: list[str], top_k: int = 10):
    # Cross-encoder reranking
    pass
```

### 4. Dense embeddings: A/B тест jina-embeddings-v3

**Текущее:** BGE-M3 (1024-dim, 8192 tokens).

**Конкурент:** `jina-embeddings-v3` — 8192 context, Matryoshka dims, сильный на multilingual MTEB.

**Когда:** После стабильной работы VPS, при следующем eval.

### 5. Contextual Retrieval (Anthropic)

**Идея:** К каждому чанку добавлять контекст-префикс (заголовок/раздел/doc summary).

**Профит:** Снижение "failed retrievals" на 49% (Anthropic benchmarks).

**Когда:** При следующей реиндексации.

### 6. Evals как часть пайплайна

**Текущее:** RAGAS faithfulness >= 0.8 (manual).

**Рекомендация 2026:** Langfuse → RAGAS интеграция для автоматических evals.

**Метрики:**
- Retrieval: recall@k, доля no-hit, diversity, latency
- Generation: faithfulness, groundedness, цитируемость
- End-to-end: LLM-judge + ручная валидация

---

## Task 19: Убрать BM42, использовать BGE-M3 sparse

**Priority:** High (минус сервис, лучше качество)

**Step 1: Обновить search_engines.py**

Заменить вызов BM42 API на BGE-M3 `/encode/hybrid` endpoint.

**Step 2: Обновить docker-compose.vps.yml**

Убрать `bm42` сервис или оставить как fallback.

**Step 3: Обновить коллекцию Qdrant**

Sparse vectors: `bge_m3_sparse` вместо `bm42`.

**Step 4: Реиндексация**

Запустить ingestion с новым sparse источником.

---

## Task 20: Обновить LiteLLM до main-stable

**Priority:** Medium

**Step 1: Обновить образ**
```yaml
litellm:
  image: ghcr.io/berriai/litellm:main-stable
```

**Step 2: Проверить config.yaml совместимость**

LiteLLM docs: model aliases, fallback behavior.

**Step 3: Restart и smoke test**
```bash
docker compose -f docker-compose.vps.yml pull litellm
docker compose -f docker-compose.vps.yml up -d litellm
```

---

## Task 21: Добавить Cross-Encoder Rerank

**Priority:** Medium (качество на "грязных" запросах)

**Step 1: Добавить модель в bge-m3-api**
```python
from FlagEmbedding import FlagReranker
reranker = FlagReranker("BAAI/bge-reranker-v2-m3", use_fp16=True)
```

**Step 2: Добавить endpoint**
```python
@app.post("/rerank/cross")
async def rerank_cross(request: RerankRequest):
    scores = reranker.compute_score([[request.query, doc] for doc in request.documents])
    # Sort and return top_k
```

**Step 3: Обновить pipeline**

Использовать cross-encoder на top-50, ColBERT на top-10.

---

## Task 22: Contextual Retrieval

**Priority:** Low (требует реиндексации)

**Step 1: Обновить chunker**

Добавить контекст-префикс к каждому чанку:
```python
def add_context_prefix(chunk: str, doc_title: str, section: str) -> str:
    return f"[{doc_title}] [{section}]\n{chunk}"
```

**Step 2: Обновить ingestion**

Использовать новый chunker.

**Step 3: Реиндексация**

Полная реиндексация с новыми embeddings.

---

## Roadmap Summary

| Task | Priority | Effort | Impact |
|------|----------|--------|--------|
| 19: BGE-M3 sparse | High | 1 day | -1 service, better RU |
| 20: LiteLLM stable | Medium | 1 hour | Stability |
| 21: Cross-encoder | Medium | 2 days | Quality |
| 22: Contextual retrieval | Low | 3 days | -49% failed retrievals |

---

## Quick Commands Reference

```bash
# Статус
ssh vps "docker ps --format 'table {{.Names}}\t{{.Status}}' | grep vps"

# Логи
ssh vps "docker logs vps-bot --tail 50"
ssh vps "docker logs vps-ingestion --tail 50"

# Restart сервиса
ssh vps "cd /opt/rag-fresh && docker compose -f docker-compose.vps.yml restart bot"

# Rebuild и restart
ssh vps "cd /opt/rag-fresh && docker compose -f docker-compose.vps.yml build bot && docker compose -f docker-compose.vps.yml up -d bot"

# Память
ssh vps "docker stats --no-stream | grep vps"

# Диск
ssh vps "docker system df"

# Очистка
ssh vps "docker system prune -f"
```

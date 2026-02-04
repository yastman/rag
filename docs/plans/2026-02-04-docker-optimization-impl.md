# Docker Optimization Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:tmux-swarm-orchestration for parallel execution.

**Goal:** Accelerate Docker startup from 5+ min to ≤90s for daily development via profiles + build caching.

**Architecture:** Three-tier Docker Compose profiles (core/bot/full) with BuildKit cache mounts for fast rebuilds.

**Tech Stack:** Docker Compose profiles, BuildKit cache mounts, uv package manager

---

## Execution Strategy: Parallel Workers

### Worker Topology

```
                    ┌─────────────────────────────────────┐
                    │           ORCHESTRATOR              │
                    │    (координация, не пишет код)      │
                    └─────────────────────────────────────┘
                                    │
            ┌───────────────────────┼───────────────────────┐
            │                       │                       │
            ▼                       ▼                       ▼
    ┌───────────────┐      ┌───────────────┐      ┌───────────────┐
    │   WORKER A    │      │   WORKER B    │      │   WORKER C    │
    │   Profiles    │      │   Dockerfile  │      │   Makefile    │
    │               │      │   + ignore    │      │   + Docs      │
    └───────────────┘      └───────────────┘      └───────────────┘
            │                       │                       │
            │                       │                       │
            ▼                       ▼                       ▼
    docker-compose.dev.yml   Dockerfile.ingestion      Makefile
                              .dockerignore      .claude/rules/docker.md
```

### Dependency Graph

```
M1 (Worker A: Profiles)  ─────┐
                               ├──► M4 (Orchestrator: Verification)
M2 (Worker B: Dockerfile) ────┤         │
                               │         ▼
M3 (Worker C: Makefile+Docs) ─┘    M5 (Orchestrator: Commit)
```

**Параллельно:** M1, M2, M3 (разные файлы)
**Последовательно:** M4 после M1-M3, M5 после M4

---

## Pre-flight Checklist

```bash
# 1. Verify tmux
echo $TMUX  # должен показать socket

# 2. Create logs directory
mkdir -p logs

# 3. Worktrees НЕ нужны — все воркеры работают в одном репо
#    (файлы не пересекаются)
```

---

## Milestone 1: Docker Compose Profiles (Worker A)

**Worker:** W-A
**Files:** `docker-compose.dev.yml` (exclusive)
**Dependencies:** None

### Tasks

#### M1.1: Add profiles to ML Platform services

Add `profiles: ["ml", "full"]` to:
- `clickhouse` (line ~185)
- `minio` (line ~209)
- `redis-langfuse` (line ~229)
- `langfuse-worker` (line ~243)
- `langfuse` (line ~294)
- `mlflow` (line ~322)

#### M1.2: Add profiles to Monitoring services

Add `profiles: ["obs", "full"]` to:
- `loki` (line ~355)
- `promtail` (line ~373)
- `alertmanager` (line ~393)

#### M1.3: Add profiles to Heavy AI services

Add `profiles: ["ai", "full"]` to:
- `bge-m3` (line ~73)
- `user-base` (line ~115)
- `lightrag` (line ~158)

#### M1.4: Add profiles to Bot/LiteLLM + fix dependencies

Add `profiles: ["bot", "full"]` to:
- `litellm` (line ~444)
- `bot` (line ~486)

**CRITICAL:** Remove dependencies:
- litellm: remove `langfuse` from depends_on
- bot: remove `user-base` from depends_on

#### M1.5: Add profile to Ingestion + graceful shutdown

Add to ingestion service:
```yaml
profiles: ["ingest", "full"]
stop_grace_period: 30s
```

#### M1.6: Verify core services (5 total)

```bash
docker compose -f docker-compose.dev.yml config --services
# Expected: postgres, redis, qdrant, docling, bm42
```

### Worker A Spawn Command

```bash
tmux new-window -n "W-A" -c /home/user/projects/rag-fresh
tmux send-keys -t "W-A" "claude --dangerously-skip-permissions 'W-A: Docker Compose Profiles.

ПЛАН: docs/plans/2026-02-04-docker-optimization-impl.md
ЗАДАЧИ: Milestone 1 (M1.1 - M1.6)

ФАЙЛЫ (exclusive):
- docker-compose.dev.yml

ИНСТРУКЦИИ:
1. Добавь profiles ко всем сервисам согласно плану
2. УБЕРИ зависимости: litellm→langfuse, bot→user-base
3. Добавь stop_grace_period: 30s к ingestion
4. Проверь что core = 5 сервисов без profile

ВЕРИФИКАЦИЯ после каждого шага:
docker compose -f docker-compose.dev.yml config --services | wc -l
docker compose -f docker-compose.dev.yml --profile full config --services | wc -l

ЛОГИРОВАНИЕ в /home/user/projects/rag-fresh/logs/worker-a.log:
[START] timestamp Task
[DONE] timestamp Task
[COMPLETE] timestamp Worker finished

НЕ делай git commit.'" Enter
```

---

## Milestone 2: Dockerfile + .dockerignore (Worker B)

**Worker:** W-B
**Files:** `Dockerfile.ingestion`, `.dockerignore` (exclusive)
**Dependencies:** None

### Tasks

#### M2.1: Rewrite Dockerfile.ingestion with BuildKit cache mounts

Replace entire file with:

```dockerfile
# syntax=docker/dockerfile:1.4
# Unified Ingestion Pipeline Dockerfile
# Multi-stage build with BuildKit cache mounts for fast rebuilds

# =============================================================================
# Build stage: Install uv and dependencies
# =============================================================================
FROM python:3.12-slim AS builder

WORKDIR /app

# Enable APT cache persistence
RUN rm -f /etc/apt/apt.conf.d/docker-clean; \
    echo 'Binary::apt::APT::Keep-Downloaded-Packages "true";' \
    > /etc/apt/apt.conf.d/keep-cache

# Install system dependencies with cache mount
RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt,sharing=locked \
    apt-get update && apt-get install -y --no-install-recommends \
    curl \
    gcc \
    g++

# Copy uv from official image (pinned version)
COPY --from=ghcr.io/astral-sh/uv:0.5.18 /uv /usr/local/bin/uv

# Enable bytecode compilation for faster startup
ENV UV_COMPILE_BYTECODE=1
ENV UV_LINK_MODE=copy

# Install dependencies with cache mount (deps change rarely)
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    uv sync --frozen --no-dev --no-install-project

# Copy dependency files for final sync
COPY pyproject.toml uv.lock ./

# Copy application code (changes often - separate layer)
COPY src/ ./src/
COPY telegram_bot/ ./telegram_bot/

# Final sync with project installation
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev

# =============================================================================
# Runtime stage: Minimal image with application
# =============================================================================
FROM python:3.12-slim AS runtime

WORKDIR /app

# Install runtime dependencies (procps for healthcheck)
RUN apt-get update && apt-get install -y --no-install-recommends \
    procps \
    && rm -rf /var/lib/apt/lists/*

# Copy uv binary (pinned version)
COPY --from=ghcr.io/astral-sh/uv:0.5.18 /uv /usr/local/bin/uv

# Copy virtual environment from builder
COPY --from=builder /app/.venv /app/.venv

# Copy dependency files (needed for uv run)
COPY pyproject.toml uv.lock ./

# Copy application code
COPY src/ ./src/
COPY telegram_bot/ ./telegram_bot/

# Create non-root user
RUN useradd -m -u 1000 ingestion && \
    chown -R ingestion:ingestion /app

USER ingestion

# Ensure uv uses the existing venv
ENV UV_PROJECT_ENVIRONMENT=/app/.venv
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD pgrep -f "src.ingestion.unified.cli" || exit 1

# Graceful shutdown
STOPSIGNAL SIGTERM

# Default command
ENTRYPOINT ["uv", "run", "python", "-m", "src.ingestion.unified.cli"]
CMD ["run", "--watch"]
```

#### M2.2: Update .dockerignore

Add to end of file:

```
# Worktrees (Claude Code)
.worktrees/

# Ruff cache
.ruff_cache/

# Claude settings
.claude/

# Scripts (not needed in container)
scripts/

# Docker configs (not needed in image)
docker/

# Services (separate builds)
services/
```

#### M2.3: Verify Dockerfile syntax

```bash
docker build -f Dockerfile.ingestion --check .
```

### Worker B Spawn Command

```bash
tmux new-window -n "W-B" -c /home/user/projects/rag-fresh
tmux send-keys -t "W-B" "claude --dangerously-skip-permissions 'W-B: Dockerfile + .dockerignore.

ПЛАН: docs/plans/2026-02-04-docker-optimization-impl.md
ЗАДАЧИ: Milestone 2 (M2.1 - M2.3)

ФАЙЛЫ (exclusive):
- Dockerfile.ingestion
- .dockerignore

ИНСТРУКЦИИ:
1. Перепиши Dockerfile.ingestion с BuildKit cache mounts
2. Добавь записи в .dockerignore
3. Проверь синтаксис: docker build -f Dockerfile.ingestion --check .

⚠️ BEST PRACTICES 2026:
- syntax=docker/dockerfile:1.4 в начале
- --mount=type=cache для apt и uv
- Pin uv version: ghcr.io/astral-sh/uv:0.5.18
- UV_COMPILE_BYTECODE=1 для быстрого старта

ЛОГИРОВАНИЕ в /home/user/projects/rag-fresh/logs/worker-b.log:
[START] timestamp Task
[DONE] timestamp Task
[COMPLETE] timestamp Worker finished

НЕ делай git commit.'" Enter
```

---

## Milestone 3: Makefile + Documentation (Worker C)

**Worker:** W-C
**Files:** `Makefile`, `.claude/rules/docker.md` (exclusive)
**Dependencies:** None

### Tasks

#### M3.1: Add Docker profile targets to Makefile

Replace section starting with `docker-up:` (line ~284) with:

```makefile
# =============================================================================
# DOCKER PROFILES
# =============================================================================

.PHONY: docker-core-up docker-bot-up docker-obs-up docker-ml-up docker-ai-up docker-ingest-up docker-full-up docker-down docker-ps

docker-core-up: ## Start core services (postgres, qdrant, redis, docling, bm42)
	@echo "$(BLUE)Starting core services...$(NC)"
	docker compose -f docker-compose.dev.yml up -d
	@echo "$(GREEN)✓ Core services started$(NC)"

docker-bot-up: ## Start core + bot services (litellm, bot)
	@echo "$(BLUE)Starting bot services...$(NC)"
	docker compose -f docker-compose.dev.yml --profile bot up -d
	@echo "$(GREEN)✓ Bot services started$(NC)"

docker-obs-up: ## Start core + observability (loki, promtail, alertmanager)
	@echo "$(BLUE)Starting observability services...$(NC)"
	docker compose -f docker-compose.dev.yml --profile obs up -d
	@echo "$(GREEN)✓ Observability services started$(NC)"

docker-ml-up: ## Start core + ML platform (langfuse, mlflow, clickhouse, minio)
	@echo "$(BLUE)Starting ML platform services...$(NC)"
	docker compose -f docker-compose.dev.yml --profile ml up -d
	@echo "$(GREEN)✓ ML platform started$(NC)"

docker-ai-up: ## Start core + heavy AI services (bge-m3, user-base, lightrag)
	@echo "$(BLUE)Starting AI services...$(NC)"
	docker compose -f docker-compose.dev.yml --profile ai up -d
	@echo "$(GREEN)✓ AI services started$(NC)"

docker-ingest-up: ## Start core + ingestion service
	@echo "$(BLUE)Starting ingestion service...$(NC)"
	docker compose -f docker-compose.dev.yml --profile ingest up -d
	@echo "$(GREEN)✓ Ingestion service started$(NC)"

docker-full-up: ## Start all services (full stack)
	@echo "$(BLUE)Starting full stack...$(NC)"
	docker compose -f docker-compose.dev.yml --profile full up -d
	@echo "$(GREEN)✓ Full stack started$(NC)"

docker-up: docker-core-up ## Alias for docker-core-up (backward compat)

docker-down: ## Stop all Docker services
	@echo "$(BLUE)Stopping Docker services...$(NC)"
	docker compose -f docker-compose.dev.yml --profile full down
	@echo "$(GREEN)✓ Services stopped$(NC)"

docker-ps: ## Show Docker service status
	@echo "$(BLUE)Docker service status:$(NC)"
	@docker compose -f docker-compose.dev.yml --profile full ps --format "table {{.Name}}\t{{.Status}}\t{{.Ports}}"
```

#### M3.2: Update monitoring-up and monitoring-down

Replace monitoring-up (line ~517):
```makefile
monitoring-up: ## Start monitoring stack (Loki, Promtail, Alertmanager)
	@echo "$(BLUE)Starting monitoring stack...$(NC)"
	docker compose -f docker-compose.dev.yml --profile obs up -d
	@echo "$(GREEN)✓ Monitoring stack started$(NC)"
	@echo "$(YELLOW)Services:$(NC)"
	@echo "  Loki:         http://localhost:3100"
	@echo "  Alertmanager: http://localhost:9093"
```

Replace monitoring-down (line ~527):
```makefile
monitoring-down: ## Stop monitoring stack
	@echo "$(BLUE)Stopping monitoring stack...$(NC)"
	docker compose -f docker-compose.dev.yml --profile obs stop
	@echo "$(GREEN)✓ Monitoring stack stopped$(NC)"
```

#### M3.3: Update .claude/rules/docker.md

Add after "Full Stack (16 containers)" section:

```markdown
## Docker Profiles (Fast Startup)

| Command | Services | Use Case |
|---------|----------|----------|
| `make docker-core-up` | postgres, qdrant, redis, docling, bm42 | Daily ingestion dev |
| `make docker-bot-up` | core + litellm, bot | Bot development |
| `make docker-obs-up` | core + loki, promtail, alertmanager | Debug logging |
| `make docker-ml-up` | core + langfuse stack, mlflow | ML experiments |
| `make docker-ai-up` | core + bge-m3, user-base, lightrag | Heavy AI models |
| `make docker-ingest-up` | core + ingestion | Ingestion container |
| `make docker-full-up` | everything (16+ services) | Full stack |

### Combining Profiles

```bash
# Bot + observability
docker compose -f docker-compose.dev.yml --profile bot --profile obs up -d

# Using COMPOSE_PROFILES env var
COMPOSE_PROFILES=bot,obs docker compose -f docker-compose.dev.yml up -d
```

### Startup Times (warm images)

| Profile | Services | Target Time |
|---------|----------|-------------|
| core | 5 | ≤90s |
| bot | 7 | ≤2-3 min |
| full | 16+ | ≤5 min |
```

#### M3.4: Verify Makefile

```bash
make help | grep docker
```

### Worker C Spawn Command

```bash
tmux new-window -n "W-C" -c /home/user/projects/rag-fresh
tmux send-keys -t "W-C" "claude --dangerously-skip-permissions 'W-C: Makefile + Documentation.

ПЛАН: docs/plans/2026-02-04-docker-optimization-impl.md
ЗАДАЧИ: Milestone 3 (M3.1 - M3.4)

ФАЙЛЫ (exclusive):
- Makefile
- .claude/rules/docker.md

ИНСТРУКЦИИ:
1. Добавь новые docker-* targets в Makefile
2. Обнови monitoring-up/down для использования --profile obs
3. Добавь секцию Docker Profiles в docker.md
4. Проверь: make help | grep docker

ЛОГИРОВАНИЕ в /home/user/projects/rag-fresh/logs/worker-c.log:
[START] timestamp Task
[DONE] timestamp Task
[COMPLETE] timestamp Worker finished

НЕ делай git commit.'" Enter
```

---

## Milestone 4: Verification (Orchestrator)

**Executor:** Orchestrator
**Dependencies:** M1, M2, M3 complete

### Tasks

#### M4.1: Verify core profile (5 services)

```bash
docker compose -f docker-compose.dev.yml config --services
# Expected: postgres, redis, qdrant, docling, bm42
```

#### M4.2: Verify full profile (16+ services)

```bash
docker compose -f docker-compose.dev.yml --profile full config --services | wc -l
# Expected: 16 or more
```

#### M4.3: Test core startup time

```bash
docker compose -f docker-compose.dev.yml --profile full down
time docker compose -f docker-compose.dev.yml up -d --wait
# Target: ≤90s
```

#### M4.4: Test bot profile without langfuse

```bash
docker compose -f docker-compose.dev.yml --profile bot up -d
docker logs dev-litellm 2>&1 | head -10
# Should start without langfuse error
```

#### M4.5: Test Dockerfile cache

```bash
DOCKER_BUILDKIT=1 docker build -f Dockerfile.ingestion -t test:v1 .
touch src/ingestion/unified/cli.py
time DOCKER_BUILDKIT=1 docker build -f Dockerfile.ingestion -t test:v2 .
# Should show CACHED and take <30s
```

#### M4.6: Verify Makefile

```bash
make help | grep docker
make docker-ps
```

---

## Milestone 5: Commit (Orchestrator)

**Executor:** Orchestrator
**Dependencies:** M4 complete

### Tasks

#### M5.1: Stage all changes

```bash
git add docker-compose.dev.yml Dockerfile.ingestion .dockerignore Makefile .claude/rules/docker.md
```

#### M5.2: Commit

```bash
git commit -m "feat(docker): add profiles for fast startup + BuildKit cache

- Add Docker Compose profiles: core (default), bot, obs, ml, ai, ingest, full
- Break bot → langfuse dependency chain (langfuse now optional)
- Add BuildKit cache mounts to Dockerfile.ingestion for 10x faster rebuilds
- Add Makefile targets: docker-core-up, docker-bot-up, docker-full-up, etc.
- Add graceful shutdown (SIGTERM + stop_grace_period)
- Update .dockerignore to exclude .worktrees, .claude, scripts

Core startup target: ≤90s (down from 5+ min)

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Auto-Monitor Setup

Create/update `scripts/monitor-workers.sh`:

```bash
#!/bin/bash
# Worker completion monitor for Docker optimization

declare -A WINDOW_MAP=(
    ["worker-a"]="W-A"
    ["worker-b"]="W-B"
    ["worker-c"]="W-C"
)

echo "[$(date)] Monitor started for workers: ${!WINDOW_MAP[*]}"

while true; do
    all_complete=true
    for worker in "${!WINDOW_MAP[@]}"; do
        log_file="logs/${worker}.log"
        window="${WINDOW_MAP[$worker]}"

        if grep -q '\[COMPLETE\]' "$log_file" 2>/dev/null; then
            echo "[$(date)] $worker COMPLETE, killing window $window"
            tmux kill-window -t "$window" 2>/dev/null
            unset "WINDOW_MAP[$worker]"
        else
            all_complete=false
        fi
    done

    if [ ${#WINDOW_MAP[@]} -eq 0 ]; then
        echo "[$(date)] All workers complete!"
        break
    fi

    sleep 30
done
```

---

## Quick Start Commands

```bash
# 1. Setup
mkdir -p logs
echo $TMUX  # verify in tmux

# 2. Spawn workers (copy-paste each block)
# Worker A
tmux new-window -n "W-A" -c /home/user/projects/rag-fresh
tmux send-keys -t "W-A" "claude --dangerously-skip-permissions 'W-A: Docker Compose Profiles. ПЛАН: docs/plans/2026-02-04-docker-optimization-impl.md ЗАДАЧИ: M1.1-M1.6. ФАЙЛЫ: docker-compose.dev.yml. ЛОГИРОВАНИЕ: /home/user/projects/rag-fresh/logs/worker-a.log. НЕ делай git commit.'" Enter

# Worker B
tmux new-window -n "W-B" -c /home/user/projects/rag-fresh
tmux send-keys -t "W-B" "claude --dangerously-skip-permissions 'W-B: Dockerfile + .dockerignore. ПЛАН: docs/plans/2026-02-04-docker-optimization-impl.md ЗАДАЧИ: M2.1-M2.3. ФАЙЛЫ: Dockerfile.ingestion, .dockerignore. ЛОГИРОВАНИЕ: /home/user/projects/rag-fresh/logs/worker-b.log. НЕ делай git commit.'" Enter

# Worker C
tmux new-window -n "W-C" -c /home/user/projects/rag-fresh
tmux send-keys -t "W-C" "claude --dangerously-skip-permissions 'W-C: Makefile + Documentation. ПЛАН: docs/plans/2026-02-04-docker-optimization-impl.md ЗАДАЧИ: M3.1-M3.4. ФАЙЛЫ: Makefile, .claude/rules/docker.md. ЛОГИРОВАНИЕ: /home/user/projects/rag-fresh/logs/worker-c.log. НЕ делай git commit.'" Enter

# 3. Start monitor
nohup ./scripts/monitor-workers.sh > logs/monitor.log 2>&1 &

# 4. Check progress
tail -f logs/worker-*.log

# 5. After all [COMPLETE]: run M4 + M5 manually
```

---

## Summary

| Milestone | Worker | Files | Dependencies |
|-----------|--------|-------|--------------|
| M1 | W-A | docker-compose.dev.yml | None |
| M2 | W-B | Dockerfile.ingestion, .dockerignore | None |
| M3 | W-C | Makefile, .claude/rules/docker.md | None |
| M4 | Orchestrator | (verification) | M1, M2, M3 |
| M5 | Orchestrator | (commit) | M4 |

**Parallel:** M1, M2, M3
**Sequential:** M4 → M5

## Verification Checklist

- [ ] All workers show [COMPLETE] in logs
- [ ] `docker compose config --services` shows 5 core services
- [ ] `make help | grep docker` shows all new targets
- [ ] Core startup ≤90s
- [ ] Dockerfile rebuild <30s with cache
- [ ] Commit includes all 5 files

# Design: Docker Container Optimization

**Date:** 2026-02-04
**Status:** Draft
**Owner:** Claude
**Based on:** Research from Exa MCP (best practices 2026)

## Executive Summary

Оптимизация Docker стека для ускорения startup time и улучшения developer experience. Текущий стек из 16+ контейнеров стартует слишком долго для daily development.

## Current State Analysis

### Services Inventory (docker-compose.dev.yml)

| Category | Services | Startup Impact |
|----------|----------|----------------|
| **Core DB** | postgres, redis, qdrant | Fast (10-30s) |
| **AI Services** | bge-m3, bm42, docling, user-base, lightrag | Slow (60-120s warmup) |
| **ML Platform** | clickhouse, minio, redis-langfuse, langfuse-worker, langfuse, mlflow | Medium (30-60s) |
| **Monitoring** | loki, promtail, alertmanager | Fast (10-20s) |
| **App** | litellm, bot, ingestion | Depends on above |

### Current Problems

1. **All-or-nothing startup** — `docker compose up` starts everything
2. **Heavy dependency chains** — bot → litellm → langfuse → clickhouse/minio
3. **No build caching** — Dockerfile.ingestion doesn't use cache mounts
4. **Weak healthchecks** — ingestion uses `pgrep` (process alive ≠ service ready)
5. **No profiles** — can't start subset of services easily

## Proposed Solution

### Architecture: Three-Tier Profiles

```
┌─────────────────────────────────────────────────────────────────┐
│                         FULL STACK                               │
│  (--profile full)                                                │
│                                                                  │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │                    BOT STACK                             │    │
│  │  (--profile bot)                                         │    │
│  │                                                          │    │
│  │  ┌─────────────────────────────────────────────────┐    │    │
│  │  │              CORE STACK (default)                │    │    │
│  │  │                                                  │    │    │
│  │  │  postgres, qdrant, redis, docling, bm42         │    │    │
│  │  │                                                  │    │    │
│  │  └─────────────────────────────────────────────────┘    │    │
│  │                                                          │    │
│  │  + bot, litellm                                          │    │
│  │                                                          │    │
│  └─────────────────────────────────────────────────────────┘    │
│                                                                  │
│  + langfuse stack, mlflow, monitoring, bge-m3, user-base,       │
│    lightrag, ingestion                                           │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

### Profile Definitions

| Profile | Services | Use Case | Target Startup |
|---------|----------|----------|----------------|
| **(none)** core | postgres, qdrant, redis, docling, bm42 | Daily ingestion dev | ≤90s |
| **bot** | core + bot, litellm | Bot development | ≤2-3 min |
| **obs** | core + loki, promtail, alertmanager | Debug logging | ≤2 min |
| **ml** | core + langfuse stack, mlflow | ML experiments | ≤3 min |
| **full** | everything | Production-like | ≤5 min |

### Service Profile Assignment

```yaml
# CORE (no profile = always starts)
postgres:      # no profile
qdrant:        # no profile
redis:         # no profile
docling:       # no profile
bm42:          # no profile

# BOT
bot:           profiles: [bot, full]
litellm:       profiles: [bot, full]

# OBSERVABILITY
loki:          profiles: [obs, full]
promtail:      profiles: [obs, full]
alertmanager:  profiles: [obs, full]

# ML PLATFORM
clickhouse:    profiles: [ml, full]
minio:         profiles: [ml, full]
redis-langfuse: profiles: [ml, full]
langfuse-worker: profiles: [ml, full]
langfuse:      profiles: [ml, full]
mlflow:        profiles: [ml, full]

# HEAVY AI (rarely needed locally)
bge-m3:        profiles: [ai, full]
user-base:     profiles: [ai, full]
lightrag:      profiles: [ai, full]

# INGESTION (optional, can run locally)
ingestion:     profiles: [ingest, full]
```

## Implementation Plan

### P0: Profiles + Dependency Cleanup (Critical)

#### P0.1: Add profiles to docker-compose.dev.yml

**Files:** `docker-compose.dev.yml`

```yaml
services:
  # Core services - NO profile (always start)
  postgres:
    # ... existing config ...
    # NO profiles: line

  # Bot services - bot profile
  bot:
    profiles: ["bot", "full"]
    depends_on:
      redis:
        condition: service_healthy
      qdrant:
        condition: service_healthy
      bm42:
        condition: service_healthy
      # REMOVE: user-base, litellm (make optional)
```

#### P0.2: Break bot → langfuse dependency

**Current:** bot → litellm → langfuse → clickhouse/minio
**Target:** bot → litellm (langfuse optional via env flag)

```yaml
litellm:
  profiles: ["bot", "full"]
  depends_on:
    postgres:
      condition: service_healthy
    # REMOVE: langfuse dependency
  environment:
    # Gate Langfuse behind env var
    LANGFUSE_PUBLIC_KEY: ${LANGFUSE_PUBLIC_KEY:-}
    LANGFUSE_SECRET_KEY: ${LANGFUSE_SECRET_KEY:-}
    # Empty = disabled
```

#### P0.3: Makefile targets

**File:** `Makefile`

```makefile
# Docker Profiles
docker-core-up:
	docker compose -f docker-compose.dev.yml up -d

docker-bot-up:
	docker compose -f docker-compose.dev.yml --profile bot up -d

docker-obs-up:
	docker compose -f docker-compose.dev.yml --profile obs up -d

docker-ml-up:
	docker compose -f docker-compose.dev.yml --profile ml up -d

docker-full-up:
	docker compose -f docker-compose.dev.yml --profile full up -d

docker-down:
	docker compose -f docker-compose.dev.yml --profile full down
```

### P1: Build Optimization (High Value)

#### P1.1: Dockerfile.ingestion with cache mounts

**File:** `Dockerfile.ingestion`

```dockerfile
# syntax=docker/dockerfile:1.4
FROM python:3.12-slim AS builder

WORKDIR /app

# APT cache mount
RUN rm -f /etc/apt/apt.conf.d/docker-clean; \
    echo 'Binary::apt::APT::Keep-Downloaded-Packages "true";' \
    > /etc/apt/apt.conf.d/keep-cache

RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt,sharing=locked \
    apt-get update && apt-get install -y --no-install-recommends \
    curl gcc g++

# Pin uv version
COPY --from=ghcr.io/astral-sh/uv:0.5.18 /uv /usr/local/bin/uv

# UV cache mount + bind mounts for deps
ENV UV_COMPILE_BYTECODE=1
ENV UV_LINK_MODE=copy

RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    uv sync --frozen --no-dev --no-install-project

# Copy code separately (cache-friendly)
COPY src/ ./src/
COPY telegram_bot/ ./telegram_bot/
COPY pyproject.toml uv.lock ./

RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev

# --- Runtime stage ---
FROM python:3.12-slim AS runtime
# ... rest unchanged ...
```

#### P1.2: Enable BuildKit in docker-compose

**File:** `docker-compose.dev.yml` (top-level)

```yaml
# Recommended: DOCKER_BUILDKIT=1 in environment
# Or use: docker compose build --progress=plain

services:
  ingestion:
    build:
      context: .
      dockerfile: Dockerfile.ingestion
      # Enable inline cache for CI
      cache_from:
        - type=registry,ref=ghcr.io/user/rag-fresh/ingestion:cache
```

### P2: Healthcheck Improvements (Medium Value)

#### P2.1: Ingestion healthcheck via marker file

**Problem:** `pgrep` only checks process exists, not service health.

**Solution:** CLI writes timestamp to `/tmp/healthy`, healthcheck verifies recency.

**File:** `src/ingestion/unified/cli.py` (add to main loop)

```python
# In watch loop, after each successful cycle:
Path("/tmp/healthy").write_text(str(time.time()))
```

**File:** `Dockerfile.ingestion`

```dockerfile
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD [ -f /tmp/healthy ] && \
        [ $(( $(date +%s) - $(cut -d. -f1 /tmp/healthy) )) -lt 120 ] || exit 1
```

#### P2.2: Add HTTP health endpoint (alternative)

If ingestion becomes a long-running service, add FastAPI health endpoint:

```python
# Optional: HTTP health server on separate thread
# GET /health → {"status": "ok", "last_run": "2026-02-04T12:00:00Z"}
```

### P3: Resource & Runtime Optimization (Nice to Have)

#### P3.1: Graceful shutdown

**File:** `Dockerfile.ingestion`

```dockerfile
STOPSIGNAL SIGTERM
```

**File:** `docker-compose.dev.yml`

```yaml
ingestion:
  stop_grace_period: 30s
```

#### P3.2: Logging limits (already present, verify)

```yaml
logging:
  driver: "json-file"
  options:
    max-size: "10m"
    max-file: "3"
```

#### P3.3: .dockerignore

**File:** `.dockerignore`

```
.git
.github
.venv
__pycache__
*.pyc
*.pyo
.pytest_cache
.mypy_cache
.ruff_cache
*.egg-info
dist
build
.env*
docs/
tests/
*.md
!README.md
.worktrees/
```

### P4: Future Considerations (Out of Scope)

- **Distroless images** — smaller attack surface, but debugging harder
- **docker-slim** — auto-minification (1GB → 40MB possible)
- **Multi-platform builds** — linux/amd64 + linux/arm64
- **Registry caching** — for CI/CD pipelines

## Acceptance Criteria

### P0 Complete When:
- [ ] `docker compose -f docker-compose.dev.yml up -d` starts only core (5 services)
- [ ] `docker compose --profile bot up -d` starts core + bot + litellm
- [ ] Bot starts without langfuse running
- [ ] Core stack healthy in ≤90s on warm images

### P1 Complete When:
- [ ] `docker compose build ingestion` uses cache (no full reinstall on code change)
- [ ] Second build of ingestion takes <30s (vs 2-3 min without cache)

### P2 Complete When:
- [ ] Ingestion healthcheck fails if service hangs (not just process alive)
- [ ] Healthcheck passes only when last successful run was <2 min ago

## Rollout Plan

```
Phase 1 (P0): Profiles
├── Add profiles to services
├── Break langfuse dependency
├── Add Makefile targets
└── Test: core, bot, full modes

Phase 2 (P1): Build caching
├── Update Dockerfile.ingestion
├── Add .dockerignore
└── Verify cache works

Phase 3 (P2): Healthchecks
├── Add marker file to CLI
├── Update healthcheck command
└── Test failure scenarios

Phase 4 (P3): Polish
├── Graceful shutdown
├── Verify logging limits
└── Documentation
```

## Commands Reference

```bash
# Daily development (ingestion)
make docker-core-up              # postgres, qdrant, redis, docling, bm42

# Bot development
make docker-bot-up               # core + bot + litellm

# With observability
docker compose --profile bot --profile obs up -d

# ML experiments
make docker-ml-up                # core + langfuse stack + mlflow

# Full stack
make docker-full-up              # everything

# Status
docker compose ps
docker compose --profile full ps

# Logs
docker compose logs -f ingestion
docker compose --profile bot logs -f

# Cleanup
make docker-down                 # stops all profiles
```

## Risks & Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| Breaking existing workflows | High | Test all `make docker-*` commands |
| Bot fails without langfuse | Medium | Gate tracing behind env var |
| Cache mount not working | Low | Fallback to current behavior |
| Healthcheck too strict | Medium | Tune intervals, add start_period |

## References

- [Docker Compose Profiles](https://docs.docker.com/compose/profiles/)
- [BuildKit Cache Mounts](https://docs.docker.com/build/cache/)
- [uv Docker Integration](https://docs.astral.sh/uv/guides/integration/docker/)
- [Docker Best Practices 2026](https://oneuptime.com/blog/post/2026-01-16-docker-optimize-build-times/view)

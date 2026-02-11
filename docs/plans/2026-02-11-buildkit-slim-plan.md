# BuildKit Cache Mounts + Slim Docker Images — Implementation Plan

**Issue:** #72 (infra: BuildKit cache mounts + slim Docker images)
**Milestone:** Stream-F: Infra-Sec
**Status:** Draft
**Date:** 2026-02-11

## Goal

Ускорить Docker builds через docker-bake.hcl (параллельные сборки), уменьшить размеры образов,
настроить HDD layout на VPS для кэшей и бэкапов.

## Текущее состояние

### Уже сделано (Phase 0 — из uv-docker-migration)

- BuildKit cache mounts (`--mount=type=cache`) — ВСЕ Dockerfile уже используют ✅
- Multi-stage builds (builder → runtime) — ВСЕ Dockerfile ✅
- `uv sync --frozen --no-dev` паттерн — ВСЕ кастомные сервисы ✅
- Non-root users — ВСЕ Dockerfile ✅
- LiteLLM версии dev/VPS — выровнены на `main-v1.81.3-stable` ✅

### Размеры образов (текущие)

| Image | Size | Base | Notes |
|-------|------|------|-------|
| bot | 1.19 GB | python:3.12-slim-bookworm | telegram_bot deps |
| bge-m3 | 2.35 GB | python:3.12-slim-bookworm | sentence-transformers, torch |
| user-base | 1.87 GB | python:3.12-slim-bookworm | sentence-transformers, torch |
| docling | 3.55 GB | python:3.12-slim-bookworm | torch CPU + docling-serve |
| ingestion | 3.77 GB | python:3.12-slim-bookworm | src/ + telegram_bot/ + CocoIndex |
| mlflow | 1.70 GB | ghcr.io/mlflow/mlflow:v3.9.0 | + psycopg2-binary |
| **Total** | **~14.4 GB** | | 6 custom images |

### Build Tool

- Нет `docker-bake.hcl` — сборка последовательная через `docker compose build`
- Нет параллельных build targets

## Шаги реализации

### Step 1: Создать docker-bake.hcl (5 мин)

**Файл:** `docker-bake.hcl` (новый, корень проекта)

**Цель:** Параллельные builds всех custom images через `docker buildx bake`

**Содержимое:**

    group "default" {
      targets = ["bot", "bge-m3", "user-base", "docling", "ingestion", "mlflow"]
    }

    group "core" {
      targets = ["bge-m3", "user-base", "docling"]
    }

    group "app" {
      targets = ["bot", "ingestion"]
    }

    target "bot" {
      context    = "."
      dockerfile = "telegram_bot/Dockerfile"
      tags       = ["rag-fresh-bot:latest"]
    }

    target "bge-m3" {
      context    = "./services/bge-m3-api"
      dockerfile = "Dockerfile"
      tags       = ["rag-fresh-bge-m3:latest"]
    }

    target "user-base" {
      context    = "./services/user-base"
      dockerfile = "Dockerfile"
      tags       = ["rag-fresh-user-base:latest"]
    }

    target "docling" {
      context    = "./services/docling"
      dockerfile = "Dockerfile"
      tags       = ["rag-fresh-docling:latest"]
    }

    target "ingestion" {
      context    = "."
      dockerfile = "Dockerfile.ingestion"
      tags       = ["rag-fresh-ingestion:latest"]
    }

    target "mlflow" {
      context    = "./docker/mlflow"
      dockerfile = "Dockerfile"
      tags       = ["rag-fresh-mlflow:latest"]
    }

**ВАЖНО:** Теги должны совпадать с `docker compose` (prefix `rag-fresh-`).
Проверить: `docker compose -f docker-compose.dev.yml config | grep image:`

**Команды после:**

    docker buildx bake --load        # Все 6 образов параллельно
    docker buildx bake core --load   # Только ML сервисы
    docker buildx bake app --load    # Только bot + ingestion

### Step 2: Добавить Makefile targets (3 мин)

**Файл:** `Makefile` — добавить секцию Docker Bake

**Добавить таргеты:**

    # Docker Bake (parallel builds)
    docker-bake:
        docker buildx bake --load

    docker-bake-core:
        docker buildx bake core --load

    docker-bake-app:
        docker buildx bake app --load

**Проверить:** существующие `docker-*` таргеты в Makefile, не дублировать.

### Step 3: Slim ingestion image — удалить uv из runtime (3 мин)

**Файл:** `Dockerfile.ingestion`, строки 59-60, 72, 81

**Проблема:** Runtime копирует uv binary (75 MB) и использует `uv run` в ENTRYPOINT.
Это не нужно — можно запускать через venv напрямую.

**Изменения:**

1. **Удалить строку 60:**

        COPY --from=ghcr.io/astral-sh/uv:0.10 /uv /usr/local/bin/uv

2. **Удалить строку 72:**

        ENV UV_PROJECT_ENVIRONMENT=/app/.venv

3. **Добавить PATH к .venv (строка 72, заменить):**

        ENV PATH="/app/.venv/bin:$PATH" \
            PYTHONUNBUFFERED=1 \
            PYTHONDONTWRITEBYTECODE=1

4. **Изменить ENTRYPOINT (строка 81):**

        # Было:
        ENTRYPOINT ["uv", "run", "python", "-m", "src.ingestion.unified.cli"]
        # Стало:
        ENTRYPOINT ["python", "-m", "src.ingestion.unified.cli"]

**Экономия:** ~75 MB (uv binary)

### Step 4: Slim ingestion — .dockerignore оптимизация (3 мин)

**Файл:** `.dockerignore` (проверить/обновить)

**Проблема:** ingestion и bot используют `context: .` — весь проект копируется.
Нужно исключить ненужное.

**Добавить в .dockerignore (если нет):**

    # Dev/test artifacts
    .venv/
    .git/
    .github/
    .claude/
    __pycache__/
    *.pyc
    .mypy_cache/
    .ruff_cache/
    .pytest_cache/
    node_modules/
    logs/
    data/
    docs/
    tests/
    *.md
    !pyproject.toml
    !uv.lock

    # Large dirs not needed in containers
    .worktrees/
    notebooks/
    scripts/
    services/
    docker/
    k8s/

**ВНИМАНИЕ:** bot Dockerfile (`context: .`) копирует `telegram_bot/`.
Ingestion Dockerfile (`context: .`) копирует `src/` и `telegram_bot/`.
Нельзя исключить `telegram_bot/` и `src/` — они нужны обоим.
Но `services/`, `docker/`, `docs/`, `tests/` можно исключить.

**Проверить:** текущий `.dockerignore` — не ломает ли существующие builds.

### Step 5: VPS HDD 3TB layout (5 мин)

**Файл:** `docs/VPS-HDD-LAYOUT.md` (новый) — документация

**Структура:**

    /mnt/hdd/                          # 3TB HDD
    ├── docker-cache/                  # Docker BuildKit cache
    │   └── buildkit/                  # --cache-from/--cache-to
    ├── hf-models/                     # HuggingFace model cache
    │   ├── hf/                        # HF_HOME
    │   └── sentence-transformers/     # SENTENCE_TRANSFORMERS_HOME
    └── backups/                       # Volume backups
        ├── postgres/
        ├── qdrant/
        └── redis/

**Изменения в docker-compose.vps.yml:**

1. **bge-m3 и user-base** — заменить named volume `hf_cache` на bind mount:

        volumes:
          - /mnt/hdd/hf-models:/models

2. **Добавить BuildKit cache config** (daemon.json на VPS):

        {
          "builder": {
            "gc": { "defaultKeepStorage": "10GB" },
            "entitlements": ["network.host"]
          },
          "data-root": "/var/lib/docker",
          "storage-driver": "overlay2"
        }

3. **Backup cron** — добавить скрипт `scripts/vps-backup.sh`:

        #!/bin/bash
        # Daily backup of critical volumes to HDD
        docker run --rm -v vps_postgres_data:/data -v /mnt/hdd/backups/postgres:/backup \
          alpine tar czf /backup/postgres-$(date +%Y%m%d).tar.gz -C /data .

**NOTE:** Этот шаг выполняется на VPS вручную, не в CI.

### Step 6: docker-bake.hcl — cache-from/cache-to для CI (5 мин)

**Файл:** `docker-bake.hcl` — добавить cache config

**Добавить к каждому target:**

    target "bot" {
      context    = "."
      dockerfile = "telegram_bot/Dockerfile"
      tags       = ["rag-fresh-bot:latest"]
      cache-from = ["type=local,src=/tmp/.buildx-cache/bot"]
      cache-to   = ["type=local,dest=/tmp/.buildx-cache-new/bot,mode=max"]
    }

**Для VPS с HDD:**

    target "bot" {
      ...
      cache-from = ["type=local,src=/mnt/hdd/docker-cache/bot"]
      cache-to   = ["type=local,dest=/mnt/hdd/docker-cache/bot,mode=max"]
    }

**Альтернатива (проще):** Не усложнять — BuildKit inline cache (`--mount=type=cache`)
уже работает. External cache нужен только для CI/CD или при `docker builder prune`.

**Решение:** Пока skip — текущие `--mount=type=cache` достаточны.
Добавить только если CI будет собирать образы.

## Что НЕ делаем (уже сделано)

| Пункт из issue | Статус | Где сделано |
|----------------|--------|-------------|
| BuildKit cache mounts для uv/pip | ✅ Уже есть | Все Dockerfile используют `--mount=type=cache,target=/root/.cache/uv` |
| BuildKit cache mounts для apt | ✅ Уже есть | Все Dockerfile используют `--mount=type=cache,target=/var/cache/apt` |
| Multi-stage builds | ✅ Уже есть | builder → runtime во всех Dockerfile |
| Align LiteLLM versions | ✅ Уже есть | dev и VPS: `main-v1.81.3-stable` |
| Non-root users | ✅ Уже есть | Все Dockerfile |
| `--chown` вместо `chown -R` | ✅ Уже есть | Все COPY используют `--chown` |

## Потенциальные оптимизации (backlog)

| Оптимизация | Текущий | Target | Effort | Блокеры |
|-------------|---------|--------|--------|---------|
| Ingestion: strip test deps | 3.77 GB | ~3.5 GB | Low | Проверить что не ломает CocoIndex |
| Bot: strip unused packages | 1.19 GB | ~1.0 GB | Low | Audit `pyproject.toml` |
| ML images: shared base | 2.35+1.87 GB | Shared layer | Medium | Нужен common base image |
| Distroless runtime | Varies | -100 MB each | Medium | Нет shell для healthchecks |
| Alpine base | Varies | -200 MB each | High | musl compat issues с ML libs |

## Test Strategy

1. **Build test:**

        docker buildx bake --load
        # Все 6 образов должны собраться без ошибок

2. **Size check:**

        docker images --format "table {{.Repository}}\t{{.Size}}" | grep rag-fresh

3. **Smoke test:**

        make docker-bot-up
        # Bot starts, отвечает на /start
        docker logs dev-bot --tail 20

4. **Ingestion test (после Step 3):**

        docker compose -f docker-compose.dev.yml --profile ingest build ingestion
        docker compose -f docker-compose.dev.yml --profile ingest up -d ingestion
        docker logs dev-ingestion --tail 20
        # Должен запуститься без uv

## Acceptance Criteria

- [ ] `docker-bake.hcl` создан, `docker buildx bake --load` собирает все образы
- [ ] `make docker-bake` работает
- [ ] Ingestion runtime НЕ содержит uv binary
- [ ] Ingestion ENTRYPOINT использует `python -m` напрямую
- [ ] `.dockerignore` оптимизирован, build context < 50 MB
- [ ] Все образы стартуют и проходят healthcheck
- [ ] Документация HDD layout создана

## Effort Estimate

| Step | Time | Priority |
|------|------|----------|
| Step 1: docker-bake.hcl | 5 мин | P0 |
| Step 2: Makefile targets | 3 мин | P0 |
| Step 3: Slim ingestion (uv removal) | 3 мин | P1 |
| Step 4: .dockerignore | 3 мин | P1 |
| Step 5: VPS HDD layout | 5 мин | P2 (ручное на VPS) |
| Step 6: External cache | skip | P3 (backlog) |
| **Total** | **~20 мин** | |

## Риски

| Риск | Митигация |
|------|-----------|
| docker-bake tag mismatch с compose | Проверить `docker compose config | grep image:` перед созданием |
| Ingestion без uv не стартует | Проверить что `python -m src.ingestion.unified.cli` работает из .venv |
| .dockerignore ломает COPY | Тестить build каждого образа отдельно |
| VPS HDD mount permissions | Проверить uid/gid контейнеров vs mount |

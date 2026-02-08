# VPS Phase 2: Ingestion & Optimization Plan

> **For Claude:** REQUIRED SUB-SKILL: Use `/tmux-swarm-orchestration` для параллельных задач (Tasks 2-3), затем `/executing-plans` для последовательных (Task 1, 4).

**Goal:** Запустить индексацию документов на VPS и оптимизировать стек (BGE-M3 sparse вместо BM42, LiteLLM stable).

**Architecture:**
- Task 1: Ingestion (sequential) — индексация документов в Qdrant
- Tasks 2-3: Parallel optimization (tmux workers) — BGE-M3 sparse + LiteLLM stable
- Task 4: Verification (sequential) — финальная проверка и cleanup
- Task 5: Docker optimization (sequential) — daemon.json, healthchecks, cleanup

**Tech Stack:** Docker Compose, BGE-M3, Qdrant, LiteLLM, tmux

---

## Task Overview

| Task | Type | Worker | Description | Priority |
|------|------|--------|-------------|----------|
| 1 | Sequential | - | VPS Ingestion | High |
| 2 | Parallel | W-SPARSE | BGE-M3 sparse вместо BM42 | High |
| 3 | Parallel | W-LITELLM | LiteLLM main-stable | Medium |
| 4 | Sequential | - | Verification & cleanup | High |
| 5 | Sequential | - | Docker VPS optimization | Medium |

**Current State (2026-02-05, updated):**
- VPS target: `vps` (zsh alias и `ssh vps`) → `admin@95.111.252.29:1654` (hostname: `vmi2696211`)
- Docker stack запущен: **10/10 контейнеров healthy** (`vps-*` включая ingestion)
- Qdrant collection `gdrive_documents_bge`: **278 points** (14/14 файлов проиндексировано)
- rclone sync настроен через `/etc/cron.d/rclone-sync` (*/5 * * * *) → `/opt/rag-fresh/drive-sync/` (файлы есть)
- Redis Stack поднят: `maxmemory=256MB`, `maxmemory-policy=volatile-lfu`, `appendonly=no` (индексы: `sem:v2:userbase768`, `rag_conversations:v2:userbase768`)
- **BGE_M3_TIMEOUT=600** + **Semaphore(1)** — sequential processing на CPU-only VPS

**Primary Blocker:** ~~ingestion не наполнил Qdrant~~ **RESOLVED** (2026-02-05)

---

# TASK 1: VPS Ingestion (Sequential)

**Dependencies:** None (run first)

**Files:**
- Check: `/opt/rag-fresh/drive-sync/` (synced documents)
- Check: `docker-compose.vps.yml` (ingestion profile)
- Check: `/opt/rag-fresh/.env` (`GDRIVE_SYNC_DIR`)

## Step 0: Sanity check (подключился к правильному VPS)

Run:
```bash
ssh vps "hostname; docker --version; docker ps --format 'table {{.Names}}\t{{.Status}}' | sed -n '1,12p'"
```

Expected:
- hostname: `vmi2696211`
- `vps-*` контейнеры в статусе `healthy`

## Step 1: Verify synced documents on VPS

Run:
```bash
ssh vps "ls -la /opt/rag-fresh/drive-sync/"
```

Expected: Files/folders from Google Drive (Test/, Procesed/, *.xlsx)

## Step 1.1: Verify rclone cron writes to the same path

Run:
```bash
ssh vps "sudo cat /etc/cron.d/rclone-sync"
```

Expected: `rclone sync ... /opt/rag-fresh/drive-sync/ ...`

## Step 2: Check ingestion service configuration

Run:
```bash
ssh vps "grep -A5 'ingestion:' /opt/rag-fresh/docker-compose.vps.yml"
```

Expected: Service definition with profile `ingest`

## Step 2.1: Fix `.env` so ingestion sees the synced files (обязательно)

Проверить:
```bash
ssh vps "grep -E '^GDRIVE_SYNC_DIR=' /opt/rag-fresh/.env || echo 'MISSING'"
```

Если `MISSING`, добавить (должно совпадать с cron):
```bash
ssh vps "echo 'GDRIVE_SYNC_DIR=/opt/rag-fresh/drive-sync' | sudo tee -a /opt/rag-fresh/.env >/dev/null"
```

## Step 2.2: Убедиться, что ingestion сервис виден только при включённом профиле

Примечание: `ingestion` объявлен в `profiles: [\"ingest\"]`, поэтому без профиля он не появится в `docker compose ... config --services`.

Run:
```bash
ssh vps "cd /opt/rag-fresh && docker compose -f docker-compose.vps.yml --profile ingest config --services | grep '^ingestion$' && echo 'ingestion OK'"
```

## Step 3: Start ingestion container

Run:
```bash
ssh vps "cd /opt/rag-fresh && docker compose --compatibility -f docker-compose.vps.yml --profile ingest up -d ingestion"
```

Expected: `Creating vps-ingestion ... done`

### Note: apply new volume mounts (если меняли `docker-compose.vps.yml`)

Если ты добавил/изменил bind-mounts для кода (`./src`, `./telegram_bot`) *после* того как контейнер уже был создан, `restart` не подхватит изменения — нужен recreate.

Проверить mounts:
```bash
ssh vps "docker inspect vps-ingestion --format '{{range .Mounts}}{{println .Destination \"|\" .Source}}{{end}}' | sort"
```

Ожидаемо (если включён “dev mount”):
- `/app/src | /opt/rag-fresh/src`
- `/app/telegram_bot | /opt/rag-fresh/telegram_bot`

Если их нет — пересоздать контейнер:
```bash
ssh vps "cd /opt/rag-fresh && docker compose -f docker-compose.vps.yml --profile ingest up -d --force-recreate ingestion"
```

## Step 3.1: Verify ingestion container sees the files

Run:
```bash
ssh vps "cd /opt/rag-fresh && docker compose -f docker-compose.vps.yml --profile ingest exec -T ingestion ls -la /data/drive-sync | head -n 50"
```

Expected: внутри контейнера видны те же файлы/папки, что в `/opt/rag-fresh/drive-sync`

## Step 4: Monitor ingestion logs

Run:
```bash
ssh vps "docker logs vps-ingestion -f --tail 80"
```

Expected: `Processing files...`, `Indexed N chunks`, progress updates

## Step 5: Verify points in Qdrant

Run:
```bash
ssh vps "cd /opt/rag-fresh && docker compose -f docker-compose.vps.yml exec -T bge-m3 python -c \"import json, urllib.request; print(json.load(urllib.request.urlopen('http://qdrant:6333/collections/gdrive_documents_bge'))['result']['points_count'])\""
```

Expected: Number > 0

## Step 6: Stop ingestion (or leave in watch mode)

Run:
```bash
ssh vps "cd /opt/rag-fresh && docker compose -f docker-compose.vps.yml --profile ingest stop ingestion"
```

Expected: `Stopping vps-ingestion ... done`

---

# PHASE 2: Parallel Optimization (tmux-swarm)

> **For Claude:** Запускать Tasks 2-3 параллельно через tmux воркеров. Task 1 должен быть завершён.

## Swarm Setup

### Структура воркеров

| Worker | Window | Task | Files | VPS Changes |
|--------|--------|------|-------|-------------|
| W-SPARSE | `W-SPARSE` | Task 2 | `telegram_bot/bot.py`, `src/ingestion/unified/qdrant_writer.py`, `telegram_bot/services/bge_m3.py` | sparse switch + reindex |
| W-LITELLM | `W-LITELLM` | Task 3 | `docker-compose.vps.yml` | image tag |

### Pre-flight (оркестратор)

```bash
# 1. Проверить tmux
echo $TMUX

# 2. Создать директории
mkdir -p logs

# 3. Создать окна
tmux new-window -n "W-SPARSE" -c /home/user/projects/rag-fresh
tmux new-window -n "W-LITELLM" -c /home/user/projects/rag-fresh
```

### Spawn Workers

**Worker W-SPARSE:**
```bash
tmux send-keys -t "W-SPARSE" "claude --dangerously-skip-permissions 'W-SPARSE: Заменить BM42 sparse на BGE-M3 lexical weights.

ПЛАН: /home/user/projects/rag-fresh/docs/plans/2026-02-05-vps-phase2-plan.md
ЗАДАЧА: Task 2

ИЗМЕНЕНИЯ:
1. Добавить BGE-M3 sparse client в telegram_bot/services/bge_m3.py
2. Обновить telegram_bot/bot.py — sparse из BGE-M3 (/encode/sparse или /encode/hybrid) вместо BM42
3. Обновить src/ingestion/unified/qdrant_writer.py — индексировать sparse через BGE-M3 lexical weights
4. Обновить tests

⚠️ BEST PRACTICES 2026:
1. ПЕРЕД реализацией API клиента используй Context7:
   - mcp__context7__resolve-library-id для qdrant-client
   - mcp__context7__query-docs для SparseVector, NamedSparseVector API
2. Проверь формат sparse vector в Qdrant (indices + values)
3. НЕ запускай все тесты — только pytest tests/unit/test_bge_m3.py -v

SKILLS: superpowers:executing-plans, superpowers:verification-before-completion

НЕ ТРОГАТЬ: docker-compose.vps.yml (другой воркер)

ЛОГИРОВАНИЕ в /home/user/projects/rag-fresh/logs/worker-sparse.log:
[START] timestamp Task
[DONE] timestamp Task
[COMPLETE] timestamp Worker finished

НЕ делай git commit — оркестратор сделает.'" Enter
```

**Worker W-LITELLM:**
```bash
tmux send-keys -t "W-LITELLM" "claude --dangerously-skip-permissions 'W-LITELLM: Обновить LiteLLM до main-stable.

ПЛАН: /home/user/projects/rag-fresh/docs/plans/2026-02-05-vps-phase2-plan.md
ЗАДАЧА: Task 3

ИЗМЕНЕНИЯ:
1. Обновить docker-compose.vps.yml: image: ghcr.io/berriai/litellm:main-stable
2. Проверить docker/litellm/config.yaml совместимость

⚠️ BEST PRACTICES 2026:
1. ПЕРЕД изменением образа используй Context7:
   - mcp__context7__resolve-library-id для litellm
   - mcp__context7__query-docs для config.yaml format, model_list syntax
2. Проверь что main-stable тег существует: docker pull --dry-run или ghcr.io tags
3. НЕ запускай все тесты — только docker compose config --quiet

SKILLS: superpowers:executing-plans, superpowers:verification-before-completion

НЕ ТРОГАТЬ: telegram_bot/bot.py, src/ingestion/unified/qdrant_writer.py (другой воркер)

ЛОГИРОВАНИЕ в /home/user/projects/rag-fresh/logs/worker-litellm.log:
[START] timestamp Task
[DONE] timestamp Task
[COMPLETE] timestamp Worker finished

НЕ делай git commit — оркестратор сделает.'" Enter
```

### Auto-Monitor

```bash
# Запустить мониторинг
./scripts/monitor-workers.sh &

# Или вручную проверять
tail -f logs/worker-sparse.log logs/worker-litellm.log
```

### Post-Swarm (оркестратор)

После всех `[COMPLETE]`:

```bash
# 1. Проверить изменения
git status
git diff --stat

# 2. Запустить тесты
make test-unit

# 3. Commit
git add -A
git commit -m "perf(vps): use BGE-M3 sparse, update LiteLLM to stable

- Replace BM42 with BGE-M3 lexical weights (better multilingual)
- Update LiteLLM image to main-stable (production ready)
- Remove dependency on separate bm42 service

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"

# 4. Deploy to VPS
rsync -avz --exclude='.git' --exclude='__pycache__' --exclude='.venv' \
  /home/user/projects/rag-fresh/ vps:/opt/rag-fresh/

# 5. Rebuild and restart on VPS
ssh vps "cd /opt/rag-fresh && docker compose -f docker-compose.vps.yml pull litellm"
ssh vps "cd /opt/rag-fresh && docker compose -f docker-compose.vps.yml build bot"
ssh vps "cd /opt/rag-fresh && docker compose --compatibility -f docker-compose.vps.yml up -d"
```

---

# TASK 2 (optional): Replace BM42 sparse with BGE-M3 lexical weights (requires reindex)

> ВАЖНО: сейчас `gdrive_documents_bge` ожидает sparse-вектор `bm42`, и ingestion генерирует его через FastEmbed BM42.
> Если переключить query sparse на BGE-M3 lexical weights, **нужно переиндексировать коллекцию**, иначе sparse-часть hybrid поиска станет бессмысленной.

**Files:**
- Create: `telegram_bot/services/bge_m3.py` (HTTP client)
- Modify: `telegram_bot/bot.py` (получение sparse вектора)
- Modify: `src/ingestion/unified/qdrant_writer.py` (sparse для документов)
- Test: `tests/unit/test_bge_m3.py`

## Step 1: Create BGE-M3 client service

Create `telegram_bot/services/bge_m3.py`:

```python
"""BGE-M3 embedding client for hybrid search.

Provides dense + sparse embeddings in single API call.
Replaces separate BM42 service for sparse vectors.
"""

import logging
from typing import Any

import httpx

logger = logging.getLogger(__name__)


class BgeM3Client:
    """Client for BGE-M3 embedding service.

    Supports:
    - Dense embeddings (1024-dim)
    - Sparse/lexical weights (for hybrid search)
    - ColBERT vectors (for reranking)
    """

    def __init__(
        self,
        base_url: str = "http://localhost:8000",
        timeout: float = 30.0,
    ):
        self.base_url = base_url
        self.timeout = timeout
        self._client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=self.base_url,
                timeout=self.timeout,
            )
        return self._client

    async def encode_hybrid(
        self,
        texts: list[str],
    ) -> dict[str, Any]:
        """Encode texts with dense + sparse in single call.

        Returns:
            {
                "dense_vecs": [[float, ...], ...],  # 1024-dim
                "lexical_weights": [{"indices": [...], "values": [...]}, ...],
                "colbert_vecs": [[[...], ...], ...],  # optional in hybrid response
            }
        """
        client = await self._get_client()
        response = await client.post(
            "/encode/hybrid",
            json={"texts": texts},
        )
        response.raise_for_status()
        return response.json()

    async def encode_dense(self, texts: list[str]) -> list[list[float]]:
        """Encode texts with dense embeddings only."""
        client = await self._get_client()
        response = await client.post(
            "/encode/dense",
            json={"texts": texts},
        )
        response.raise_for_status()
        return response.json()["dense_vecs"]

    async def encode_sparse(self, texts: list[str]) -> list[dict[str, Any]]:
        """Encode texts with sparse/lexical weights only.

        Returns: [{"indices": [...], "values": [...]}, ...]
        """
        client = await self._get_client()
        response = await client.post(
            "/encode/sparse",
            json={"texts": texts},
        )
        response.raise_for_status()
        return response.json()["lexical_weights"]

    async def rerank_colbert(
        self,
        query: str,
        documents: list[str],
        top_k: int = 10,
    ) -> list[dict[str, Any]]:
        """Rerank documents using ColBERT MaxSim."""
        client = await self._get_client()
        response = await client.post(
            "/rerank",
            json={
                "query": query,
                "documents": documents,
                "top_k": top_k,
            },
        )
        response.raise_for_status()
        return response.json()["results"]

    async def aclose(self):
        """Close HTTP client."""
        if self._client:
            await self._client.aclose()
            self._client = None
```

## Step 2: Add to services __init__.py

Modify `telegram_bot/services/__init__.py`:

```python
from telegram_bot.services.bge_m3 import BgeM3Client

__all__ = [
    # ... existing exports
    "BgeM3Client",
]
```

## Step 3: Write failing test

Create `tests/unit/test_bge_m3.py`:

```python
"""Tests for BGE-M3 client."""

import pytest
from unittest.mock import AsyncMock, patch

from telegram_bot.services.bge_m3 import BgeM3Client


@pytest.fixture
def client():
    return BgeM3Client(base_url="http://test:8000")


@pytest.mark.asyncio
async def test_encode_hybrid_returns_dense_and_sparse(client):
    """encode_hybrid returns both dense and sparse vectors."""
    mock_response = {
        "dense_vecs": [[0.1] * 1024],
        "lexical_weights": [{"indices": [123, 456], "values": [0.5, 0.3]}],
    }

    with patch.object(client, "_get_client") as mock_get:
        mock_client = AsyncMock()
        mock_client.post.return_value.json.return_value = mock_response
        mock_client.post.return_value.raise_for_status = lambda: None
        mock_get.return_value = mock_client

        result = await client.encode_hybrid(["test text"])

        assert "dense_vecs" in result
        assert "lexical_weights" in result
        assert len(result["dense_vecs"][0]) == 1024


@pytest.mark.asyncio
async def test_encode_dense_returns_vectors(client):
    """encode_dense returns only dense vectors."""
    mock_response = {"dense_vecs": [[0.1] * 1024]}

    with patch.object(client, "_get_client") as mock_get:
        mock_client = AsyncMock()
        mock_client.post.return_value.json.return_value = mock_response
        mock_client.post.return_value.raise_for_status = lambda: None
        mock_get.return_value = mock_client

        result = await client.encode_dense(["test text"])

        assert len(result) == 1
        assert len(result[0]) == 1024
```

## Step 4: Run test to verify it passes

Run: `pytest tests/unit/test_bge_m3.py -v`

Expected: PASS

## Step 5: Update bot sparse retrieval + ingestion sparse indexing (reindex required)

1) `telegram_bot/bot.py`: заменить `_get_sparse_vector()` (BM42) на вызов BGE-M3 `/encode/sparse`
   (или `/encode/hybrid` для одного текста) и кешировать под другим `model_name`
   (например `bge-m3-lexical`).

2) `src/ingestion/unified/qdrant_writer.py`: sparse для документов должен совпадать со sparse для query.
   Самый простой путь: вместо `SparseTextEmbedding(...bm42...)` использовать BGE-M3 `/encode/sparse`
   для chunk-текстов и писать это в Qdrant как sparse-вектор `bm42` (или переименовать vector field и
   пересоздать коллекцию).

3) Пересоздать коллекцию и прогнать ingestion заново (Task 1), иначе sparse-часть hybrid поиска не будет работать.

## Step 6: Log completion

```bash
echo "[DONE] $(date '+%Y-%m-%d %H:%M:%S') Task 2: BGE-M3 sparse" >> /home/user/projects/rag-fresh/logs/worker-sparse.log
echo "[COMPLETE] $(date '+%Y-%m-%d %H:%M:%S') Worker W-SPARSE finished" >> /home/user/projects/rag-fresh/logs/worker-sparse.log
```

---

# TASK 3: LiteLLM Stable (Worker W-LITELLM)

**Files:**
- Modify: `docker-compose.vps.yml`
- Check: `docker/litellm/config.yaml`

## Step 1: Update LiteLLM image tag

Modify `docker-compose.vps.yml`, find litellm service:

**Before:**
```yaml
litellm:
  image: ghcr.io/berriai/litellm:v1.81.3.rc.3
```

**After:**
```yaml
litellm:
  image: ghcr.io/berriai/litellm:main-stable
```

Примечание: если `main-stable` недоступен/не подходит, выбрать конкретный stable-tag (не `rc`) и зафиксировать его.

## Step 2: Verify config.yaml compatibility

Run:
```bash
cat docker/litellm/config.yaml | head -30
```

Check that model_list format is compatible with stable version.

## Step 3: Validate compose file syntax

Run:
```bash
docker compose -f docker-compose.vps.yml config --quiet && echo "Syntax OK"
```

Expected: `Syntax OK` (no errors)

## Step 4: Log completion

```bash
echo "[DONE] $(date '+%Y-%m-%d %H:%M:%S') Task 3: LiteLLM stable" >> /home/user/projects/rag-fresh/logs/worker-litellm.log
echo "[COMPLETE] $(date '+%Y-%m-%d %H:%M:%S') Worker W-LITELLM finished" >> /home/user/projects/rag-fresh/logs/worker-litellm.log
```

---

# TASK 4: Verification & Cleanup (Sequential)

**Dependencies:** Tasks 1-3 complete, changes deployed to VPS

## Step 1: Verify all containers healthy

Run:
```bash
ssh vps "docker ps --format 'table {{.Names}}\t{{.Status}}' | grep vps"
```

Expected: 9/9 healthy (or 8/9 if bm42 removed)

## Step 2: Verify Qdrant has documents

Run:
```bash
ssh vps "cd /opt/rag-fresh && docker compose -f docker-compose.vps.yml exec -T bge-m3 python -c \"import json, urllib.request; print(json.load(urllib.request.urlopen('http://qdrant:6333/collections/gdrive_documents_bge'))['result']['points_count'])\""
```

Expected: Number > 0

## Step 3: Test bot response

Send test message to `@test_nika_homes_bot` in Telegram.

Expected: Bot responds with relevant information from indexed documents.

## Step 4: Check LiteLLM health

Run:
```bash
ssh vps "cd /opt/rag-fresh && docker compose -f docker-compose.vps.yml exec -T litellm python -c \"import urllib.request; print(urllib.request.urlopen('http://localhost:4000/health/liveliness', timeout=5).read().decode())\""
```

Expected: `"healthy"` or `{"status":"healthy"}`

## Step 5: Check memory usage

Run:
```bash
ssh vps "docker stats --no-stream --format 'table {{.Name}}\t{{.MemUsage}}' | grep vps"
```

Expected (для текущего VPS с ~11GiB RAM):
- контейнеры суммарно < ~8GiB
- swap не растёт постоянно при idle

## Step 6: Optional - Remove BM42 service

If BGE-M3 sparse is working correctly:

```bash
ssh vps "docker compose -f docker-compose.vps.yml stop bm42"
ssh vps "docker compose -f docker-compose.vps.yml rm -f bm42"
```

## Step 7: Update deployment plan

Mark Phase 2 as complete in `docs/plans/2026-02-05-vps-deployment-plan.md`.

## Step 8: Final commit

```bash
git add docs/plans/
git commit -m "docs: mark VPS Phase 2 complete

- Ingestion running, documents indexed
- BGE-M3 sparse replaces BM42
- LiteLLM updated to main-stable

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Чеклист завершения

### Task 1: Ingestion ✅ COMPLETE (2026-02-05)
- [x] Documents synced via rclone (14 файлов)
- [x] Ingestion container started (vps-ingestion healthy)
- [x] Points in Qdrant > 0 (**278 points**, 9 reprocessed, 5 no change)
- [x] Ingestion in watch mode (CocoIndex FlowLiveUpdater)
- [x] BGE_M3_TIMEOUT=600 (CPU inference fix)
- [x] Semaphore(1) — sequential processing (no OOM/timeout)

### Tasks 2-3: Parallel Optimization (tmux workers)
- [ ] W-SPARSE: BgeM3Client created
- [ ] W-SPARSE: bot + ingestion updated (sparse)
- [ ] W-SPARSE: tests pass
- [ ] W-LITELLM: docker-compose.vps.yml updated
- [ ] W-LITELLM: config validated
- [ ] Changes committed
- [ ] Deployed to VPS

### Task 4: Verification
- [ ] All containers healthy
- [ ] Bot responds correctly
- [ ] LiteLLM healthy
- [ ] Memory OK (см. критерий выше)
- [ ] BM42 removed (optional)
- [ ] Plan updated

### Task 5: Docker VPS Optimization
- [ ] daemon.json с log rotation
- [ ] Healthchecks с start_period
- [ ] Resource limits verified
- [ ] Cleanup cron настроен
- [ ] Kernel tuning (optional)

---

---

# TASK 5: Docker VPS Optimization (Best Practices 2026)

> **Источники:** Exa MCP search (2026-02-05) — northflank.com, oneuptime.com, docker.recipes, youstable.com

**Priority:** Medium (после ingestion)

## 5.1 Docker Daemon Configuration

**File:** `/etc/docker/daemon.json` на VPS

```json
{
  "storage-driver": "overlay2",
  "log-driver": "json-file",
  "log-opts": {
    "max-size": "50m",
    "max-file": "3"
  },
  "default-ulimits": {
    "nofile": {
      "Name": "nofile",
      "Hard": 65536,
      "Soft": 65536
    }
  },
  "live-restore": true,
  "userland-proxy": false,
  "default-address-pools": [
    {"base": "172.17.0.0/16", "size": 24}
  ]
}
```

**Применить:**
```bash
ssh vps "sudo tee /etc/docker/daemon.json << 'EOF'
{
  \"storage-driver\": \"overlay2\",
  \"log-driver\": \"json-file\",
  \"log-opts\": {
    \"max-size\": \"50m\",
    \"max-file\": \"3\"
  },
  \"default-ulimits\": {
    \"nofile\": {
      \"Name\": \"nofile\",
      \"Hard\": 65536,
      \"Soft\": 65536
    }
  },
  \"live-restore\": true,
  \"userland-proxy\": false
}
EOF"
ssh vps "sudo systemctl restart docker"
```

| Параметр | Значение | Эффект |
|----------|----------|--------|
| `overlay2` | storage driver | Лучшая производительность на Linux |
| `max-size: 50m` | log rotation | Предотвращает заполнение диска |
| `max-file: 3` | log files | Хранит 3 файла × 50MB = 150MB max |
| `nofile: 65536` | file descriptors | Для high-concurrency сервисов |
| `live-restore: true` | daemon restart | Контейнеры не падают при рестарте dockerd |
| `userland-proxy: false` | networking | Быстрее, использует iptables напрямую |

## 5.2 Healthcheck Best Practices

**Проблема:** `depends_on` только ждёт старта контейнера, не готовности сервиса.

**Решение:** Healthcheck + `condition: service_healthy`

```yaml
services:
  postgres:
    image: postgres:16-alpine
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U postgres"]
      interval: 10s
      timeout: 5s
      retries: 5
      start_period: 30s  # Grace period для медленного старта

  redis:
    image: redis:7-alpine
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 10s
      timeout: 5s
      retries: 3

  qdrant:
    image: qdrant/qdrant:v1.13.2
    healthcheck:
      test: ["CMD-SHELL", "curl -sf http://localhost:6333/readyz || exit 1"]
      interval: 15s
      timeout: 10s
      retries: 5
      start_period: 60s

  bge-m3:
    # ... model service
    healthcheck:
      test: ["CMD-SHELL", "curl -sf http://localhost:8000/health || exit 1"]
      interval: 30s
      timeout: 15s
      retries: 3
      start_period: 300s  # 5 min для загрузки модели

  bot:
    depends_on:
      postgres:
        condition: service_healthy
      redis:
        condition: service_healthy
      qdrant:
        condition: service_healthy
      bge-m3:
        condition: service_healthy
```

**Важно:** `start_period` — время grace period до первой проверки (для сервисов с долгой инициализацией).

## 5.3 Resource Limits (Memory & CPU)

```yaml
services:
  bge-m3:
    deploy:
      resources:
        limits:
          memory: 4G
          cpus: '2.0'
        reservations:
          memory: 2G
          cpus: '1.0'

  bot:
    deploy:
      resources:
        limits:
          memory: 512M
          cpus: '0.5'
```

**Применить лимиты:** `docker compose --compatibility up -d`

**Проверить:**
```bash
ssh vps "docker stats --no-stream --format 'table {{.Name}}\t{{.MemUsage}}\t{{.MemPerc}}\t{{.CPUPerc}}' | grep vps"
```

## 5.4 BuildKit Cache Mounts (Faster Rebuilds)

**Уже реализовано в наших Dockerfiles:**

```dockerfile
# syntax=docker/dockerfile:1.4

# Cache pip downloads (10-100x faster rebuilds)
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install -r requirements.txt

# Cache uv (если используется)
RUN --mount=type=cache,target=/root/.cache/uv \
    uv pip install -r requirements.txt
```

**Включить BuildKit:**
```bash
export DOCKER_BUILDKIT=1
# или в daemon.json:
# "features": { "buildkit": true }
```

## 5.5 Multi-Stage Builds (Smaller Images)

**Pattern:**
```dockerfile
# === BUILD STAGE ===
FROM python:3.12-slim AS builder
WORKDIR /app
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"
COPY requirements.txt .
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install -r requirements.txt

# === RUNTIME STAGE ===
FROM python:3.12-slim AS runtime
COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"
COPY app.py .
USER appuser
CMD ["python", "app.py"]
```

**Экономия:** 30-70% размера образа

## 5.6 Image Optimization Checklist

| Практика | Статус | Эффект |
|----------|--------|--------|
| Multi-stage builds | ✅ | -30-70% размер |
| Alpine/slim base images | ✅ | -50% размер |
| CPU-only PyTorch | ✅ | -82% (docling) |
| Cache mounts | ✅ | 10x быстрее rebuild |
| Non-root user | ✅ | Security |
| .dockerignore | ⚠️ Проверить | Меньше context |
| Pin versions | ✅ | Reproducibility |

## 5.7 Cleanup & Maintenance

### Текущий статус на VPS (2026-02-05)

На `vmi2696211` сейчас основное “съедает” не данные, а **Build Cache + unused images**:
- Images: ~43GB reclaimable (99%)
- Build cache: ~31GB, reclaimable ~31GB
- Volumes: ~6GB (0 reclaimable)

Проверить:
```bash
ssh vps "df -h /; docker system df"
```

### Рекомендованная очистка (без потери данных)

**Шаг A (самый безопасный): только BuildKit cache** — не трогает running containers и volumes, просто следующий build будет дольше.
```bash
ssh vps "docker builder prune -a -f"
```

**Шаг B (если нужно ещё место): удалить неиспользуемые образы** — не удаляет образы, которые используются running containers.
```bash
ssh vps "docker image prune -a -f"
```

После каждого шага:
```bash
ssh vps "docker system df"
```

### Автоматизация (без `--volumes`)

`--volumes` в автокроне не ставим: если когда-нибудь сервисы будут остановлены/пересобраны, “unused” volumes могут стать данными (Postgres/Qdrant/Redis).

**Консервативная еженедельная очистка:**
```bash
# Пример cron: чистим только build cache старше 7 дней + dangling images
0 3 * * 0 docker builder prune -f --filter 'until=168h' 2>&1 | logger -t docker-cleanup
5 3 * * 0 docker image prune -f 2>&1 | logger -t docker-cleanup
```

## 5.8 Kernel Tuning (Optional, Advanced)

```bash
# /etc/sysctl.d/99-docker.conf на VPS
ssh vps "sudo tee /etc/sysctl.d/99-docker.conf << 'EOF'
# Increase max connections
net.core.somaxconn = 65535
net.ipv4.tcp_max_syn_backlog = 65535

# Faster TIME_WAIT recycling
net.ipv4.tcp_tw_reuse = 1

# Increase file descriptors
fs.file-max = 2097152
fs.inotify.max_user_watches = 524288

# Memory overcommit (for Redis)
vm.overcommit_memory = 1
EOF"
ssh vps "sudo sysctl -p /etc/sysctl.d/99-docker.conf"
```

---

## Чеклист Task 5: Docker Optimization

- [ ] daemon.json с log rotation и overlay2
- [ ] Healthchecks с start_period для всех сервисов
- [ ] Resource limits проверены
- [ ] BuildKit включён
- [ ] .dockerignore актуален
- [ ] Cron для cleanup настроен (без `--volumes`)
- [ ] Kernel tuning применён (optional)

---

## 5.9 Shrink `rag-fresh_ingestion` image (disk win)

### Симптом

На VPS `rag-fresh_ingestion:latest` занимает ~28GB, при этом внутри контейнера основная масса — `/app/.venv` (~8.6GB). На практике такой размер почти всегда означает **дублирование данных в слоях образа**, а не “реально нужные” зависимости.

### Причина (типовой кейс)

`RUN chown -R ... /app` после `COPY /app/.venv ...` создаёт новый слой, который “перезаписывает” большую часть файлов — в итоге они оказываются **и в слое COPY, и в слое chown**.

Проверить на VPS:
```bash
ssh vps "docker history rag-fresh_ingestion:latest | sed -n '1,25p'"
```

### Фикс (не ломая runtime-права)

- Создать пользователя **до** копирования файлов в runtime stage
- Убрать рекурсивный `chown -R`
- Вместо этого использовать `COPY --chown=ingestion:ingestion ...` для `.venv`, `src/`, `telegram_bot/`

После фикса потребуется rebuild образа ingestion (можно в окне maintenance):
```bash
ssh vps "cd /opt/rag-fresh && docker compose -f docker-compose.vps.yml --profile ingest build ingestion"
ssh vps "cd /opt/rag-fresh && docker compose -f docker-compose.vps.yml --profile ingest up -d --force-recreate ingestion"
```

## Quick Reference

```bash
# Check VPS status
ssh vps "docker ps --format 'table {{.Names}}\t{{.Status}}' | grep vps"

# Check Qdrant points
ssh vps "cd /opt/rag-fresh && docker compose -f docker-compose.vps.yml exec -T bge-m3 python -c \"import json, urllib.request; print(json.load(urllib.request.urlopen('http://qdrant:6333/collections/gdrive_documents_bge'))['result']['points_count'])\""

# Ingestion logs
ssh vps "docker logs vps-ingestion --tail 50"

# Memory
ssh vps "docker stats --no-stream | grep vps"

# Restart service
ssh vps "cd /opt/rag-fresh && docker compose -f docker-compose.vps.yml restart bot"
```

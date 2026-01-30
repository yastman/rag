# WSL Migration Verification Plan

**Date:** 2026-01-30
**Output:** `docs/2026-01-30-wsl-migration-report.md`

---

## Prerequisites

```bash
# Ensure Docker is running
docker info >/dev/null 2>&1 || echo "ERROR: Docker not running"

# Start services if needed
docker compose -f docker-compose.dev.yml up -d

# Wait for services to be healthy (30-60 seconds)
docker compose -f docker-compose.dev.yml ps
```

---

## 1. Environment (5 checks)

### 1.1 Python version
```bash
python --version
```
**Expected:** `Python 3.12.x`

### 1.2 Python path is native WSL
```bash
which python
```
**Expected:** `/home/user/projects/rag-fresh/.venv/bin/python` (NOT `/mnt/...`)

### 1.3 Project filesystem is native
```bash
df -T . | awk 'NR==2 {print $2}'
```
**Expected:** `ext4` (NOT `9p` or `drvfs`)

### 1.4 .env symlink works
```bash
ls -la .env && head -1 .env
```
**Expected:** `.env -> .env.local`, first line readable (no permission error)

### 1.5 Git status clean (no CRLF/permission changes)
```bash
git status --porcelain | head -10
```
**Expected:** Only expected changes (CLAUDE.md, uv.lock). No mass M/D flags from line endings or permissions.

---

## 2. Docker Services (11 checks)

```bash
docker compose -f docker-compose.dev.yml ps --format "table {{.Name}}\t{{.Status}}"
```

| Service | Expected Status |
|---------|-----------------|
| dev-qdrant | healthy |
| dev-redis | healthy |
| dev-langfuse | healthy |
| dev-litellm | healthy OR running |
| dev-mlflow | healthy |
| dev-bot | healthy |
| dev-clickhouse | healthy |
| dev-minio | healthy |
| dev-postgres | healthy |
| dev-redis-langfuse | healthy |
| dev-langfuse-worker | running (no healthcheck) |

**Pass criteria:** All 11 containers Up, no Restarting/Exit states.

---

## 3. Unit Tests (1 check)

```bash
pytest tests/unit/ -q --tb=no
```
**Expected:**
- Exit code 0
- `X passed` where X >= 1600
- No failures or errors

---

## 4. Integration (5 checks)

### 4.1 Redis ping
```bash
docker exec dev-redis redis-cli PING
```
**Expected:** `PONG`

### 4.2 Redis set/get
```bash
docker exec dev-redis redis-cli SET wsl_test "ok" EX 10 && \
docker exec dev-redis redis-cli GET wsl_test
```
**Expected:** `OK` then `ok`

### 4.3 Qdrant collection info
```bash
curl -s http://localhost:6333/collections/contextual_bulgaria_voyage | jq '.result.points_count'
```
**Expected:** Number >= 90 (current: 192)

### 4.4 LiteLLM health
```bash
curl -s http://localhost:4000/health | jq '.status'
```
**Expected:** `"healthy"` OR non-empty JSON response

### 4.5 Langfuse API
```bash
curl -s http://localhost:3001/api/public/health | jq '.status'
```
**Expected:** `"OK"` or 200 response

---

## 5. Bot Smoke (3 checks)

### 5.1 Services import
```bash
python -c "from telegram_bot.services import VoyageService, QdrantService, CacheService; print('OK')"
```
**Expected:** `OK` (no ImportError)

### 5.2 VoyageService init (no API call)
```bash
python -c "
from telegram_bot.services import VoyageService
import os
v = VoyageService(api_key=os.getenv('VOYAGE_API_KEY', 'test'))
print('VoyageService: OK')
"
```
**Expected:** `VoyageService: OK`

### 5.3 QdrantService init
```bash
python -c "
from telegram_bot.services import QdrantService
q = QdrantService(url='http://localhost:6333', collection_name='contextual_bulgaria_voyage')
print('QdrantService: OK')
"
```
**Expected:** `QdrantService: OK`

---

## 6. WSL-Specific Risks (3 checks)

### 6.1 No Windows paths in use
```bash
pwd | grep -q "^/mnt/" && echo "FAIL: using Windows FS" || echo "OK: native WSL"
```
**Expected:** `OK: native WSL`

### 6.2 Executable permissions preserved
```bash
ls -la scripts/*.py | head -3
```
**Expected:** Scripts have appropriate permissions (not all 777 or missing execute)

### 6.3 Symlinks work
```bash
readlink .env && test -f "$(readlink .env)" && echo "Symlink OK"
```
**Expected:** `.env.local` and `Symlink OK`

---

## Summary

| Category | Checks | Pass Criteria |
|----------|--------|---------------|
| Environment | 5 | All green |
| Docker Services | 11 | All Up/healthy |
| Unit Tests | 1 | >= 1600 passed, 0 failed |
| Integration | 5 | All endpoints respond |
| Bot Smoke | 3 | All imports/inits succeed |
| WSL-Specific | 3 | Native FS, permissions OK |

**Total:** 28 checks

---

## Execution

Run checks in order. Record results in `docs/2026-01-30-wsl-migration-report.md` with:
- Timestamp
- Pass/Fail per category
- Any error details
- Versions (Python, Docker, key packages)

# TODO - Current Tasks

> **Дата:** 2026-01-21
> **Версия:** v2.8.0
> **План:** [docs/plans/2026-01-21-local-project-setup.md](docs/plans/2026-01-21-local-project-setup.md)

---

## Текущий статус

```
Phase 1 (Configuration):    ██████████ 100% (4/4)
Phase 2 (Dev Tools):        ██████████ 100% (2/2)
Phase 3 (Test Infra):       ██████████ 100% (2/2)
Phase 4 (Index Data):       ██████████ 100% (3/3)
Phase 5 (Verify Services):  ██████████ 100% (3/3)
Phase 6 (Telegram Bot):     ██████████ 100% (2/2)
Phase 7 (Final):            ██████████ 100% (1/1)
─────────────────────────────────────────────────
Total:                      ██████████ 100% (17/17)
```

---

## Phase 1: Fix Configuration

| #   | Task                         | Status | Details                           |
| --- | ---------------------------- | ------ | --------------------------------- |
| 1.1 | Fix BGE_M3_URL in .env.local | ✅     | 8001 → 8000                       |
| 1.2 | Create .env symlink          | ✅     | ln -s .env.local .env             |
| 1.3 | Fix QDRANT_COLLECTION        | ✅     | apartments_local → test_documents |
| 1.4 | Fix docker health checks     | ✅     | Qdrant, Langfuse now healthy      |

---

## Phase 2: Install Dev Tools

| #   | Task                 | Status | Details                                   |
| --- | -------------------- | ------ | ----------------------------------------- |
| 2.1 | Install pytest       | ✅     | pytest 9.0.2 installed                    |
| 2.2 | Verify make commands | ✅     | lint OK, type-check has issue (see notes) |

---

## Phase 3: Test Infrastructure

| #   | Task                    | Status | Details                        |
| --- | ----------------------- | ------ | ------------------------------ |
| 3.1 | Create conftest.py      | ✅     | tests/conftest.py              |
| 3.2 | Create sample test data | ✅     | data/test/sample_articles.json |

---

## Phase 4: Index Documents

| #   | Task                   | Status | Details                               |
| --- | ---------------------- | ------ | ------------------------------------- |
| 4.1 | Create indexing script | ✅     | scripts/index_test_data.py            |
| 4.2 | Run indexing           | ✅     | 3 documents indexed to test_documents |
| 4.3 | Test search works      | ✅     | Search PASSED (Крадіжка top result)   |

---

## Phase 5: Verify Services

| #   | Task                   | Status | Details                                       |
| --- | ---------------------- | ------ | --------------------------------------------- |
| 5.1 | Test Redis cache       | ✅     | `docker exec dev-redis redis-cli ping` → PONG |
| 5.2 | Test embedding service | ✅     | EmbeddingService OK (1024 dims)               |
| 5.3 | Test retriever service | ✅     | RetrieverService OK (3 results, Крадіжка top) |

---

## Phase 6: Telegram Bot

| #   | Task                 | Status | Details                               |
| --- | -------------------- | ------ | ------------------------------------- |
| 6.1 | Test bot services    | ✅     | BotConfig OK, all services configured |
| 6.2 | Verify bot can start | ✅     | Bot module imports OK, ready to start |

---

## Phase 7: Final Verification

| #   | Task          | Status | Details                                                                    |
| --- | ------------- | ------ | -------------------------------------------------------------------------- |
| 7.1 | Run all tests | ✅     | pytest has import errors, make check has type errors, all services healthy |

---

## Legend

| Symbol | Meaning     |
| ------ | ----------- |
| ⏳     | Pending     |
| 🔄     | In Progress |
| ✅     | Completed   |
| ❌     | Blocked     |
| ⚠️     | Has Issues  |

---

## Infrastructure Status (Аудит 2026-01-21)

| Service  | Port       | Status     |
| -------- | ---------- | ---------- |
| Postgres | 5432       | ✅ healthy |
| Redis    | 6379, 8001 | ✅ healthy |
| Qdrant   | 6333       | ✅ healthy |
| BGE-M3   | 8000       | ✅ healthy |
| Docling  | 5001       | ✅ healthy |
| MLflow   | 5000       | ✅ healthy |
| Langfuse | 3001       | ✅ healthy |
| LightRAG | 9621       | ✅ healthy |

---

## Quick Commands

```bash
# View plan
cat docs/plans/2026-01-21-local-project-setup.md

# Start services
docker compose -f docker-compose.dev.yml up -d

# Check services
docker ps --format "table {{.Names}}\t{{.Status}}"

# Run tests
make test

# Start bot
python -m telegram_bot.main
```

---

## Discovered Issues (добавлять сюда новые проблемы)

### Issue 1: MyPy fails with package name error

**Error:** `rag-fresh is not a valid Python package name`
**Cause:** Directory name contains hyphen, mypy doesn't like it
**Workaround:** Run mypy from src/ directory or rename project folder
**Priority:** Low (doesn't block development)

### Issue 2: Root **init**.py breaks pytest ✅ FIXED

**Error:** `ImportError: attempted relative import with no known parent package`
**Cause:** Root `__init__.py` has relative imports but isn't a proper package
**Solution:** Removed the obsolete root `__init__.py` file
**Status:** Resolved

### Issue 3: Async syntax in sync function ✅ FIXED

**Error:** `SyntaxError: 'async with' outside async function` in search_engines.py
**Cause:** `_search_hybrid_colbert` method used `async with httpx.AsyncClient` but was defined as sync
**Solution:** Changed to sync `with httpx.Client` (function is called synchronously)
**Status:** Resolved

---

**Last Updated:** 2026-01-21

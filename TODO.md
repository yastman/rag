# TODO - Current Tasks

> **Дата:** 2026-01-21
> **Версия:** v2.9.0
> **Ветка:** feat/redis-stack-vector-search

---

## Текущий статус

```
Local Setup:            ██████████ 100% ✅
Telegram Bot:           ██████████ 100% ✅
CESC Personalization:   ██████████ 100% ✅ NEW
Contextual Retrieval:   ████████░░  80% 🟡
Production Deploy:      ░░░░░░░░░░   0% ⏸️
```

---

## Active Tasks

| # | Task | Status | Priority |
|---|------|--------|----------|
| 1 | Process VTT files → JSON | ⏳ | High |
| 2 | Index contextual chunks | ⏳ | High |
| 3 | Test search quality | ⏳ | High |
| 4 | Merge to main | ⏳ | Medium |

---

## Completed Today (2026-01-21)

### CESC Implementation (v2.9.0)
- [x] UserContextService - извлечение preferences через LLM
- [x] CESCPersonalizer - персонализация cache HIT
- [x] Bot integration - handle_query с CESC
- [x] Configuration - cesc_enabled, extraction_frequency, ttl
- [x] Unit tests - 19 + 11 = 30 tests
- [x] Integration tests - 3 tests
- [x] Documentation - CHANGELOG, CACHING, README

### Earlier Today
- [x] Contextual Retrieval pipeline (schema, loader, script)
- [x] 19 tests passing for contextual modules
- [x] Removed cross-encoder (redundant with ColBERT)
- [x] GLM-4.7 config improvements
- [x] index_test_data.py compatibility fix

---

## CESC Feature Summary

```
┌─────────────────────────────────────────────────┐
│  CESC (Context-Enabled Semantic Cache)          │
├─────────────────────────────────────────────────┤
│  User preferences extracted every 3rd query     │
│  Stored in Redis JSON (TTL: 30 days)            │
│  Cache HIT personalized via LLM (~100 tokens)   │
│  Latency: ~100ms (vs 2-3s full RAG)             │
└─────────────────────────────────────────────────┘
```

**New Files:**
- `telegram_bot/services/user_context.py`
- `telegram_bot/services/cesc.py`
- `tests/test_user_context.py`
- `tests/test_cesc.py`
- `tests/test_cesc_integration.py`

---

## Infrastructure Status

| Service | Port | Status |
|---------|------|--------|
| Postgres | 5432 | ✅ |
| Redis Stack | 6379, 8001 | ✅ |
| Qdrant | 6333 | ✅ |
| BGE-M3 | 8000 | ✅ |
| Docling | 5001 | ✅ |
| MLflow | 5000 | ✅ |
| Langfuse | 3001 | ✅ |
| Telegram Bot | - | ✅ Working |

---

## Next Steps

### Option A: Test Contextual Retrieval
```bash
# 1. Claude CLI processes VTT → JSON
# 2. Index JSON
python scripts/index_contextual.py docs/processed/*.json -c contextual_demo
# 3. Test search
```

### Option B: Merge to Main
```bash
git checkout main
git merge feat/redis-stack-vector-search
git push
```

---

## Quick Commands

```bash
# Start services
docker compose -f docker-compose.dev.yml up -d

# Run all tests
source venv/bin/activate && pytest tests/ -v

# Run CESC tests only
pytest tests/test_user_context.py tests/test_cesc.py tests/test_cesc_integration.py -v

# Run contextual tests only
pytest tests/test_contextual_*.py -v

# Start bot
python -m telegram_bot.main
```

---

**Last Updated:** 2026-01-21

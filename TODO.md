# TODO - Current Tasks

> **Дата:** 2026-01-22
> **Версия:** v2.9.0 (Voyage AI unified)
> **Ветка:** feat/redis-stack-vector-search

---

## Текущий статус

```
Local Setup:            ██████████ 100% ✅
Telegram Bot:           ██████████ 100% ✅
CESC Personalization:   ██████████ 100% ✅
Voyage AI Migration:    ██████████ 100% ✅ NEW
Contextual Retrieval:   ████████░░  80% 🟡
Production Deploy:      ░░░░░░░░░░   0% ⏸️
```

---

## Voyage AI Migration (Completed 2026-01-22)

| Phase | Task | Status |
|-------|------|--------|
| 1 | VoyageEmbeddingService | ✅ Complete |
| 2 | VoyageRerankerService | ✅ Complete |
| 3 | HybridRetrieverService (RRF fusion) | ✅ Complete |
| 4 | SemanticCache (VoyageAITextVectorizer) | ✅ Complete |
| 5 | QueryPreprocessor integration | ✅ Complete |
| 6 | Collection migration (contextual_bulgaria_voyage) | ✅ Complete |
| 7 | Integration tests (52 tests) | ✅ Complete |
| 8 | Documentation updates | ✅ Complete |

**Key Changes:**
- Collection: `contextual_bulgaria_voyage` (Voyage 1024-dim + BM42 sparse)
- Embeddings: voyage-3-large (1024-dim)
- Cache: voyage-3-lite via VoyageAITextVectorizer
- Reranking: rerank-2

---

## Active Tasks

| # | Task | Status | Priority |
|---|------|--------|----------|
| 1 | Merge to main | ⏳ | High |
| 2 | Production deployment | ⏳ | Medium |

---

## Completed Today (2026-01-22)

### Cache Bugfixes & Features (v2.9.1)
- [x] Fix EmbeddingsCache API - `text` → `content` parameter
- [x] Add LLMService.generate() - for CESC preference extraction
- [x] Fix streaming duplicate edit - prevent Telegram "message not modified" error
- [x] Add SemanticMessageHistory - semantic conversation context retrieval
- [x] Tests - 8 new tests passing

### Voyage AI Migration (v2.9.0)
- [x] VoyageEmbeddingService - dense embeddings via voyage-3-large
- [x] VoyageRerankerService - reranking via rerank-2
- [x] HybridRetrieverService - RRF fusion (dense + sparse)
- [x] SemanticCache migration - VoyageAITextVectorizer (voyage-3-lite)
- [x] QueryPreprocessor - translit, dynamic RRF weights
- [x] Collection indexed - contextual_bulgaria_voyage (92 chunks)
- [x] Integration tests - 52 tests passing
- [x] Documentation updates - CLAUDE.md, TODO.md

### Completed 2026-01-21

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

**Last Updated:** 2026-01-22

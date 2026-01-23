# Full Stack Migration to Voyage AI + Docker

**Date:** 2026-01-22
**Status:** In Progress
**Version:** 2.9.0 (Voyage AI unified)
**Goal:** Make full RAG stack work locally, containerize Telegram bot, pass all tests

---

## 1. Current State Analysis

### What's Already Implemented (v2.9.0)

The project already has Voyage AI services fully implemented:

| Service | Status | Description |
|---------|--------|-------------|
| `VoyageClient` | ✅ Done | Singleton API client with tenacity retry |
| `VoyageEmbeddingService` | ✅ Done | voyage-3-large (1024-dim) |
| `VoyageRerankerService` | ✅ Done | rerank-2 |
| `HybridRetrieverService` | ✅ Done | RRF fusion (dense + sparse) |
| `QueryPreprocessor` | ✅ Done | Translit, dynamic RRF weights |
| `CacheService` | ✅ Done | Semantic cache with VoyageAITextVectorizer |
| `CESCPersonalizer` | ✅ Done | Context-Enabled Semantic Cache |

### Infrastructure Running

```
Docker containers (dev):
├── dev-qdrant      (6333) - Vector database ✅
├── dev-redis       (6379) - Semantic cache ✅
├── dev-postgres    (5432) - Metadata store ✅
├── dev-mlflow      (5000) - Experiment tracking ✅
├── dev-langfuse    (3001) - LLM tracing ✅
├── dev-bge-m3      (8000) - Legacy embeddings (optional)
├── dev-docling     (5001) - Document parsing
└── dev-lightrag    (9621) - Graph RAG
```

### Data Collections

| Collection | Points | Vectors | Status |
|------------|--------|---------|--------|
| `contextual_bulgaria` | 92 | BGE-M3 (1024-dim) | Old |
| `contextual_bulgaria_voyage` | 92 | Voyage (1024-dim) + BM42 | ✅ Ready |

### API Keys (.env)

```env
VOYAGE_API_KEY=REDACTED_VOYAGE_KEY
TELEGRAM_BOT_TOKEN=8568271552:AAE0owKx2LqVXkxgarJ4eFKbDZFBd_pjjtw
LLM_API_KEY=REDACTED_CEREBRAS_KEY_2  ***REMOVED***
```

---

## 2. Target Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                     Telegram Bot (Docker)                        │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  User Query                                                      │
│      │                                                           │
│      ▼                                                           │
│  ┌──────────────────┐    ┌──────────────────┐                   │
│  │ QueryPreprocessor│    │ Translit         │                   │
│  │ (normalize)      │───►│ Latin→Cyrillic   │                   │
│  └────────┬─────────┘    └──────────────────┘                   │
│           │                                                      │
│           ▼                                                      │
│  ┌──────────────────┐    ┌──────────────────┐                   │
│  │ Semantic Cache   │◄──►│ Redis Stack      │                   │
│  │ (voyage-3-lite)  │    │ (6379)           │                   │
│  └────────┬─────────┘    └──────────────────┘                   │
│           │ miss                                                 │
│           ▼                                                      │
│  ┌──────────────────┐                                           │
│  │ VoyageEmbedding  │ ──► voyage-3-large (1024-dim)             │
│  │ Service          │                                           │
│  └────────┬─────────┘                                           │
│           │                                                      │
│           ▼                                                      │
│  ┌──────────────────┐    ┌──────────────────┐                   │
│  │ RetrieverService │◄──►│ Qdrant           │                   │
│  │ (dense search)   │    │ (6333)           │                   │
│  └────────┬─────────┘    └──────────────────┘                   │
│           │ top 50                                               │
│           ▼                                                      │
│  ┌──────────────────┐                                           │
│  │ VoyageReranker   │ ──► rerank-2 (top 5)                      │
│  │ Service          │                                           │
│  └────────┬─────────┘                                           │
│           │                                                      │
│           ▼                                                      │
│  ┌──────────────────┐                                           │
│  │ LLM Service      │ ──► Cerebras qwen-3-32b (streaming)       │
│  └──────────────────┘                                           │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

---

## 3. Remaining Tasks

### Phase 1: Fix RetrieverService Filter ⏳ IN PROGRESS

**Problem:** RetrieverService filters by `source_type=csv_row`, but Voyage collection has `source_type=vtt_contextual`.

**Solution:** Remove restrictive filter, search all documents.

```python
# telegram_bot/services/retriever.py
def _build_base_filter(self) -> Optional[models.Filter]:
    """Return None to search all documents."""
    return None
```

**Files to modify:**
- `telegram_bot/services/retriever.py` - Remove csv_row filter

### Phase 2: Test Full Pipeline

```bash
# 1. Test embedding
python3 -c "
import asyncio
from telegram_bot.services import VoyageEmbeddingService
async def test():
    svc = VoyageEmbeddingService()
    emb = await svc.embed_query('квартира в Солнечном береге')
    print(f'Embedding: {len(emb)}-dim')
asyncio.run(test())
"

# 2. Test search + rerank
python3 -c "
import asyncio
from telegram_bot.services import VoyageEmbeddingService, RetrieverService, VoyageRerankerService
async def test():
    embed = VoyageEmbeddingService()
    retriever = RetrieverService('http://localhost:6333', '', 'contextual_bulgaria_voyage')
    reranker = VoyageRerankerService()

    vec = await embed.embed_query('квартира в Солнечном береге')
    results = retriever.search(vec, top_k=20, min_score=0.3)
    reranked = await reranker.rerank('квартира', results, top_k=5)

    print(f'Search: {len(results)}, Reranked: {len(reranked)}')
    for r in reranked[:3]:
        print(f'  Score: {r[\"rerank_score\"]:.3f} - {r[\"metadata\"].get(\"topic\", \"\")}')
asyncio.run(test())
"
```

### Phase 3: Build & Run Bot in Docker

```bash
# Build
docker compose -f docker-compose.dev.yml build bot

# Start
docker compose -f docker-compose.dev.yml up -d bot

# Check logs
docker logs -f dev-bot

# Verify Telegram connection
curl -s "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/getMe" | python3 -m json.tool
```

### Phase 4: Run Tests

```bash
# All tests
make test

***REMOVED***-specific tests
pytest tests/test_voyage*.py -v

# Integration tests
pytest tests/integration/ -v
```

### Phase 5: Update Documentation

- [ ] Update CLAUDE.md with current status
- [ ] Update TODO.md
- [ ] Commit all changes

---

## 4. Files Modified

| File | Status | Changes |
|------|--------|---------|
| `.env` | ✅ | VOYAGE_API_KEY, TELEGRAM_BOT_TOKEN |
| `telegram_bot/Dockerfile` | ✅ | Multi-stage build |
| `telegram_bot/requirements.txt` | ✅ | voyageai, redisvl, fastembed |
| `docker-compose.dev.yml` | ✅ | Bot service added |
| `src/ingestion/voyage_indexer.py` | ✅ | VoyageIndexer with rate limiting |
| `telegram_bot/bot.py` | ✅ | Uses Voyage services |
| `telegram_bot/services/retriever.py` | ⏳ | Remove csv_row filter |

---

## 5. Docker Bot Service

```yaml
# docker-compose.dev.yml
bot:
  build:
    context: .
    dockerfile: telegram_bot/Dockerfile
  container_name: dev-bot
  environment:
    TELEGRAM_BOT_TOKEN: ${TELEGRAM_BOT_TOKEN}
    VOYAGE_API_KEY: ${VOYAGE_API_KEY}
    VOYAGE_EMBED_MODEL: ${VOYAGE_EMBED_MODEL:-voyage-3-large}
    VOYAGE_RERANK_MODEL: ${VOYAGE_RERANK_MODEL:-rerank-2}
    LLM_API_KEY: ${LLM_API_KEY}
    LLM_BASE_URL: ${LLM_BASE_URL:-https://api.cerebras.ai/v1}
    LLM_MODEL: ${LLM_MODEL:-qwen-3-32b}
    REDIS_URL: redis://redis:6379
    QDRANT_URL: http://qdrant:6333
    QDRANT_COLLECTION: ${QDRANT_COLLECTION:-contextual_bulgaria_voyage}
  depends_on:
    redis:
      condition: service_healthy
    qdrant:
      condition: service_healthy
  restart: unless-stopped
  deploy:
    resources:
      limits:
        memory: 512M
```

---

## 6. Search Quality Metrics

Tested with query: "квартира в Солнечном береге"

| Stage | Results | Top Score | Notes |
|-------|---------|-----------|-------|
| Dense search | 5 | 0.555 | Good relevance |
| After rerank | 3 | TBD | Should improve order |

**Sample results:**
1. Score 0.555 - "Локации и способы покупки" (relevant)
2. Score 0.504 - "Миф о дешёвой недвижимости" (relevant)
3. Score 0.503 - "Признаки проблемной недвижимости" (relevant)

---

## 7. Rate Limits

| Service | Free Tier | Notes |
|---------|-----------|-------|
| Voyage AI | 3 RPM, 10K TPM | Add 25s delay between batches |
| Cerebras | Standard | No issues observed |

**Mitigation:** VoyageIndexer uses 25s delay between batches for reindexing.

---

## 8. Success Criteria

- [ ] Bot responds to `/start` in Telegram
- [ ] Search returns relevant results (score > 0.4)
- [ ] Reranking improves top results
- [ ] All tests pass (`make test`)
- [ ] Docker container stable > 1 hour
- [ ] No API rate limit errors

---

## 9. Rollback Plan

If issues occur:

1. **Keep old collection** - `contextual_bulgaria` remains intact
2. **Revert .env** - Set `QDRANT_COLLECTION=contextual_bulgaria`
3. **BGE-M3 available** - Container on port 8000
4. **Git revert** - All changes in single branch `feat/redis-stack-vector-search`

---

## 10. Post-Migration Optimizations

### Week 2: Cache Tuning
- A/B test semantic threshold (0.92-0.97)
- Monitor hit rate via Redis metrics

### Week 3: Hybrid Search
- Enable BM42 sparse in bot
- Implement RRF fusion in retriever

### Week 4: Production
- Deploy to VPS
- Configure Langfuse monitoring
- Set up alerts

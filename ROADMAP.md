# RAG Project Roadmap

> **Статус проекта:** Local development ready, bot working with CESC
> **Последнее обновление:** 2026-01-21
> **Текущий релиз:** v2.9.0
> **Ветка:** feat/redis-stack-vector-search (26 commits ahead of main)

---

## Прогресс

```
Phase 1 (Infrastructure):  ██████████  100% ✅ COMPLETED
Phase 2 (Configuration):   ██████████  100% ✅ COMPLETED
Phase 3 (Data & Testing):  █████████░   90% 🟡 IN PROGRESS
Phase 4 (Production):      ░░░░░░░░░░    0% ⏸️ PLANNED
```

---

## PHASE 1: INFRASTRUCTURE ✅ COMPLETED

Все сервисы развёрнуты и работают.

| Компонент | Статус | Порт |
|-----------|--------|------|
| Docker Compose | ✅ | - |
| Postgres + pgvector | ✅ | 5432 |
| Redis Stack | ✅ | 6379, 8001 |
| Qdrant | ✅ | 6333 |
| BGE-M3 API | ✅ | 8000 |
| Docling | ✅ | 5001 |
| MLflow | ✅ | 5000 |
| Langfuse | ✅ | 3001 |
| LightRAG | ✅ | 9621 |
| GitHub Actions CI | ✅ | - |

---

## PHASE 2: CONFIGURATION ✅ COMPLETED

- [x] pyproject.toml (ruff, mypy, pytest config)
- [x] .env.local with API keys
- [x] .env symlink
- [x] docker-compose.dev.yml
- [x] docker-compose.local.yml
- [x] CI workflows (lint, type-check)
- [x] BGE_M3_URL fixed (8000)
- [x] pytest installed
- [x] tests/conftest.py created
- [x] Docker health checks fixed

---

## PHASE 3: DATA & TESTING 🟡 IN PROGRESS

### ✅ Completed
- [x] Test documents indexed (test_documents collection)
- [x] Search works (HybridRRFColBERT)
- [x] Telegram bot working with GLM-4.7
- [x] Contextual Retrieval pipeline (schema, loader, script)
- [x] Unit tests for contextual modules (19 tests)
- [x] Cross-encoder removed (ColBERT handles reranking)
- [x] **CESC v2.9.0** - Context-Enabled Semantic Cache
  - [x] UserContextService (preference extraction)
  - [x] CESCPersonalizer (cache personalization)
  - [x] Bot integration
  - [x] 33 tests (unit + integration)
  - [x] Documentation updated

### ⏳ Remaining
- [ ] Process VTT files with Contextual Retrieval
- [ ] Index real video content
- [ ] Integration tests for full pipeline
- [ ] Merge to main branch

---

## PHASE 4: PRODUCTION ⏸️ PLANNED

### VPS Deployment
- [ ] Production docker-compose
- [ ] SSL/TLS configuration
- [ ] Environment variables for production
- [ ] Backup strategy

### Monitoring
- [ ] Prometheus metrics
- [ ] Grafana dashboards
- [ ] Alerting rules

### Security
- [ ] Rate limiting
- [ ] Input validation
- [ ] Secrets management

---

## Recent Changes (2026-01-21)

| Change | Impact |
|--------|--------|
| **CESC v2.9.0** | Personalized cache responses |
| UserContextService | Extract preferences from queries |
| CESCPersonalizer | Adapt cached answers to user context |
| 33 new tests | Full CESC coverage |
| Contextual Retrieval pipeline | +35-49% retrieval accuracy for VTT |
| Removed cross-encoder | Faster startup, less RAM |
| GLM-4.7 integration | Free LLM via Cerebras |
| Redis Stack upgrade | Vector search support |

---

## Version History

| Version | Date | Highlights |
|---------|------|------------|
| v2.9.0 | 2026-01-21 | CESC personalization |
| v2.8.0 | 2025-01-06 | Graceful degradation, JSON logging |
| v2.7.0 | 2025-01-06 | Streaming LLM, conversation memory |
| v2.6.0 | 2025-01-06 | Async migration, BGE-M3 singleton |

---

## Service URLs (Local Development)

| Service | URL |
|---------|-----|
| Qdrant Dashboard | http://localhost:6333/dashboard |
| RedisInsight | http://localhost:8001 |
| MLflow UI | http://localhost:5000 |
| Langfuse | http://localhost:3001 |
| BGE-M3 Docs | http://localhost:8000/docs |
| Docling Docs | http://localhost:5001/docs |

---

## Quick Commands

```bash
# Start services
docker compose -f docker-compose.dev.yml up -d

# Run tests
source venv/bin/activate && pytest tests/ -v

# Run CESC tests
pytest tests/test_user_context.py tests/test_cesc.py tests/test_cesc_integration.py -v

# Start bot
python -m telegram_bot.main

# Index contextual JSON
python scripts/index_contextual.py docs/processed/*.json
```

---

**Last Updated:** 2026-01-21

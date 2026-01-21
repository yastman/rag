***REMOVED*** RAG Project Roadmap

> **Статус проекта:** Development environment ready
> **Последнее обновление:** 2026-01-21
> **Текущий релиз:** v2.8.0
> **Активный план:** [docs/plans/2026-01-21-local-project-setup.md](docs/plans/2026-01-21-local-project-setup.md)

---

***REMOVED******REMOVED*** Прогресс

```
Phase 1 (Infrastructure):  ██████████  100% ✅ COMPLETED
Phase 2 (Configuration):   ████░░░░░░   40% 🟡 IN PROGRESS
Phase 3 (Data & Testing):  ░░░░░░░░░░    0% ⏸️ BLOCKED
Phase 4 (Production):      ░░░░░░░░░░    0% ⏸️ PLANNED
```

---

***REMOVED******REMOVED*** PHASE 1: INFRASTRUCTURE ✅ COMPLETED

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

***REMOVED******REMOVED*** PHASE 2: CONFIGURATION 🟡 IN PROGRESS

***REMOVED******REMOVED******REMOVED*** ✅ Completed
- [x] pyproject.toml (ruff, mypy, pytest config)
- [x] .env.local with API keys
- [x] docker-compose.dev.yml
- [x] CI workflows (lint, type-check)

***REMOVED******REMOVED******REMOVED*** ❌ Remaining
- [ ] **Fix BGE_M3_URL** (8001 → 8000)
- [ ] **Fix src/config/settings.py** (crashes without .env)
- [ ] **Install pytest** in dev environment
- [ ] Create tests/conftest.py
- [ ] Fix docker health checks (Qdrant, Langfuse)

---

***REMOVED******REMOVED*** PHASE 3: DATA & TESTING ⏸️ BLOCKED

**Blocker:** No documents indexed, configuration issues

***REMOVED******REMOVED******REMOVED*** Tasks
- [ ] Prepare documents for indexing
- [ ] Run document ingestion pipeline
- [ ] Verify Qdrant collections have data
- [ ] Write unit tests (cache, LLM, retriever)
- [ ] Write integration tests
- [ ] Add service containers to CI

---

***REMOVED******REMOVED*** PHASE 4: PRODUCTION ⏸️ PLANNED

***REMOVED******REMOVED******REMOVED*** VPS Deployment
- [ ] Production docker-compose
- [ ] SSL/TLS configuration
- [ ] Environment variables for production
- [ ] Backup strategy

***REMOVED******REMOVED******REMOVED*** Monitoring
- [ ] Prometheus metrics
- [ ] Grafana dashboards
- [ ] Alerting rules

***REMOVED******REMOVED******REMOVED*** Security
- [ ] Rate limiting
- [ ] Input validation
- [ ] Secrets management

---

***REMOVED******REMOVED*** Current Blockers

| Blocker | Impact | Fix |
|---------|--------|-----|
| Wrong BGE_M3_URL | Bot can't get embeddings | Change 8001 → 8000 |
| Empty collections | Search returns nothing | Index documents |
| No pytest | Can't run tests | pip install pytest |
| settings.py crashes | Can't import src modules | Create .env symlink |

---

***REMOVED******REMOVED*** Quick Start (После исправления)

```bash
***REMOVED*** 1. Fix configuration
sed -i 's/8001/8000/' .env.local
ln -s .env.local .env

***REMOVED*** 2. Install dev tools
pip install pytest pytest-asyncio pytest-cov

***REMOVED*** 3. Start services
docker compose -f docker-compose.dev.yml up -d

***REMOVED*** 4. Index documents
python -m src.ingestion.indexer --input data/documents/

***REMOVED*** 5. Run tests
make test

***REMOVED*** 6. Start bot
python -m telegram_bot.main
```

---

***REMOVED******REMOVED*** Service URLs (Local Development)

| Service | URL |
|---------|-----|
| Qdrant Dashboard | http://localhost:6333/dashboard |
| RedisInsight | http://localhost:8001 |
| MLflow UI | http://localhost:5000 |
| Langfuse | http://localhost:3001 |
| BGE-M3 Docs | http://localhost:8000/docs |
| Docling Docs | http://localhost:5001/docs |

---

**Last Updated:** 2026-01-21

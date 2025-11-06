# 📋 TODO - Current Tasks

> **Дата:** 2025-01-06
> **Версия:** v2.8.0 (95% Production-Ready)
> **Статус:** Ready for VPS deployment

---

## ✅ COMPLETED (v2.6.0 - v2.8.0)

### v2.8.0 - Resilience & Observability
- [x] Graceful degradation for all services (Qdrant, LLM, Redis)
- [x] Structured JSON logging for production
- [x] LLM fallback answers on API failure
- [x] Health checks for services

### v2.7.0 - User Experience
- [x] Streaming LLM responses (0.1s TTFB)
- [x] Conversation memory (multi-turn dialogues)
- [x] Cross-encoder reranking (+10-15% accuracy)
- [x] /clear and /stats commands

### v2.6.0 - Critical Fixes
- [x] Security: Removed exposed API keys
- [x] Performance: requests → httpx.AsyncClient
- [x] Dependencies: Complete requirements.txt
- [x] Performance: Fixed blocking async calls
- [x] BGE-M3 singleton pattern (saves 4-6GB RAM)

---

## 🔥 HIGH PRIORITY (Текущая неделя)

### 🖥️ SERVER TASKS (Deploy на VPS)

#### S1. Deploy BGE-M3 FastAPI Service ⭐ КРИТИЧНО
**Время:** 2-3 часа
**Порт:** 8001

```bash
# Create src/services/bge_m3_api.py
# Create docker/bge-m3/Dockerfile
# docker-compose integration
Status: ⏳ Bot expects localhost:8001 but service not running
```

**Действия:**
1. Create FastAPI app with /embed endpoint
2. Load BGE-M3 model once at startup (singleton)
3. Add /health endpoint
4. Create Dockerfile (CPU or CUDA)
5. Test: curl -X POST localhost:8001/embed

---

#### S2. Deploy MLflow Server
**Время:** 1 час
**Порт:** 5000

```bash
mlflow server \
  --backend-store-uri sqlite:///mlflow.db \
  --default-artifact-root ./mlruns \
  --host 0.0.0.0 --port 5000

Status: ⏳ Referenced in code, unclear if running
```

---

#### S3. Deploy Langfuse Server
**Время:** 1 час
**Порт:** 3001

```bash
docker run -d --name langfuse \
  -p 3001:3000 \
  -e DATABASE_URL=postgresql://... \
  langfuse/langfuse:latest

Status: ⏳ Code integration exists, server unknown
```

---

### 💻 LOCAL TASKS (Можно делать локально)

#### L1. Create docker-compose.yml ⭐ НАЧАТЬ С ЭТОГО
**Время:** 2-3 hours

```yaml
# Include: Qdrant, Redis, BGE-M3, Bot, MLflow, Langfuse
# Networks, volumes, health checks
# .env integration

Status: ❌ No file exists (referenced everywhere)
Priority: 🔴 CRITICAL for easy deployment
```

**После создания:**
- Test locally: `docker-compose up -d`
- Push to git
- Deploy on VPS with same command

---

#### L2. Setup pytest Configuration
**Время:** 2-3 hours

```bash
Create:
- pytest.ini (test discovery, coverage config)
- conftest.py (shared fixtures)
- tests/unit/ (unit tests structure)
- tests/integration/ (integration tests)

Status: ❌ Test files exist but no pytest infrastructure
```

---

#### L3. GitHub Actions CI/CD
**Время:** 3-4 hours

```yaml
Create:
- .github/workflows/ci.yml (test + lint on PR)
- .github/workflows/deploy.yml (build + push images)

Status: ❌ No CI/CD pipeline
```

---

## 🟡 MEDIUM PRIORITY (Следующая неделя)

### Testing (Local)
- [ ] Unit tests: Cache service (23 tests, 85% coverage) - 4-5h
- [ ] Unit tests: LLM service (17 tests, 80% coverage) - 3-4h
- [ ] Unit tests: Retriever service (14 tests, 75% coverage) - 3h
- [ ] Integration tests: RAG pipeline (8 tests) - 4-5h
- [ ] Integration tests: Graceful degradation (8 tests) - 3h

### Monitoring (Server)
- [ ] Prometheus + Grafana deployment - 2-3h
- [ ] Prometheus /metrics endpoint in bot - 2-3h
- [ ] Grafana dashboards for cache, LLM, Qdrant - 2h

### Performance (Local → Server)
- [ ] Connection pooling (Qdrant, Redis) - 3-4h
- [ ] Migrate to AsyncQdrantClient - 3-4h
- [ ] Distributed lock for semantic cache - 2h
- [ ] Load testing scripts (locust) - 2-3h

---

## 🟢 LOW PRIORITY (Nice to Have)

### Features
- [ ] User feedback loop (👍/👎 inline buttons) - 3-4h
- [ ] Admin dashboard for monitoring - 1 week
- [ ] A/B testing framework for cache strategies - 1 week

### Code Quality
- [ ] Setup ruff, mypy, pre-commit hooks - 2h
- [ ] API documentation generation (Sphinx/mkdocs) - 2-3h
- [ ] Resolve TODOs in mlflow_experiments.py - 1-2h

---

## 📅 RECOMMENDED TIMELINE

### Week 1: VPS Setup (Current Week)
```bash
День 1 (Server):
- Morning: Deploy BGE-M3 service (S1) - 3h
- Afternoon: Deploy MLflow (S2) - 1h

День 2 (Server):
- Morning: Deploy Langfuse (S3) - 1h
- Afternoon: Test full integration - 2h

День 3 (Local → Server):
- Morning: Create docker-compose.yml (L1) - 3h
- Afternoon: Deploy docker-compose on VPS - 2h
```

### Week 2: Testing & CI/CD
```bash
День 1-2 (Local):
- pytest setup (L2) - 3h
- Unit tests for cache, LLM, retriever - 10h

День 3-4 (Local):
- Integration tests - 7h
- GitHub Actions CI/CD (L3) - 4h

День 5 (Server):
- Load testing - 4h
```

### Week 3: Monitoring & Polish
```bash
День 1-2 (Server):
- Prometheus + Grafana - 5h
- Backup strategy - 2h

День 3-5 (Local + Server):
- Performance optimizations - 10h
- Documentation updates - 3h
- Final testing - 4h
```

---

## 🎯 SUCCESS METRICS

### Before VPS Deployment
- [x] All v2.8.0 features working
- [ ] docker-compose.yml created
- [ ] BGE-M3 service ready
- [ ] All secrets in .env

### After VPS Deployment
- [ ] All services running (Qdrant, Redis, BGE-M3, Bot, MLflow, Langfuse)
- [ ] Bot responds to queries < 2s
- [ ] Cache hit rate > 70%
- [ ] No exposed secrets
- [ ] Logs in JSON format
- [ ] Monitoring dashboards active

### After Testing Phase
- [ ] 70%+ test coverage
- [ ] CI/CD pipeline green
- [ ] Load test passed (10 users, 100 req/min)
- [ ] Zero-downtime deployment tested

---

## 📚 Quick Links

**Documentation:**
- [VPS_QUICKSTART.md](./VPS_QUICKSTART.md) - Guide for VPS work
- [TASK_ALLOCATION.md](./docs/TASK_ALLOCATION.md) - Full task breakdown
- [TESTING_PLAN.md](./docs/TESTING_PLAN.md) - Testing strategy
- [CHANGELOG.md](./CHANGELOG.md) - Version history
- [DEPLOYMENT.md](./DEPLOYMENT.md) - Deployment guide

**Monitoring (after deployment):**
- Qdrant: http://localhost:6333/dashboard
- MLflow: http://localhost:5000
- Langfuse: http://localhost:3001
- Grafana: http://localhost:3000

---

## 🚀 GETTING STARTED

### For Local Development:
```bash
cd /mnt/c/Users/user/Documents/Сайты/Раг
git pull origin main

# Start with docker-compose.yml creation
touch docker-compose.yml
# ... (add services)
```

### For VPS Deployment:
```bash
ssh admin@your-server-ip
cd /srv/contextual_rag
git pull origin main

# Follow VPS_QUICKSTART.md
# Start with S1: Deploy BGE-M3 service
```

---

**Last Updated:** 2025-01-06
**Status:** Ready for VPS work
**Next Step:** Read VPS_QUICKSTART.md → Start S1 (BGE-M3 deployment)

# Task Allocation - Server vs Local Development

> **Цель:** Разделить задачи по месту выполнения для эффективной разработки

**Дата:** 2025-01-06
**Версия:** 2.8.0
**Статус:** 95% Production-Ready

---

## 📊 Current Environment

### Local Development (Windows WSL)
```
Location: /mnt/c/Users/user/Documents/Сайты/Раг
Hardware: CPU only (no GPU)
Purpose: Code development, testing with mocks, documentation
Git: Connected to https://github.com/yastman/rag.git
```

### Production VPS Server
```
Location: /home/admin/contextual_rag
Hardware: Unknown specs (likely CPU only or small GPU)
Running: Qdrant (6333), Redis (6379), Telegram Bot
Purpose: Production deployment, real service testing
```

---

## 🖥️ SERVER TASKS (Требуют VPS)

### Priority 1: Must Deploy on Server 🔴

#### S1.1 BGE-M3 Model Deployment (2-3 hours)
**Why Server:** Requires 2-3GB RAM, runs continuously

```bash
# On VPS: /home/admin/contextual_rag
Task:
- Setup BGE-M3 as standalone service (FastAPI wrapper)
- Port 8001 exposed
- Load model once on startup (singleton)
- Health check endpoint
- Dockerfile for deployment

Location: Create src/services/bge_m3_api.py
Docker: Create docker/bge-m3/Dockerfile

Status: ⏳ Referenced in bot config but not running as service
```

**Deliverables:**
- [ ] BGE-M3 FastAPI service
- [ ] Dockerfile for BGE-M3
- [ ] Health check endpoint /health
- [ ] Embedding endpoint /embed (batch support)
- [ ] Running on VPS port 8001

---

#### S1.2 MLflow Server Deployment (1 hour)
**Why Server:** Needs persistent storage, shared across team

```bash
# On VPS
Task:
- Setup MLflow tracking server (port 5000)
- Configure artifact storage
- Setup database backend (SQLite or PostgreSQL)
- Ensure accessible from local dev

Commands:
mlflow server \
  --backend-store-uri sqlite:///mlflow.db \
  --default-artifact-root ./mlruns \
  --host 0.0.0.0 \
  --port 5000

Status: ⏳ Mentioned in docs, but unclear if running
```

**Deliverables:**
- [ ] MLflow server running on port 5000
- [ ] Persistent storage configured
- [ ] Accessible from local machine (firewall rules)

---

#### S1.3 Langfuse Server Deployment (1 hour)
**Why Server:** LLM tracing needs centralized collection

```bash
# On VPS
Task:
- Deploy Langfuse (port 3001)
- Configure database (PostgreSQL recommended)
- Setup API keys
- Connect bot to Langfuse

Docker:
docker run -d \
  --name langfuse \
  -p 3001:3000 \
  -e DATABASE_URL=postgresql://... \
  langfuse/langfuse:latest

Status: ⏳ Code integrated, unclear if server running
```

**Deliverables:**
- [ ] Langfuse server running on port 3001
- [ ] Database configured
- [ ] Bot sending traces to Langfuse

---

#### S1.4 Prometheus + Grafana Stack (2-3 hours)
**Why Server:** Real-time monitoring requires 24/7 uptime

```bash
# On VPS
Task:
- Deploy Prometheus (port 9090)
- Deploy Grafana (port 3000)
- Configure scraping targets
- Create dashboards for:
  * Cache hit rates
  * LLM latency
  * Query volume
  * Error rates

Status: ❌ Not deployed (ROADMAP Phase 4.1)
```

**Deliverables:**
- [ ] Prometheus running and scraping metrics
- [ ] Grafana dashboards created
- [ ] Bot exposing /metrics endpoint (see L2.4)

---

### Priority 2: Should Deploy on Server 🟡

#### S2.1 Load Testing & Performance Tuning (4-5 hours)
**Why Server:** Needs production environment

```bash
# On VPS
Task:
- Run locust/artillery load tests
- Measure performance under:
  * 10 concurrent users
  * 100 queries/minute
  * Cache cold-start
- Tune connection pools
- Optimize Qdrant HNSW parameters

Tools:
- locust -f tests/load/locustfile.py
- Monitor with Prometheus/Grafana

Status: ⏳ Need to create load tests first (see L3.3)
```

**Deliverables:**
- [ ] Load test results documented
- [ ] Performance bottlenecks identified
- [ ] Connection pooling tuned
- [ ] Performance baseline established

---

#### S2.2 Backup & Disaster Recovery (2-3 hours)
**Why Server:** Requires access to production data

```bash
# On VPS
Task:
- Setup automated Qdrant backups
- Setup Redis persistence (RDB + AOF)
- Backup MLflow experiments
- Document restore procedures

Cron jobs:
0 2 * * * /usr/local/bin/backup_qdrant.sh
0 3 * * * /usr/local/bin/backup_redis.sh

Status: ❌ No backup strategy (not in ROADMAP)
```

**Deliverables:**
- [ ] Automated Qdrant backups (daily)
- [ ] Redis persistence enabled
- [ ] Backup scripts in repo
- [ ] Restore procedure documented

---

#### S2.3 Production Environment Variables Audit (1 hour)
**Why Server:** Check actual production config

```bash
# On VPS
Task:
- Review .env file
- Ensure all secrets properly set
- Check LOG_LEVEL, LOG_FORMAT
- Verify API endpoints accessible
- Document any missing configs

Location: /home/admin/contextual_rag/.env

Status: ⚠️ Should verify after v2.8.0 changes
```

**Deliverables:**
- [ ] .env audit report
- [ ] Missing variables identified
- [ ] Updated .env.example if needed

---

### Priority 3: Nice to Have on Server 🟢

#### S3.1 SSL/TLS for Internal Services (2 hours)
**Why Server:** Requires certificate management

```bash
# On VPS
Task:
- Setup Let's Encrypt for public endpoints
- Or self-signed certs for internal services
- Configure nginx reverse proxy
- HTTPS for MLflow, Langfuse, Grafana

Status: ⏳ Likely not needed (internal network)
```

---

#### S3.2 Resource Monitoring & Alerts (3 hours)
**Why Server:** Continuous monitoring

```bash
# On VPS
Task:
- Setup resource alerts (CPU, RAM, disk)
- Prometheus alertmanager
- Telegram notifications on errors
- Log rotation (logrotate)

Status: ❌ No alerting configured
```

---

## 💻 LOCAL TASKS (Можно делать на WSL)

### Priority 1: Critical for CI/CD 🔴

#### L1.1 docker-compose.yml Creation (2-3 hours)
**Why Local:** Configuration file, can test locally

```yaml
# Create: docker-compose.yml
Services:
- qdrant:
    image: qdrant/qdrant:v1.15.4
    ports: [6333:6333]
    volumes: [./qdrant_storage:/qdrant/storage]

- redis:
    image: redis/redis-stack:8.2.0-v0
    ports: [6379:6379]

- bge-m3:
    build: ./docker/bge-m3
    ports: [8001:8001]

- telegram-bot:
    build: .
    depends_on: [qdrant, redis, bge-m3]
    env_file: .env

- mlflow:
    image: ghcr.io/mlflow/mlflow:latest
    ports: [5000:5000]

- langfuse:
    image: langfuse/langfuse:latest
    ports: [3001:3000]

Status: ❌ ROADMAP Task 3.2 (High Priority)
```

**Deliverables:**
- [x] docker-compose.yml with all services
- [ ] docker-compose.override.yml for dev
- [ ] README section on docker-compose usage
- [ ] Test: `docker-compose up -d` (requires Docker Desktop)

---

#### L1.2 GitHub Actions CI/CD Pipeline (3-4 hours)
**Why Local:** YAML configuration files

```yaml
# Create: .github/workflows/ci.yml
name: CI/CD Pipeline

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
      - run: pip install -r requirements.txt
      - run: pytest tests/ --cov
      - run: ruff check .

  build:
    runs-on: ubuntu-latest
    steps:
      - uses: docker/build-push-action@v5
        with:
          push: true
          tags: ghcr.io/${{ github.repository }}:latest

Status: ❌ ROADMAP Task 3.3
```

**Deliverables:**
- [ ] .github/workflows/ci.yml (test + lint)
- [ ] .github/workflows/deploy.yml (build + push)
- [ ] GitHub Secrets configured
- [ ] Badges in README.md

---

#### L1.3 pytest Configuration & Fixtures (2-3 hours)
**Why Local:** Test infrastructure setup

```python
# Create: pytest.ini, conftest.py
Files:
- pytest.ini (test discovery, coverage config)
- conftest.py (shared fixtures)
- tests/unit/ (unit tests with mocks)
- tests/integration/ (real service tests)

Status: ❌ ROADMAP Phase 4
```

**Deliverables:**
- [ ] pytest.ini configured
- [ ] conftest.py with fixtures (mock_redis, mock_qdrant, etc.)
- [ ] Test structure created
- [ ] Coverage reporting enabled

---

### Priority 2: Testing Implementation 🟡

#### L2.1 Unit Tests - Cache Service (4-5 hours)
**Why Local:** Mock Redis, no real services needed

```python
# Create: tests/unit/test_cache_service.py
Coverage: 23 test cases for ~85% coverage

Tests:
- Semantic cache hit/miss/threshold
- Embeddings cache hit/miss/TTL
- Query analyzer cache
- Search results cache
- Conversation memory
- Metrics calculation
- Graceful degradation

Mocking: Use fakeredis or unittest.mock
```

**Deliverables:**
- [ ] tests/unit/test_cache_service.py (23 tests)
- [ ] 85% coverage for cache.py
- [ ] All tests passing with mocks

---

#### L2.2 Unit Tests - LLM Service (3-4 hours)
**Why Local:** Mock httpx client

```python
# Create: tests/unit/test_llm_service.py
Coverage: 17 test cases for ~80% coverage

Tests:
- Answer generation (success, timeout, errors)
- Streaming (chunk-by-chunk, errors)
- Fallback answers
- Context formatting

Mocking: Mock httpx.AsyncClient
```

**Deliverables:**
- [ ] tests/unit/test_llm_service.py (17 tests)
- [ ] 80% coverage for llm.py
- [ ] Mock streaming responses

---

#### L2.3 Unit Tests - Retriever Service (3 hours)
**Why Local:** Mock Qdrant client

```python
# Create: tests/unit/test_retriever_service.py
Coverage: 14 test cases for ~75% coverage

Tests:
- Search with filters (price, rooms, city)
- Filter building (exact, range, multiple)
- Graceful degradation
- Health checks

Mocking: Mock QdrantClient
```

**Deliverables:**
- [ ] tests/unit/test_retriever_service.py (14 tests)
- [ ] 75% coverage for retriever.py
- [ ] Mock Qdrant responses

---

#### L2.4 Integration Tests - RAG Pipeline (4-5 hours)
**Why Local:** Use docker-compose for real services

```python
# Create: tests/integration/test_rag_pipeline.py
Coverage: 8 test cases

Tests:
- Full query → answer flow
- Cache hit/miss scenarios
- Multi-turn conversations
- Performance benchmarks

Requires: docker-compose up (Qdrant, Redis, BGE-M3)
```

**Deliverables:**
- [ ] tests/integration/test_rag_pipeline.py (8 tests)
- [ ] Requires docker-compose running
- [ ] Test data fixtures
- [ ] Performance baselines documented

---

#### L2.5 Integration Tests - Graceful Degradation (3 hours)
**Why Local:** Test service failures with docker-compose

```python
# Create: tests/integration/test_graceful_degradation.py
Coverage: 8 test cases

Tests:
- Bot works without Redis (no cache)
- Bot works without Qdrant (fallback message)
- Bot works without LLM (search results only)
- Timeout handling

Requires: Ability to stop services during test
```

**Deliverables:**
- [ ] tests/integration/test_graceful_degradation.py (8 tests)
- [ ] Service failure simulation
- [ ] Verify fallback messages

---

### Priority 3: Documentation & Quality 🟢

#### L3.1 Code Quality Tools Setup (2 hours)
**Why Local:** Configuration files

```bash
# Create: .pre-commit-config.yaml, pyproject.toml
Tools:
- ruff (linting + formatting, replaces black + flake8)
- mypy (type checking)
- pre-commit hooks

Commands:
pip install ruff mypy pre-commit
pre-commit install

Status: ⏳ Mentioned in docs but not configured
```

**Deliverables:**
- [ ] .pre-commit-config.yaml
- [ ] pyproject.toml with ruff config
- [ ] mypy.ini for type checking
- [ ] Pre-commit hooks working

---

#### L3.2 API Documentation Generation (2-3 hours)
**Why Local:** Extract docstrings → docs

```bash
# Create: docs/api/ using Sphinx or mkdocs
Tools:
- Sphinx with autodoc
- Or mkdocs with mkdocstrings

Generate from:
- src/ modules
- telegram_bot/ modules

Status: ❌ Only manual docs exist
```

**Deliverables:**
- [ ] Sphinx/mkdocs configuration
- [ ] Auto-generated API docs
- [ ] Hosted on GitHub Pages or ReadTheDocs

---

#### L3.3 Load Testing Scripts (2-3 hours)
**Why Local:** Scripts can be written locally, run on server

```python
# Create: tests/load/locustfile.py
Framework: Locust or Playwright

Scenarios:
- 10 concurrent users
- 100 queries/minute
- Cache cold-start
- Peak load simulation

Run on server: locust -f tests/load/locustfile.py --host http://localhost
```

**Deliverables:**
- [ ] tests/load/locustfile.py
- [ ] Load test scenarios documented
- [ ] Performance benchmarks (run on server, see S2.1)

---

#### L3.4 User Feedback Loop - Telegram Inline Buttons (3-4 hours)
**Why Local:** Bot code modification

```python
# Modify: telegram_bot/bot.py
Add:
- 👍/👎 inline buttons after each answer
- Store feedback in Redis
- /stats shows feedback metrics
- Export feedback to MLflow

Schema:
feedback:{user_id}:{message_id} = {
  "query": "...",
  "answer": "...",
  "rating": 1 or -1,
  "timestamp": "..."
}

Status: ⏳ ROADMAP Phase 4 (Nice-to-have)
```

**Deliverables:**
- [ ] InlineKeyboard with 👍/👎 buttons
- [ ] Callback handler for feedback
- [ ] Feedback storage in Redis
- [ ] /stats command shows feedback

---

### Priority 4: Performance Optimizations 🟢

#### L4.1 Connection Pooling Implementation (3-4 hours)
**Why Local:** Code modification

```python
# Modify: telegram_bot/services/retriever.py, cache.py
Add:
- QdrantClient with connection pooling
- Redis connection pool (aioredis)
- Tune pool sizes (min=5, max=20)

Changes:
- RetrieverService: Use QdrantConnectionPool
- CacheService: Use redis.ConnectionPool

Status: ⏳ ROADMAP Task 3.1
```

**Deliverables:**
- [ ] Qdrant connection pool configured
- [ ] Redis connection pool configured
- [ ] Pool size tuned (benchmark on server)
- [ ] Reduced connection overhead

---

#### L4.2 AsyncQdrantClient Migration (3-4 hours)
**Why Local:** Code refactoring

```python
# Migrate: telegram_bot/services/retriever.py
Change:
from qdrant_client import QdrantClient
to
from qdrant_client import AsyncQdrantClient

Update:
- All search() calls to async
- Connection initialization to async
- Error handling for async context

Status: ⏳ ROADMAP Task 3.4
```

**Deliverables:**
- [ ] Migrated to AsyncQdrantClient
- [ ] All methods properly async
- [ ] Tests updated
- [ ] Latency improvement measured

---

#### L4.3 Prometheus Metrics Endpoint (2-3 hours)
**Why Local:** Code addition

```python
# Create: telegram_bot/metrics.py
Add:
- /metrics endpoint using prometheus_client
- Metrics:
  * rag_query_total (counter)
  * rag_query_latency_seconds (histogram)
  * rag_cache_hit_rate (gauge)
  * rag_llm_tokens_total (counter)
  * rag_errors_total (counter)

Status: ⏳ ROADMAP Task 4.1
```

**Deliverables:**
- [ ] prometheus_client integration
- [ ] /metrics endpoint exposed (port 8000?)
- [ ] 5-10 key metrics tracked
- [ ] Grafana can scrape metrics

---

#### L4.4 Distributed Lock for Semantic Cache (2 hours)
**Why Local:** Redis lock implementation

```python
# Modify: telegram_bot/services/cache.py
Add:
- Redis distributed lock (SETNX)
- Lock during semantic cache write
- Prevent race conditions

Pattern:
lock_key = f"lock:semantic:{hash}"
if await redis.set(lock_key, 1, nx=True, ex=5):
    # Write to cache
    await redis.delete(lock_key)

Status: ⏳ ROADMAP Task 2.2 (High Priority)
```

**Deliverables:**
- [ ] Distributed lock implemented
- [ ] Race condition tests
- [ ] Lock timeout handling

---

## 📋 HYBRID TASKS (Нужны оба места)

### H1. End-to-End Testing (4-5 hours)
**Phase 1 (Local):** Write tests with mocks
**Phase 2 (Server):** Run tests against real services

```python
# Local: Write tests/e2e/test_full_pipeline.py
# Server: Run with real Qdrant, Redis, BGE-M3, LLM

Test scenarios:
- User sends query → receives answer
- Cache hit path (2nd identical query)
- Multi-turn conversation
- Service failure recovery

Location: Write locally, execute on server
```

---

### H2. Documentation Updates (Ongoing)
**Local:** Write docs, commit to git
**Server:** Verify accuracy against production

```markdown
# Update after each feature:
- README.md
- CHANGELOG.md
- ROADMAP.md (mark completed)
- docs/ technical guides

Verify: Match code reality on server
```

---

## 🎯 RECOMMENDED WORKFLOW

### Week 1: Local Development
```bash
Priority 1 - Local:
Day 1: docker-compose.yml creation (L1.1)
Day 2: pytest setup + fixtures (L1.3)
Day 3: Unit tests - Cache (L2.1)
Day 4: Unit tests - LLM (L2.2)
Day 5: Unit tests - Retriever (L2.3)

Deliverables:
✅ docker-compose.yml
✅ 70%+ test coverage
✅ pytest infrastructure
```

### Week 2: Server Deployment
```bash
Priority 1 - Server:
Day 1: Deploy BGE-M3 service (S1.1)
Day 2: Deploy MLflow + Langfuse (S1.2, S1.3)
Day 3: Integration tests on server (L2.4, L2.5)
Day 4: Load testing (S2.1)
Day 5: Backup strategy (S2.2)

Deliverables:
✅ All services running on VPS
✅ Integration tests passing
✅ Performance benchmarks
```

### Week 3: CI/CD & Monitoring
```bash
Priority 1 - Local + Server:
Day 1-2: GitHub Actions (L1.2)
Day 3: Prometheus metrics (L4.3)
Day 4-5: Prometheus + Grafana on server (S1.4)

Deliverables:
✅ CI/CD pipeline
✅ Monitoring dashboards
✅ 100% production ready
```

---

## ⚖️ TASK DISTRIBUTION SUMMARY

### Server Tasks (Must deploy there)
- **Total:** 8 tasks
- **Time:** ~15-20 hours
- **Critical:** BGE-M3, MLflow, Langfuse, Load testing

### Local Tasks (Can do in WSL)
- **Total:** 14 tasks
- **Time:** ~40-50 hours
- **Critical:** docker-compose, CI/CD, Unit tests

### Hybrid Tasks (Both places)
- **Total:** 2 tasks
- **Time:** ~5-10 hours

---

## 🚀 GETTING STARTED

### To Start Local Development:
```bash
cd /mnt/c/Users/user/Documents/Сайты/Раг
git pull origin main

# Pick first task:
# L1.1 - Create docker-compose.yml
touch docker-compose.yml
# Start writing services...
```

### To Access Server:
```bash
# SSH to VPS
ssh admin@your-server-ip

cd /home/admin/contextual_rag
git pull origin main

# Check running services
docker ps
systemctl status telegram-bot

# Deploy new code
./deploy.sh
```

---

**Last Updated:** 2025-01-06
**Total Tasks:** 24 (8 server, 14 local, 2 hybrid)
**Estimated Effort:** 60-80 hours to 100% completion

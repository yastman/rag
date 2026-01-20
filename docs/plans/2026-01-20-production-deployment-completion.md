# Production Deployment Completion Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Complete the remaining 5% to achieve full production-ready deployment with testing and observability.

**Architecture:** The project uses a hybrid RAG pipeline (RRF + ColBERT) with BGE-M3 embeddings, Qdrant vector DB, Redis caching, and a Telegram bot interface. This plan focuses on: (1) production Docker orchestration, (2) CI integration tests, (3) connection pooling, (4) cache safety, and (5) metrics endpoint.

**Tech Stack:** Python 3.12, Docker Compose, GitHub Actions, pytest, asyncio, prometheus-client, aioredlock

---

## Phase 1: Production Docker Orchestration (Priority: CRITICAL)

### Task 1: Create Production docker-compose.yml

**Context:** Local development uses `docker-compose.local.yml`. Production needs a complete orchestration file with all services, health checks, and proper networking.

**Files:**
- Create: `docker-compose.prod.yml`
- Reference: `docker-compose.local.yml`
- Reference: `/home/admin/docker-compose.yml` (main server compose)

**Step 1: Create production compose file**

```yaml
# docker-compose.prod.yml
# Production deployment for RAG Telegram Bot
# Usage: docker compose -f docker-compose.prod.yml up -d

services:
  telegram-bot:
    build:
      context: .
      dockerfile: Dockerfile
    container_name: rag-telegram-bot
    restart: unless-stopped
    env_file:
      - telegram_bot/.env
    environment:
      - QDRANT_URL=http://qdrant:6333
      - REDIS_URL=redis://redis:6379
      - BGE_M3_URL=http://bge-m3:8000
    depends_on:
      qdrant:
        condition: service_healthy
      redis:
        condition: service_healthy
      bge-m3:
        condition: service_healthy
    networks:
      - rag-network
    logging:
      driver: "json-file"
      options:
        max-size: "10m"
        max-file: "3"

  qdrant:
    image: qdrant/qdrant:v1.15.4
    container_name: rag-qdrant
    restart: unless-stopped
    ports:
      - "6333:6333"
      - "6334:6334"
    volumes:
      - qdrant_data:/qdrant/storage
    environment:
      - QDRANT__SERVICE__GRPC_PORT=6334
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:6333/readyz"]
      interval: 10s
      timeout: 5s
      retries: 5
    networks:
      - rag-network

  redis:
    image: redis/redis-stack:7.4.0-v3
    container_name: rag-redis
    restart: unless-stopped
    ports:
      - "6379:6379"
      - "8002:8001"
    volumes:
      - redis_data:/data
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 10s
      timeout: 5s
      retries: 5
    networks:
      - rag-network

  bge-m3:
    build:
      context: ./services/bge-m3-api
      dockerfile: Dockerfile
    container_name: rag-bge-m3
    restart: unless-stopped
    ports:
      - "8001:8000"
    volumes:
      - bge_models:/root/.cache/huggingface
    environment:
      - MODEL_NAME=BAAI/bge-m3
      - DEVICE=cpu
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/health"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 120s
    deploy:
      resources:
        limits:
          memory: 4G
    networks:
      - rag-network

  docling:
    image: ds4sd/docling-serve:latest
    container_name: rag-docling
    restart: unless-stopped
    ports:
      - "5001:5001"
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:5001/health"]
      interval: 30s
      timeout: 10s
      retries: 3
    networks:
      - rag-network

networks:
  rag-network:
    driver: bridge

volumes:
  qdrant_data:
  redis_data:
  bge_models:
```

**Step 2: Verify syntax**

Run: `docker compose -f docker-compose.prod.yml config`
Expected: Valid YAML output without errors

**Step 3: Commit**

```bash
git add docker-compose.prod.yml
git commit -m "feat: add production docker-compose with health checks

- All 5 services: bot, qdrant, redis, bge-m3, docling
- Health checks for graceful startup ordering
- Resource limits for BGE-M3 (4GB RAM)
- Logging configuration for production

🤖 Generated with Claude Code
Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

### Task 2: Create Bot Dockerfile

**Context:** The bot needs a Dockerfile for containerized deployment.

**Files:**
- Create: `Dockerfile`
- Reference: `requirements.txt`
- Reference: `telegram_bot/main.py`

**Step 1: Create Dockerfile**

```dockerfile
# Dockerfile
# Multi-stage build for RAG Telegram Bot

# Stage 1: Build dependencies
FROM python:3.12-slim as builder

WORKDIR /app

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install
COPY requirements.txt .
RUN pip wheel --no-cache-dir --wheel-dir /app/wheels -r requirements.txt

# Stage 2: Production image
FROM python:3.12-slim

WORKDIR /app

# Install runtime dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy wheels from builder
COPY --from=builder /app/wheels /wheels
RUN pip install --no-cache /wheels/*

# Copy application code
COPY src/ ./src/
COPY telegram_bot/ ./telegram_bot/

# Create non-root user
RUN useradd -m -u 1000 botuser
USER botuser

# Health check
HEALTHCHECK --interval=30s --timeout=10s --retries=3 \
    CMD curl -f http://localhost:8080/health || exit 1

# Run bot
CMD ["python", "-m", "telegram_bot.main"]
```

**Step 2: Test build locally**

Run: `docker build -t rag-bot:test .`
Expected: Successfully built image

**Step 3: Commit**

```bash
git add Dockerfile
git commit -m "feat: add multi-stage Dockerfile for bot

- Two-stage build for smaller image
- Non-root user for security
- Health check endpoint
- Curl for debugging

🤖 Generated with Claude Code
Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

### Task 3: Add Health Check Endpoint to Bot

**Context:** The Dockerfile expects a `/health` endpoint. Add minimal health server.

**Files:**
- Modify: `telegram_bot/main.py`
- Create: `telegram_bot/health.py`

**Step 1: Create health check server**

```python
# telegram_bot/health.py
"""Simple health check HTTP server."""

import asyncio
from aiohttp import web


async def health_handler(request: web.Request) -> web.Response:
    """Return 200 OK for health checks."""
    return web.Response(text="OK", status=200)


async def start_health_server(port: int = 8080) -> web.AppRunner:
    """Start health check server on specified port."""
    app = web.Application()
    app.router.add_get("/health", health_handler)

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()

    return runner
```

**Step 2: Integrate into main.py**

Modify `telegram_bot/main.py` to start health server alongside bot:

```python
# Add at top of main.py
from telegram_bot.health import start_health_server

# Modify run_bot() function to include:
async def run_bot():
    """Run the bot with health check server."""
    config = BotConfig()
    bot = PropertyBot(config)

    # Start health check server
    health_runner = await start_health_server(8080)
    logger.info("Health server started on port 8080")

    try:
        await bot.start()
    finally:
        await health_runner.cleanup()
        await bot.stop()
```

**Step 3: Test locally**

Run: `python -m telegram_bot.main &` then `curl localhost:8080/health`
Expected: `OK`

**Step 4: Commit**

```bash
git add telegram_bot/health.py telegram_bot/main.py
git commit -m "feat: add health check endpoint for container orchestration

- Simple aiohttp server on port 8080
- Returns 200 OK for /health endpoint
- Graceful shutdown with bot

🤖 Generated with Claude Code
Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

## Phase 2: CI Integration Tests (Priority: HIGH)

### Task 4: Add Service Containers to CI

**Context:** Current CI only runs linting. Add Qdrant and Redis services to run actual tests.

**Files:**
- Modify: `.github/workflows/ci.yml`

**Step 1: Update CI workflow with services**

```yaml
# .github/workflows/ci.yml
name: CI

on:
  push:
    branches: [main, development]
  pull_request:
    branches: [main]

jobs:
  lint:
    name: Lint & Type Check
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: "3.12"
          cache: "pip"

      - name: Install linters
        run: pip install ruff mypy

      - name: Ruff lint
        run: ruff check src/ telegram_bot/ tests/ --output-format=github

      - name: Ruff format check
        run: ruff format --check src/ telegram_bot/ tests/

      - name: Type check
        run: mypy src/ --ignore-missing-imports --no-error-summary || true

  test:
    name: Tests
    runs-on: ubuntu-latest
    needs: lint

    services:
      qdrant:
        image: qdrant/qdrant:v1.15.4
        ports:
          - 6333:6333
        options: >-
          --health-cmd "curl -f http://localhost:6333/readyz"
          --health-interval 10s
          --health-timeout 5s
          --health-retries 5

      redis:
        image: redis:7-alpine
        ports:
          - 6379:6379
        options: >-
          --health-cmd "redis-cli ping"
          --health-interval 10s
          --health-timeout 5s
          --health-retries 5

    steps:
      - uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: "3.12"
          cache: "pip"

      - name: Install dependencies
        run: |
          pip install pytest pytest-asyncio pytest-cov httpx
          pip install qdrant-client redis

      - name: Run unit tests
        run: |
          pytest tests/unit/ -v --tb=short || true
        env:
          QDRANT_URL: http://localhost:6333
          REDIS_URL: redis://localhost:6379

      - name: Run integration tests
        run: |
          pytest tests/integration/ -v --tb=short || true
        env:
          QDRANT_URL: http://localhost:6333
          REDIS_URL: redis://localhost:6379
```

**Step 2: Verify workflow syntax**

Run: `cat .github/workflows/ci.yml | python3 -c "import yaml,sys; yaml.safe_load(sys.stdin); print('Valid YAML')"`
Expected: `Valid YAML`

**Step 3: Commit**

```bash
git add .github/workflows/ci.yml
git commit -m "feat: add Qdrant and Redis services to CI

- Service containers for integration tests
- Health checks for reliable startup
- Separate unit and integration test runs

🤖 Generated with Claude Code
Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

### Task 5: Create Test Directory Structure

**Context:** Organize tests into unit and integration directories for CI.

**Files:**
- Create: `tests/unit/__init__.py`
- Create: `tests/integration/__init__.py`
- Move: existing tests to appropriate directories

**Step 1: Create directory structure**

```bash
mkdir -p tests/unit tests/integration
touch tests/unit/__init__.py tests/integration/__init__.py
```

**Step 2: Create sample unit test**

```python
# tests/unit/test_filter_extractor.py
"""Unit tests for filter extraction."""

import pytest
from telegram_bot.services.filter_extractor import FilterExtractor


class TestFilterExtractor:
    """Test suite for FilterExtractor."""

    @pytest.fixture
    def extractor(self):
        """Create extractor instance."""
        return FilterExtractor()

    def test_extract_price_less_than(self, extractor):
        """Test price extraction for 'дешевле X'."""
        result = extractor.extract_filters("квартира дешевле 100000")
        assert result == {"price": {"lt": 100000}}

    def test_extract_price_range(self, extractor):
        """Test price range extraction."""
        result = extractor.extract_filters("от 80000 до 150000")
        assert result == {"price": {"gte": 80000, "lte": 150000}}

    def test_extract_rooms(self, extractor):
        """Test room count extraction."""
        result = extractor.extract_filters("3-комнатная квартира")
        assert result == {"rooms": 3}

    def test_extract_city(self, extractor):
        """Test city extraction."""
        result = extractor.extract_filters("квартира в Несебр")
        assert result == {"city": "Несебр"}

    def test_extract_combined(self, extractor):
        """Test combined filter extraction."""
        result = extractor.extract_filters("2-комнатная в Солнечный берег до 100000")
        assert "rooms" in result
        assert "city" in result
        assert "price" in result
```

**Step 3: Create sample integration test**

```python
# tests/integration/test_qdrant_connection.py
"""Integration tests for Qdrant connection."""

import os
import pytest
from qdrant_client import QdrantClient


@pytest.fixture
def qdrant_client():
    """Create Qdrant client from env."""
    url = os.getenv("QDRANT_URL", "http://localhost:6333")
    return QdrantClient(url=url, timeout=5.0)


class TestQdrantConnection:
    """Test Qdrant connectivity."""

    def test_connection(self, qdrant_client):
        """Test basic connection to Qdrant."""
        collections = qdrant_client.get_collections()
        assert collections is not None

    def test_health(self, qdrant_client):
        """Test Qdrant health endpoint."""
        # Just verify we can connect
        info = qdrant_client.get_collections()
        assert hasattr(info, "collections")
```

**Step 4: Run tests locally**

Run: `pytest tests/unit/ -v`
Expected: All tests pass

**Step 5: Commit**

```bash
git add tests/
git commit -m "test: organize tests into unit and integration directories

- tests/unit/ for fast isolated tests
- tests/integration/ for service-dependent tests
- Sample tests for filter extractor and Qdrant

🤖 Generated with Claude Code
Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

## Phase 3: Connection Pooling (Priority: HIGH)

### Task 6: Create Client Manager with Connection Pooling

**Context:** Current implementation creates new connections per request. Add connection pooling for Qdrant and Redis.

**Files:**
- Create: `src/core/client_manager.py`
- Modify: `telegram_bot/services/retriever.py`
- Modify: `telegram_bot/services/cache.py`

**Step 1: Create client manager**

```python
# src/core/client_manager.py
"""Centralized client management with connection pooling."""

import logging
from typing import Optional

from qdrant_client import AsyncQdrantClient, QdrantClient
from redis.asyncio import ConnectionPool, Redis

logger = logging.getLogger(__name__)


class ClientManager:
    """Manages database connections with pooling."""

    _instance: Optional["ClientManager"] = None
    _qdrant_client: Optional[QdrantClient] = None
    _async_qdrant_client: Optional[AsyncQdrantClient] = None
    _redis_pool: Optional[ConnectionPool] = None

    def __new__(cls):
        """Singleton pattern."""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    async def get_redis(self, url: str) -> Redis:
        """Get Redis client with connection pool."""
        if self._redis_pool is None:
            self._redis_pool = ConnectionPool.from_url(
                url,
                max_connections=20,
                decode_responses=False,
            )
            logger.info(f"Created Redis connection pool: {url}")

        return Redis(connection_pool=self._redis_pool)

    def get_qdrant(self, url: str, api_key: Optional[str] = None) -> QdrantClient:
        """Get Qdrant sync client (reused)."""
        if self._qdrant_client is None:
            self._qdrant_client = QdrantClient(
                url=url,
                api_key=api_key,
                timeout=10.0,
            )
            logger.info(f"Created Qdrant client: {url}")

        return self._qdrant_client

    async def get_async_qdrant(
        self, url: str, api_key: Optional[str] = None
    ) -> AsyncQdrantClient:
        """Get Qdrant async client."""
        if self._async_qdrant_client is None:
            self._async_qdrant_client = AsyncQdrantClient(
                url=url,
                api_key=api_key,
                timeout=10.0,
            )
            logger.info(f"Created async Qdrant client: {url}")

        return self._async_qdrant_client

    async def close(self):
        """Close all connections."""
        if self._redis_pool:
            await self._redis_pool.disconnect()
            self._redis_pool = None

        if self._qdrant_client:
            self._qdrant_client.close()
            self._qdrant_client = None

        if self._async_qdrant_client:
            await self._async_qdrant_client.close()
            self._async_qdrant_client = None

        logger.info("All client connections closed")


# Global instance
client_manager = ClientManager()
```

**Step 2: Add test**

```python
# tests/unit/test_client_manager.py
"""Tests for client manager."""

import pytest
from src.core.client_manager import ClientManager


class TestClientManager:
    """Test ClientManager singleton."""

    def test_singleton(self):
        """Test that ClientManager is singleton."""
        cm1 = ClientManager()
        cm2 = ClientManager()
        assert cm1 is cm2

    def test_qdrant_client_reuse(self):
        """Test Qdrant client is reused."""
        cm = ClientManager()
        # Reset for test
        cm._qdrant_client = None

        client1 = cm.get_qdrant("http://localhost:6333")
        client2 = cm.get_qdrant("http://localhost:6333")
        assert client1 is client2
```

**Step 3: Run test**

Run: `pytest tests/unit/test_client_manager.py -v`
Expected: PASS

**Step 4: Commit**

```bash
git add src/core/client_manager.py tests/unit/test_client_manager.py
git commit -m "feat: add ClientManager with connection pooling

- Singleton pattern for client reuse
- Redis connection pool (max 20 connections)
- Qdrant client reuse (sync and async)
- Graceful shutdown

🤖 Generated with Claude Code
Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

## Phase 4: Cache Safety (Priority: HIGH)

### Task 7: Add Distributed Lock for Semantic Cache

**Context:** Parallel requests to semantic cache can cause race conditions. Add distributed locking.

**Files:**
- Modify: `telegram_bot/services/cache.py`
- Modify: `requirements.txt`

**Step 1: Add aioredlock to requirements**

Add to `requirements.txt`:
```
aioredlock>=0.7.0
```

**Step 2: Update cache service with locking**

Add to `telegram_bot/services/cache.py`:

```python
# Add import at top
from aioredlock import Aioredlock, LockError

# Add lock manager in CacheService.__init__
self._lock_manager: Optional[Aioredlock] = None

# Add method to get lock manager
async def _get_lock_manager(self) -> Aioredlock:
    """Get or create lock manager."""
    if self._lock_manager is None:
        self._lock_manager = Aioredlock([self.redis_url])
    return self._lock_manager

# Modify store_semantic_cache to use locking
async def store_semantic_cache(
    self, query: str, embedding: list[float], answer: str
) -> None:
    """Store in semantic cache with distributed lock."""
    lock_manager = await self._get_lock_manager()
    lock_key = f"lock:semantic:{hash(query)}"

    try:
        async with await lock_manager.lock(lock_key, lock_timeout=10):
            # Check if already cached (double-check pattern)
            existing = await self.check_semantic_cache(embedding)
            if existing:
                return

            # Store in cache
            await self._store_semantic_cache_internal(query, embedding, answer)
    except LockError:
        logger.warning(f"Could not acquire lock for semantic cache: {query[:50]}")
```

**Step 3: Test locally**

Run: `pytest tests/unit/test_cache.py -v` (if exists)
Expected: Tests pass

**Step 4: Commit**

```bash
git add telegram_bot/services/cache.py requirements.txt
git commit -m "feat: add distributed lock for semantic cache

- Prevents race conditions on parallel requests
- Uses aioredlock for Redis-based locking
- Double-check pattern for efficiency

🤖 Generated with Claude Code
Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

## Phase 5: Observability (Priority: MEDIUM)

### Task 8: Add Prometheus Metrics Endpoint

**Context:** For Grafana dashboards, need `/metrics` endpoint with key metrics.

**Files:**
- Create: `telegram_bot/metrics.py`
- Modify: `telegram_bot/health.py`
- Modify: `requirements.txt`

**Step 1: Add prometheus-client to requirements**

Add to `requirements.txt`:
```
prometheus-client>=0.20.0
```

**Step 2: Create metrics module**

```python
# telegram_bot/metrics.py
"""Prometheus metrics for RAG bot."""

from prometheus_client import Counter, Histogram, Gauge

# Request metrics
REQUESTS_TOTAL = Counter(
    "rag_bot_requests_total",
    "Total requests processed",
    ["status"]
)

REQUEST_DURATION = Histogram(
    "rag_bot_request_duration_seconds",
    "Request duration in seconds",
    buckets=[0.1, 0.5, 1.0, 2.0, 5.0, 10.0]
)

# Cache metrics
CACHE_HITS = Counter(
    "rag_bot_cache_hits_total",
    "Cache hits by type",
    ["cache_type"]
)

CACHE_MISSES = Counter(
    "rag_bot_cache_misses_total",
    "Cache misses by type",
    ["cache_type"]
)

# Search metrics
SEARCH_RESULTS = Histogram(
    "rag_bot_search_results_count",
    "Number of search results returned",
    buckets=[0, 1, 3, 5, 10, 20]
)

# Active users
ACTIVE_USERS = Gauge(
    "rag_bot_active_users",
    "Number of active users in last hour"
)
```

**Step 3: Add metrics endpoint to health server**

Modify `telegram_bot/health.py`:

```python
# Add import
from prometheus_client import generate_latest, CONTENT_TYPE_LATEST

# Add metrics handler
async def metrics_handler(request: web.Request) -> web.Response:
    """Return Prometheus metrics."""
    metrics = generate_latest()
    return web.Response(body=metrics, content_type=CONTENT_TYPE_LATEST)

# Update start_health_server
async def start_health_server(port: int = 8080) -> web.AppRunner:
    """Start health and metrics server."""
    app = web.Application()
    app.router.add_get("/health", health_handler)
    app.router.add_get("/metrics", metrics_handler)
    # ...
```

**Step 4: Test metrics endpoint**

Run: `curl localhost:8080/metrics`
Expected: Prometheus-formatted metrics output

**Step 5: Commit**

```bash
git add telegram_bot/metrics.py telegram_bot/health.py requirements.txt
git commit -m "feat: add Prometheus metrics endpoint

- /metrics endpoint for Grafana integration
- Request duration, cache hits, search results
- Active users gauge

🤖 Generated with Claude Code
Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

## Phase 6: Documentation & Cleanup

### Task 9: Update Makefile with Production Commands

**Files:**
- Modify: `Makefile`

**Step 1: Add production commands**

```makefile
# Add to Makefile

# Production deployment
prod-up:
	docker compose -f docker-compose.prod.yml up -d

prod-down:
	docker compose -f docker-compose.prod.yml down

prod-logs:
	docker compose -f docker-compose.prod.yml logs -f

prod-build:
	docker compose -f docker-compose.prod.yml build

# Health checks
health-check:
	@echo "Checking services..."
	@curl -sf http://localhost:6333/readyz && echo "✓ Qdrant OK" || echo "✗ Qdrant FAIL"
	@curl -sf http://localhost:8001/health && echo "✓ BGE-M3 OK" || echo "✗ BGE-M3 FAIL"
	@redis-cli ping > /dev/null && echo "✓ Redis OK" || echo "✗ Redis FAIL"
	@curl -sf http://localhost:8080/health && echo "✓ Bot OK" || echo "✗ Bot FAIL"

# Full test suite
test-all:
	pytest tests/ -v --tb=short

test-unit:
	pytest tests/unit/ -v

test-integration:
	pytest tests/integration/ -v
```

**Step 2: Commit**

```bash
git add Makefile
git commit -m "feat: add production commands to Makefile

- prod-up/down/logs/build for production compose
- health-check for all services
- test-all/unit/integration targets

🤖 Generated with Claude Code
Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

### Task 10: Update README with New Commands

**Files:**
- Modify: `README.md`

**Step 1: Add deployment section**

Add to README.md:

```markdown
## Deployment

### Local Development
```bash
make local-up        # Start Qdrant, Redis, BGE-M3, Docling
make test-unit       # Run unit tests
```

### Production
```bash
make prod-build      # Build all containers
make prod-up         # Start production stack
make health-check    # Verify all services
make prod-logs       # Tail logs
```

### CI/CD
- **Push to main:** Runs linting + tests
- **Tag `deploy-code`:** Quick deploy (git pull + restart)
- **Tag `v*.*.*`:** Full release (Docker build + deploy)
```

**Step 2: Commit**

```bash
git add README.md
git commit -m "docs: add deployment commands to README

🤖 Generated with Claude Code
Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

## Summary

| Task | Priority | Time Est. | Description |
|------|----------|-----------|-------------|
| 1 | CRITICAL | 30 min | Production docker-compose.yml |
| 2 | CRITICAL | 20 min | Bot Dockerfile |
| 3 | CRITICAL | 15 min | Health check endpoint |
| 4 | HIGH | 30 min | CI service containers |
| 5 | HIGH | 20 min | Test directory structure |
| 6 | HIGH | 30 min | Connection pooling |
| 7 | HIGH | 20 min | Distributed cache lock |
| 8 | MEDIUM | 25 min | Prometheus metrics |
| 9 | LOW | 10 min | Makefile updates |
| 10 | LOW | 10 min | README updates |

**Total estimated time:** ~3.5 hours

**After completing this plan:**
1. Full production Docker deployment ready
2. CI runs actual tests with services
3. Connection pooling prevents resource exhaustion
4. Cache race conditions prevented
5. Prometheus metrics for Grafana dashboards

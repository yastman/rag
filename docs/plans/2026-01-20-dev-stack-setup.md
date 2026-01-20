# Dev Stack Setup Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Create a complete local development environment with 9 services (PostgreSQL, Redis, Qdrant, BGE-M3, Docling, LightRAG, Langfuse, MLflow, telegram-bot) that works out of the box with `docker compose up`.

**Architecture:** Single `docker-compose.dev.yml` file with all services. PostgreSQL serves as backend for Langfuse and MLflow. Qdrant stores vectors for LightRAG. BGE-M3 provides local embeddings. Default credentials allow immediate start without configuration.

**Tech Stack:** Docker Compose, PostgreSQL 17 + pgvector, Redis 8, Qdrant 1.16, LightRAG, Langfuse 2, MLflow 2.22, Python 3.11

---

## Task 1: Create PostgreSQL Init Directory Structure

**Files:**
- Create: `docker/postgres/init/00-init-databases.sql`

**Step 1: Create directory structure**

```bash
mkdir -p docker/postgres/init
```

**Step 2: Create init SQL script**

Create file `docker/postgres/init/00-init-databases.sql`:

```sql
-- Dev Stack: Auto-create databases for services
-- This script runs automatically on first PostgreSQL start

-- Database for Langfuse (LLM tracing)
CREATE DATABASE langfuse;

-- Database for MLflow (ML experiments)
CREATE DATABASE mlflow;

-- Grant permissions (using default postgres user)
GRANT ALL PRIVILEGES ON DATABASE langfuse TO postgres;
GRANT ALL PRIVILEGES ON DATABASE mlflow TO postgres;
```

**Step 3: Verify file created**

Run: `cat docker/postgres/init/00-init-databases.sql`
Expected: SQL content with CREATE DATABASE statements

**Step 4: Commit**

```bash
git add docker/postgres/init/00-init-databases.sql
git commit -m "feat: add PostgreSQL init script for Langfuse and MLflow databases

- Creates langfuse and mlflow databases on first start
- Grants permissions to postgres user

🤖 Generated with Claude Code
Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

## Task 2: Create MLflow Dockerfile

**Files:**
- Create: `docker/mlflow/Dockerfile`

**Step 1: Create directory**

```bash
mkdir -p docker/mlflow
```

**Step 2: Create Dockerfile**

Create file `docker/mlflow/Dockerfile`:

```dockerfile
FROM ghcr.io/mlflow/mlflow:v2.22.1

# Install PostgreSQL driver for backend store
RUN pip install --no-cache-dir psycopg2-binary==2.9.11

# Default port
EXPOSE 5000

# Healthcheck
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD python3 -c "import urllib.request; urllib.request.urlopen('http://localhost:5000/health')" || exit 1
```

**Step 3: Verify file created**

Run: `cat docker/mlflow/Dockerfile`
Expected: Dockerfile with FROM mlflow and pip install psycopg2-binary

**Step 4: Commit**

```bash
git add docker/mlflow/Dockerfile
git commit -m "feat: add MLflow Dockerfile with PostgreSQL support

- Based on official MLflow 2.22.1 image
- Adds psycopg2-binary for PostgreSQL backend

🤖 Generated with Claude Code
Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

## Task 3: Create docker-compose.dev.yml

**Files:**
- Create: `docker-compose.dev.yml`

**Step 1: Create docker-compose.dev.yml**

Create file `docker-compose.dev.yml`:

```yaml
# Dev Stack for RAG Bot Development
# Start: docker compose -f docker-compose.dev.yml up -d
# Stop:  docker compose -f docker-compose.dev.yml down
# Reset: docker compose -f docker-compose.dev.yml down -v

services:
  # =============================================================================
  # DATABASES
  # =============================================================================

  postgres:
    image: pgvector/pgvector:pg17
    container_name: dev-postgres
    ports:
      - "5432:5432"
    environment:
      POSTGRES_USER: postgres
      POSTGRES_PASSWORD: postgres
      POSTGRES_DB: postgres
    volumes:
      - postgres_data:/var/lib/postgresql/data
      - ./docker/postgres/init:/docker-entrypoint-initdb.d:ro
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U postgres"]
      interval: 10s
      timeout: 5s
      retries: 5
      start_period: 10s

  redis:
    image: redis:8-alpine
    container_name: dev-redis
    ports:
      - "6379:6379"
    volumes:
      - redis_data:/data
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 10s
      timeout: 5s
      retries: 3

  qdrant:
    image: qdrant/qdrant:v1.16
    container_name: dev-qdrant
    ports:
      - "6333:6333"
      - "6334:6334"
    volumes:
      - qdrant_data:/qdrant/storage
    environment:
      QDRANT__SERVICE__GRPC_PORT: 6334
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:6333/readyz"]
      interval: 10s
      timeout: 5s
      retries: 3

  # =============================================================================
  # AI SERVICES
  # =============================================================================

  bge-m3:
    build:
      context: ./services/bge-m3-api
      dockerfile: Dockerfile
    container_name: dev-bge-m3
    ports:
      - "8000:8000"
    volumes:
      - bge_models:/models
    environment:
      OMP_NUM_THREADS: 4
      MKL_NUM_THREADS: 4
      MODEL_CACHE_DIR: /models
    healthcheck:
      test: ["CMD", "python", "-c", "import requests; requests.get('http://localhost:8000/health', timeout=5)"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 120s
    deploy:
      resources:
        limits:
          memory: 4G

  docling:
    image: ghcr.io/docling-project/docling-serve-cpu:main
    container_name: dev-docling
    ports:
      - "5001:5001"
    environment:
      UVICORN_HOST: 0.0.0.0
      UVICORN_PORT: 5001
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:5001/health"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 120s
    deploy:
      resources:
        limits:
          memory: 4G

  lightrag:
    image: ghcr.io/hkuds/lightrag:v1.4.9.11
    container_name: dev-lightrag
    ports:
      - "9621:9621"
    environment:
      OPENAI_API_KEY: ${OPENAI_API_KEY:-sk-placeholder}
      LLM_BINDING: openai
      EMBEDDING_BINDING: openai
      LLM_MODEL: gpt-4o-mini
      EMBEDDING_MODEL: text-embedding-3-small
      EMBEDDING_DIM: 1536
    volumes:
      - lightrag_data:/app/lightrag_data
    healthcheck:
      test: ["CMD", "python", "-c", "import requests; requests.get('http://localhost:9621/health', timeout=5)"]
      interval: 30s
      timeout: 10s
      retries: 5
      start_period: 60s

  # =============================================================================
  # ML PLATFORM
  # =============================================================================

  langfuse:
    image: langfuse/langfuse:2
    container_name: dev-langfuse
    ports:
      - "3001:3000"
    environment:
      DATABASE_URL: postgresql://postgres:postgres@postgres:5432/langfuse
      NEXTAUTH_SECRET: dev-secret-change-in-production
      SALT: dev-salt-change-in-production
      NEXTAUTH_URL: http://localhost:3001
      TELEMETRY_ENABLED: "false"
      HOSTNAME: 0.0.0.0
    depends_on:
      postgres:
        condition: service_healthy
    healthcheck:
      test: ["CMD", "wget", "--no-verbose", "--tries=1", "--spider", "http://localhost:3000/api/public/health"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 60s

  mlflow:
    build:
      context: ./docker/mlflow
      dockerfile: Dockerfile
    container_name: dev-mlflow
    ports:
      - "5000:5000"
    environment:
      MLFLOW_BACKEND_STORE_URI: postgresql://postgres:postgres@postgres:5432/mlflow
      MLFLOW_DEFAULT_ARTIFACT_ROOT: /mlflow/artifacts
    volumes:
      - mlflow_artifacts:/mlflow/artifacts
    entrypoint: >
      mlflow server
      --backend-store-uri postgresql://postgres:postgres@postgres:5432/mlflow
      --default-artifact-root /mlflow/artifacts
      --host 0.0.0.0
      --port 5000
    depends_on:
      postgres:
        condition: service_healthy
    healthcheck:
      test: ["CMD", "python3", "-c", "import urllib.request; urllib.request.urlopen('http://localhost:5000/health')"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 60s

  # =============================================================================
  # BOT (optional - uncomment to run in container)
  # =============================================================================

  # bot:
  #   build:
  #     context: .
  #     dockerfile: Dockerfile
  #   container_name: dev-bot
  #   environment:
  #     TELEGRAM_BOT_TOKEN: ${TELEGRAM_BOT_TOKEN}
  #     REDIS_URL: redis://redis:6379
  #     QDRANT_URL: http://qdrant:6333
  #     BGE_M3_URL: http://bge-m3:8000
  #     OPENAI_API_KEY: ${OPENAI_API_KEY}
  #   depends_on:
  #     redis:
  #       condition: service_healthy
  #     qdrant:
  #       condition: service_healthy
  #     bge-m3:
  #       condition: service_healthy

# =============================================================================
# VOLUMES
# =============================================================================

volumes:
  postgres_data:
  redis_data:
  qdrant_data:
  bge_models:
  lightrag_data:
  mlflow_artifacts:
```

**Step 2: Verify file created**

Run: `head -50 docker-compose.dev.yml`
Expected: YAML content starting with services definition

**Step 3: Validate YAML syntax**

Run: `docker compose -f docker-compose.dev.yml config --quiet && echo "Valid YAML"`
Expected: "Valid YAML"

**Step 4: Commit**

```bash
git add docker-compose.dev.yml
git commit -m "feat: add docker-compose.dev.yml with full dev stack

Services included:
- PostgreSQL 17 + pgvector (port 5432)
- Redis 8 (port 6379)
- Qdrant 1.16 (port 6333)
- BGE-M3 embeddings (port 8000)
- Docling PDF parser (port 5001)
- LightRAG (port 9621)
- Langfuse LLM tracing (port 3001)
- MLflow experiments (port 5000)

Works out of the box with default credentials.

🤖 Generated with Claude Code
Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

## Task 4: Update .env.example

**Files:**
- Modify: `.env.example`

**Step 1: Add new environment variables**

Append to `.env.example`:

```bash
# =============================================================================
# DEV STACK CONFIGURATION
# =============================================================================

# Telegram Bot
TELEGRAM_BOT_TOKEN=your-telegram-bot-token

# LightRAG (uses OpenAI for LLM and embeddings)
# OPENAI_API_KEY is already defined above

# Langfuse (optional - for LLM tracing)
LANGFUSE_PUBLIC_KEY=pk-lf-dev
LANGFUSE_SECRET_KEY=sk-lf-dev
LANGFUSE_HOST=http://localhost:3001

# MLflow (optional - for experiment tracking)
MLFLOW_TRACKING_URI=http://localhost:5000
```

**Step 2: Verify changes**

Run: `tail -20 .env.example`
Expected: New DEV STACK CONFIGURATION section

**Step 3: Commit**

```bash
git add .env.example
git commit -m "feat: add dev stack environment variables to .env.example

- TELEGRAM_BOT_TOKEN for bot
- LANGFUSE_* for LLM tracing
- MLFLOW_TRACKING_URI for experiments

🤖 Generated with Claude Code
Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

## Task 5: Create LOCAL-DEVELOPMENT.md

**Files:**
- Create: `docs/LOCAL-DEVELOPMENT.md`

**Step 1: Create documentation file**

Create file `docs/LOCAL-DEVELOPMENT.md`:

```markdown
# Local Development Guide

Complete guide for running the RAG bot development environment locally.

## Requirements

- Docker 24+
- Docker Compose v2
- OpenAI API key (for LLM and embeddings)
- ~8GB RAM (BGE-M3 and Docling are memory-intensive)

## Quick Start

### 1. Clone and setup

```bash
git clone https://github.com/yastman/rag.git
cd rag
cp .env.example .env
```

### 2. Configure API keys

Edit `.env` and set:
```bash
OPENAI_API_KEY=sk-your-openai-key
TELEGRAM_BOT_TOKEN=your-telegram-bot-token  # optional
```

### 3. Start dev stack

```bash
docker compose -f docker-compose.dev.yml up -d
```

First start takes 5-10 minutes (downloading images, loading models).

### 4. Verify services

```bash
docker compose -f docker-compose.dev.yml ps
```

All services should show "healthy" status.

## Services

| Service | URL | Purpose |
|---------|-----|---------|
| PostgreSQL | localhost:5432 | Database (user: postgres, pass: postgres) |
| Redis | localhost:6379 | Cache |
| Qdrant | http://localhost:6333 | Vector database |
| Qdrant Dashboard | http://localhost:6333/dashboard | Qdrant UI |
| BGE-M3 | http://localhost:8000 | Embeddings API |
| Docling | http://localhost:5001 | PDF parser |
| LightRAG | http://localhost:9621 | RAG API |
| Langfuse | http://localhost:3001 | LLM tracing UI |
| MLflow | http://localhost:5000 | ML experiments UI |

## Common Commands

### View logs

```bash
# All services
docker compose -f docker-compose.dev.yml logs -f

# Specific service
docker compose -f docker-compose.dev.yml logs -f langfuse
```

### Restart service

```bash
docker compose -f docker-compose.dev.yml restart langfuse
```

### Stop all services

```bash
docker compose -f docker-compose.dev.yml down
```

### Reset all data (clean start)

```bash
docker compose -f docker-compose.dev.yml down -v
docker compose -f docker-compose.dev.yml up -d
```

## Running the Bot

### Option 1: Local Python (recommended for development)

```bash
# Activate virtual environment
source venv/bin/activate

# Install dependencies
pip install -e .

# Run bot
python -m telegram_bot.main
```

### Option 2: Docker container

Uncomment the `bot` service in `docker-compose.dev.yml` and run:

```bash
docker compose -f docker-compose.dev.yml up -d bot
```

## Using Langfuse for LLM Tracing

1. Open http://localhost:3001
2. Create account (first user becomes admin)
3. Create project and get API keys
4. Add to your code:

```python
from langfuse import Langfuse

langfuse = Langfuse(
    public_key="pk-lf-...",
    secret_key="sk-lf-...",
    host="http://localhost:3001"
)
```

## Using MLflow for Experiments

1. Open http://localhost:5000
2. Create experiment in UI or code:

```python
import mlflow

mlflow.set_tracking_uri("http://localhost:5000")
mlflow.set_experiment("my-experiment")

with mlflow.start_run():
    mlflow.log_param("model", "gpt-4o-mini")
    mlflow.log_metric("accuracy", 0.95)
```

## Troubleshooting

### Service won't start

```bash
# Check logs
docker compose -f docker-compose.dev.yml logs <service-name>

# Check resources
docker stats
```

### BGE-M3 slow to start

First start downloads ~2GB model. Check progress:

```bash
docker compose -f docker-compose.dev.yml logs -f bge-m3
```

### Database connection issues

Verify PostgreSQL is healthy:

```bash
docker compose -f docker-compose.dev.yml exec postgres pg_isready
```

### Port conflicts

If ports are in use, modify `docker-compose.dev.yml` port mappings:

```yaml
ports:
  - "5433:5432"  # Change left side (host port)
```
```

**Step 2: Verify file created**

Run: `head -50 docs/LOCAL-DEVELOPMENT.md`
Expected: Markdown content with Quick Start section

**Step 3: Commit**

```bash
git add docs/LOCAL-DEVELOPMENT.md
git commit -m "docs: add comprehensive local development guide

- Quick start instructions
- Service URLs and ports
- Common commands
- Langfuse and MLflow usage examples
- Troubleshooting section

🤖 Generated with Claude Code
Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

## Task 6: Update README.md Quick Start

**Files:**
- Modify: `README.md`

**Step 1: Find Quick Start section**

Run: `grep -n "Quick Start\|Getting Started\|Installation" README.md | head -5`
Expected: Line number of existing section

**Step 2: Add Dev Stack section after Quick Start**

Add after existing Quick Start section (or create if missing):

```markdown
## Dev Stack (Docker)

Full development environment with all services:

```bash
# Clone and setup
git clone https://github.com/yastman/rag.git
cd rag
cp .env.example .env
# Edit .env: add OPENAI_API_KEY

# Start all services
docker compose -f docker-compose.dev.yml up -d

# Check status
docker compose -f docker-compose.dev.yml ps
```

Services available:
- **Langfuse** (LLM tracing): http://localhost:3001
- **MLflow** (experiments): http://localhost:5000
- **LightRAG** (RAG API): http://localhost:9621
- **Qdrant** (vectors): http://localhost:6333/dashboard

See [docs/LOCAL-DEVELOPMENT.md](docs/LOCAL-DEVELOPMENT.md) for full guide.
```

**Step 3: Verify changes**

Run: `grep -A 20 "Dev Stack" README.md`
Expected: New Dev Stack section content

**Step 4: Commit**

```bash
git add README.md
git commit -m "docs: add Dev Stack quick start to README

- Docker compose command for full stack
- Links to service UIs
- Reference to detailed guide

🤖 Generated with Claude Code
Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

## Task 7: Test Dev Stack

**Files:**
- None (testing only)

**Step 1: Start the stack**

Run: `cd /home/admin/contextual_rag && docker compose -f docker-compose.dev.yml up -d`
Expected: All containers created and starting

**Step 2: Wait for services to be healthy**

Run: `sleep 60 && docker compose -f docker-compose.dev.yml ps`
Expected: All services show "healthy" or "running"

**Step 3: Test PostgreSQL**

Run: `docker compose -f docker-compose.dev.yml exec postgres psql -U postgres -c "\l" | grep -E "langfuse|mlflow"`
Expected: Both databases listed

**Step 4: Test Langfuse**

Run: `curl -s http://localhost:3001/api/public/health | head -1`
Expected: JSON response with status

**Step 5: Test MLflow**

Run: `curl -s http://localhost:5000/health`
Expected: OK or JSON health response

**Step 6: Test Qdrant**

Run: `curl -s http://localhost:6333/readyz`
Expected: Response indicating ready

**Step 7: Stop stack (cleanup)**

Run: `docker compose -f docker-compose.dev.yml down`
Expected: All containers stopped

---

## Task 8: Final Commit and Push

**Files:**
- None (git operations only)

**Step 1: Check status**

Run: `git status`
Expected: Clean working tree (all changes committed)

**Step 2: View commit history**

Run: `git log --oneline -10`
Expected: All commits from this plan visible

**Step 3: Push to remote**

Run: `git push origin main`
Expected: Push successful

---

## Summary

After completing all tasks:

| Component | Status |
|-----------|--------|
| `docker/postgres/init/00-init-databases.sql` | Created |
| `docker/mlflow/Dockerfile` | Created |
| `docker-compose.dev.yml` | Created |
| `.env.example` | Updated |
| `docs/LOCAL-DEVELOPMENT.md` | Created |
| `README.md` | Updated |
| Tests | Passed |
| Git | Pushed |

**Usage:**
```bash
git clone https://github.com/yastman/rag.git
cd rag
cp .env.example .env
# Edit .env with OPENAI_API_KEY
docker compose -f docker-compose.dev.yml up -d
```

# Local Development Setup - Full Stack Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Полностью локальная среда разработки RAG проекта со всеми сервисами в Docker.

**Architecture:** 4 сервиса в Docker (Qdrant + Redis + BGE-M3 + Docling). LLM APIs удалённые (Anthropic/OpenAI/Groq). Telegram бот запускается локально в venv.

**Tech Stack:** Docker Desktop (WSL2), Python 3.12, Qdrant v1.15.4, Redis Stack, BGE-M3 FastAPI, Docling, aiogram 3.15

**Working Directory:** `/mnt/c/Users/user/Documents/Сайты/rag-fresh`

---

## Архитектура

```
Docker (localhost):
├── Qdrant    :6333  - Vector DB
├── Redis     :6379  - Cache
├── BGE-M3    :8001  - Embeddings
└── Docling   :5001  - PDF Parser

Python venv:
└── telegram_bot.main → LLM APIs (remote)
```

---

## Phase 1: Git & Security

### Task 1.1: Fix .gitignore

**Step 1:** Add `.env.server` and `.env.production` to `.gitignore` section `# Sensitive files`

**Step 2:** Verify: `grep -E "\.env\.(local|server|production)" .gitignore`

---

### Task 1.2: Verify git credentials

**Step 1:** `git fetch origin` - should work without auth errors

---

## Phase 2: Docker Infrastructure

### Task 2.1: Create docker-compose.local.yml

```yaml
version: "3.8"

services:
  qdrant:
    image: qdrant/qdrant:v1.15.4
    container_name: rag-qdrant-local
    ports:
      - "6333:6333"
      - "6334:6334"
    volumes:
      - qdrant_storage:/qdrant/storage
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:6333/health"]
      interval: 10s
      timeout: 5s
      retries: 5
    restart: unless-stopped

  redis:
    image: redis/redis-stack:latest
    container_name: rag-redis-local
    ports:
      - "6379:6379"
      - "8002:8001"
    volumes:
      - redis_data:/data
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 10s
      timeout: 5s
      retries: 3
    restart: unless-stopped

  bge-m3:
    build:
      context: ./services/bge-m3-api
      dockerfile: Dockerfile
    container_name: rag-bge-m3-local
    ports:
      - "8001:8000"
    volumes:
      - bge_m3_models:/models
    environment:
      - PYTHONUNBUFFERED=1
      - OMP_NUM_THREADS=4
      - MKL_NUM_THREADS=4
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/health"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 120s
    restart: unless-stopped
    deploy:
      resources:
        limits:
          memory: 6G

  docling:
    image: ds4sd/docling-serve:latest
    container_name: rag-docling-local
    ports:
      - "5001:5000"
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:5000/health"]
      interval: 30s
      timeout: 10s
      retries: 3
    restart: unless-stopped

volumes:
  qdrant_storage:
  redis_data:
  bge_m3_models:
```

---

### Task 2.2: Build BGE-M3 image

```bash
docker compose -f docker-compose.local.yml build bge-m3
```

---

### Task 2.3: Start all services

```bash
docker compose -f docker-compose.local.yml up -d
docker compose -f docker-compose.local.yml ps
```

---

### Task 2.4: Verify health

```bash
curl -s http://localhost:6333/health  ***REMOVED***
docker exec rag-redis-local redis-cli ping  # Redis
curl -s http://localhost:8001/health  # BGE-M3
curl -s http://localhost:5001/health  # Docling
```

---

## Phase 3: Environment

### Task 3.1: Create .env.local

```bash
cp .env.local.example .env.local
```

Edit with API keys from `/tmp/env-backup.txt`:
- OPENAI_API_KEY
- ANTHROPIC_API_KEY
- GROQ_API_KEY
- TELEGRAM_BOT_TOKEN (from @BotFather)

---

### Task 3.2: Create symlink

```bash
ln -sf ../.env.local telegram_bot/.env
```

---

## Phase 4: Python

### Task 4.1: Create venv

```bash
python3 -m venv venv
source venv/bin/activate
```

---

### Task 4.2: Install dependencies

```bash
pip install --upgrade pip
pip install -r requirements.txt
```

---

## Phase 5: Linters

### Task 5.1: Update pre-commit

```bash
pip install pre-commit
pre-commit autoupdate
pre-commit install --install-hooks
```

---

### Task 5.2: Run linters

```bash
pre-commit run --all-files
git add -A  # if fixes applied
```

---

## Phase 6: Qdrant Collection

### Task 6.1: Create collection

```python
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams

client = QdrantClient(url='http://localhost:6333')
client.create_collection(
    collection_name='apartments_local',
    vectors_config={'dense': VectorParams(size=1024, distance=Distance.COSINE)}
)
```

---

## Phase 7: Verification

### Task 7.1: Test connections

```bash
source venv/bin/activate
export $(grep -v '^#' .env.local | grep -v '^$' | xargs)

python -c "
from qdrant_client import QdrantClient
import redis, httpx, os

QdrantClient(url=os.getenv('QDRANT_URL')).get_collections()
print('Qdrant OK')

redis.from_url(os.getenv('REDIS_URL')).ping()
print('Redis OK')

httpx.get(f\"{os.getenv('BGE_M3_URL')}/health\").json()
print('BGE-M3 OK')

httpx.get(f\"{os.getenv('DOCLING_URL')}/health\")
print('Docling OK')
"
```

---

### Task 7.2: Test bot

```bash
python -m telegram_bot.main
# Ctrl+C to stop
```

---

## Phase 8: Commit

### Task 8.1: Commit & push

```bash
git add docker-compose.local.yml .gitignore .pre-commit-config.yaml
git commit -m "feat: complete local dev setup with Qdrant+Redis+BGE-M3+Docling

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
git push origin main
```

---

## Quick Start

```bash
# Start
docker compose -f docker-compose.local.yml up -d
source venv/bin/activate
export $(grep -v '^#' .env.local | grep -v '^$' | xargs)
python -m telegram_bot.main

# Stop
# Ctrl+C
docker compose -f docker-compose.local.yml down
```

---

## Checklist

| Task | Description |
|------|-------------|
| 1.1 | Fix .gitignore |
| 1.2 | Verify git |
| 2.1 | Create docker-compose |
| 2.2 | Build BGE-M3 |
| 2.3 | Start services |
| 2.4 | Verify health |
| 3.1 | Create .env.local |
| 3.2 | Create symlink |
| 4.1 | Create venv |
| 4.2 | Install deps |
| 5.1 | Update pre-commit |
| 5.2 | Run linters |
| 6.1 | Create collection |
| 7.1 | Test connections |
| 7.2 | Test bot |
| 8.1 | Commit & push |

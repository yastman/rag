# Local Project Setup - Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Make the RAG project fully functional locally - from broken configuration to working Telegram bot with search.

**Architecture:** Fix configuration issues, install dev tools, create test infrastructure, index sample documents, verify all services, run end-to-end tests.

**Tech Stack:** Python 3.12, Docker Compose, Qdrant, Redis, BGE-M3, pytest, aiogram

---

## Task Tracking

**IMPORTANT:** Keep these files in sync as tasks are completed:

| File | Purpose | Update When |
|------|---------|-------------|
| `TODO.md` | Current sprint tasks | Task completed, new task discovered |
| `ROADMAP.md` | Phase progress | Phase completed, scope changed |
| This plan | Detailed steps | New steps needed, blockers found |

**After completing each task:**
1. Mark task done in this plan (add ✅)
2. Update TODO.md status
3. Commit changes

**If new task discovered:**
1. Add to this plan in appropriate phase
2. Add to TODO.md with priority
3. Update ROADMAP.md if affects phase progress

---

## Phase 1: Fix Configuration (4 tasks)

### Task 1.1: Fix BGE_M3_URL in .env.local ✅

**Problem:** Bot expects port 8001, but BGE-M3 service runs on port 8000.

**Files:**
- Modify: `.env.local`

**Step 1: Check current value**

Run: `grep BGE_M3_URL .env.local`
Expected: `BGE_M3_URL=http://localhost:8001`

**Step 2: Fix the port**

Run: `sed -i 's/BGE_M3_URL=http:\/\/localhost:8001/BGE_M3_URL=http:\/\/localhost:8000/' .env.local`

**Step 3: Verify fix**

Run: `grep BGE_M3_URL .env.local`
Expected: `BGE_M3_URL=http://localhost:8000`

**Step 4: Commit**

```bash
git add .env.local
git commit -m "fix(config): correct BGE_M3_URL port 8001 -> 8000"
```

---

### Task 1.2: Create .env symlink for src module ✅

**Problem:** `src/config/settings.py` expects `.env` in root, but we have `.env.local`

**Files:**
- Create: `.env` (symlink to `.env.local`)

**Step 1: Check current state**

Run: `ls -la .env 2>/dev/null || echo "No .env file"`
Expected: "No .env file"

**Step 2: Create symlink**

Run: `ln -s .env.local .env`

**Step 3: Verify symlink**

Run: `ls -la .env`
Expected: `.env -> .env.local`

**Step 4: Test settings import**

Run: `python3 -c "from dotenv import load_dotenv; load_dotenv(); from src.config.settings import settings; print('Settings OK')"`
Expected: "Settings OK" (or error about missing specific key, not file)

**Step 5: Add .env to .gitignore if not present**

Run: `grep -q "^\.env$" .gitignore || echo ".env" >> .gitignore`

**Step 6: Commit**

```bash
git add .gitignore
git commit -m "chore: add .env to gitignore (symlink to .env.local)"
```

---

### Task 1.3: Fix QDRANT_COLLECTION for testing ✅

**Problem:** Bot uses `apartments_local` collection which is empty. Need to set a test collection.

**Files:**
- Modify: `.env.local`

**Step 1: Check current collection**

Run: `grep QDRANT_COLLECTION .env.local`
Expected: `QDRANT_COLLECTION=apartments_local`

**Step 2: Create test collection name**

Run: `sed -i 's/QDRANT_COLLECTION=apartments_local/QDRANT_COLLECTION=test_documents/' .env.local`

**Step 3: Verify**

Run: `grep QDRANT_COLLECTION .env.local`
Expected: `QDRANT_COLLECTION=test_documents`

**Step 4: Commit**

```bash
git add .env.local
git commit -m "fix(config): set QDRANT_COLLECTION to test_documents"
```

---

### Task 1.4: Fix docker health checks ✅

**Problem:** Qdrant and Langfuse show "unhealthy" but work fine.

**Files:**
- Modify: `docker-compose.dev.yml:55-58` (Qdrant healthcheck)
- Modify: `docker-compose.dev.yml:147-152` (Langfuse healthcheck)

**Step 1: Fix Qdrant healthcheck**

Change in `docker-compose.dev.yml` line 55-58:
```yaml
# FROM:
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:6333/readyz"]

# TO:
    healthcheck:
      test: ["CMD-SHELL", "curl -sf http://localhost:6333/readyz || exit 1"]
```

**Step 2: Fix Langfuse healthcheck**

Change in `docker-compose.dev.yml` line 147-152:
```yaml
# FROM:
    healthcheck:
      test: ["CMD", "wget", "--no-verbose", "--tries=1", "--spider", "http://localhost:3000/api/public/health"]

# TO:
    healthcheck:
      test: ["CMD-SHELL", "wget -q --spider http://localhost:3000/api/public/health || exit 1"]
```

**Step 3: Restart services to apply changes**

Run: `docker compose -f docker-compose.dev.yml restart qdrant langfuse`

**Step 4: Wait and verify health status**

Run: `sleep 30 && docker ps --format "table {{.Names}}\t{{.Status}}" | grep -E "qdrant|langfuse"`
Expected: Both show "healthy"

**Step 5: Commit**

```bash
git add docker-compose.dev.yml
git commit -m "fix(docker): correct health checks for Qdrant and Langfuse"
```

---

## Phase 2: Install Dev Tools (2 tasks)

### Task 2.1: Install pytest and dev dependencies ✅

**Problem:** `make test` fails - pytest not installed.

**Step 1: Check current state**

Run: `pip list | grep -E "pytest|pytest-asyncio|pytest-cov" || echo "Not installed"`
Expected: "Not installed" or partial list

**Step 2: Install dev dependencies**

Run: `pip install -e ".[dev]"`

**Step 3: Verify installation**

Run: `pip list | grep -E "pytest|pytest-asyncio|pytest-cov"`
Expected:
```
pytest              8.x.x
pytest-asyncio      0.24.x
pytest-cov          5.x.x
```

**Step 4: Test pytest runs**

Run: `pytest --version`
Expected: `pytest 8.x.x`

---

### Task 2.2: Verify make commands work ✅

**Step 1: Run lint**

Run: `make lint`
Expected: "All checks passed!" or list of warnings

**Step 2: Run type-check**

Run: `make type-check`
Expected: MyPy output (may have errors, that's OK for now)

**Step 3: Run test (will fail without conftest, that's expected)**

Run: `pytest tests/test_redis_url.py -v`
Expected: PASSED (this test has no external dependencies)

---

## Phase 3: Create Test Infrastructure (2 tasks)

### Task 3.1: Create conftest.py with shared fixtures ✅

**Files:**
- Create: `tests/conftest.py`

**Step 1: Create conftest.py**

```python
"""Shared pytest fixtures for all tests."""

import os
import pytest
from dotenv import load_dotenv

# Load environment variables before any imports
load_dotenv()


@pytest.fixture(scope="session")
def qdrant_url():
    """Qdrant server URL."""
    return os.getenv("QDRANT_URL", "http://localhost:6333")


@pytest.fixture(scope="session")
def qdrant_api_key():
    """Qdrant API key (optional)."""
    return os.getenv("QDRANT_API_KEY", "")


@pytest.fixture(scope="session")
def qdrant_collection():
    """Qdrant collection name for tests."""
    return os.getenv("QDRANT_COLLECTION", "test_documents")


@pytest.fixture(scope="session")
def redis_url():
    """Redis server URL."""
    return os.getenv("REDIS_URL", "redis://localhost:6379")


@pytest.fixture(scope="session")
def bge_m3_url():
    """BGE-M3 embedding service URL."""
    return os.getenv("BGE_M3_URL", "http://localhost:8000")


@pytest.fixture(scope="session")
def openai_api_key():
    """OpenAI API key for LLM tests."""
    return os.getenv("OPENAI_API_KEY", "")


@pytest.fixture
def sample_texts():
    """Sample texts for embedding tests."""
    return [
        "Кримінальний кодекс України визначає злочини та покарання.",
        "Стаття 115 передбачає відповідальність за умисне вбивство.",
        "Крадіжка є таємним викраденням чужого майна.",
    ]


@pytest.fixture
def sample_query():
    """Sample query for search tests."""
    return "Яке покарання за крадіжку?"
```

**Step 2: Verify conftest is loaded**

Run: `pytest tests/test_redis_url.py -v --collect-only`
Expected: Shows test collection with fixtures available

**Step 3: Commit**

```bash
git add tests/conftest.py
git commit -m "test: add conftest.py with shared fixtures"
```

---

### Task 3.2: Create sample data for testing ✅

**Files:**
- Create: `data/test/sample_articles.json`

**Step 1: Create test data directory**

Run: `mkdir -p data/test`

**Step 2: Create sample test data**

```json
{
  "documents": [
    {
      "id": "article_115",
      "title": "Стаття 115. Умисне вбивство",
      "content": "Умисне вбивство, тобто умисне протиправне заподіяння смерті іншій людині, карається позбавленням волі на строк від семи до п'ятнадцяти років.",
      "metadata": {
        "article_number": "115",
        "chapter": "Злочини проти життя та здоров'я особи",
        "section": "Особлива частина"
      }
    },
    {
      "id": "article_185",
      "title": "Стаття 185. Крадіжка",
      "content": "Крадіжка, тобто таємне викрадення чужого майна, карається штрафом від п'ятдесяти до ста неоподатковуваних мінімумів доходів громадян або громадськими роботами на строк від вісімдесяти до двохсот сорока годин.",
      "metadata": {
        "article_number": "185",
        "chapter": "Злочини проти власності",
        "section": "Особлива частина"
      }
    },
    {
      "id": "article_190",
      "title": "Стаття 190. Шахрайство",
      "content": "Шахрайство, тобто заволодіння чужим майном або придбання права на майно шляхом обману чи зловживання довірою, карається штрафом від п'ятдесяти до ста неоподатковуваних мінімумів.",
      "metadata": {
        "article_number": "190",
        "chapter": "Злочини проти власності",
        "section": "Особлива частина"
      }
    }
  ]
}
```

**Step 3: Commit**

```bash
git add data/test/sample_articles.json
git commit -m "test: add sample Ukrainian Criminal Code articles for testing"
```

---

## Phase 4: Index Test Documents (3 tasks)

### Task 4.1: Create simple indexing script for JSON ✅

**Files:**
- Create: `scripts/index_test_data.py`

**Step 1: Create indexing script**

```python
#!/usr/bin/env python3
"""Index test data from JSON into Qdrant."""

import asyncio
import json
import os
import sys
from pathlib import Path

import httpx
from dotenv import load_dotenv
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, PointStruct, VectorParams

load_dotenv()

QDRANT_URL = os.getenv("QDRANT_URL", "http://localhost:6333")
QDRANT_API_KEY = os.getenv("QDRANT_API_KEY", "")
BGE_M3_URL = os.getenv("BGE_M3_URL", "http://localhost:8000")
COLLECTION_NAME = os.getenv("QDRANT_COLLECTION", "test_documents")


async def get_embeddings(texts: list[str]) -> list[list[float]]:
    """Get dense embeddings from BGE-M3 service."""
    async with httpx.AsyncClient(timeout=60.0) as client:
        response = await client.post(
            f"{BGE_M3_URL}/encode/dense",
            json={"texts": texts}
        )
        response.raise_for_status()
        return response.json()["dense_vecs"]


def create_collection(client: QdrantClient, collection_name: str, vector_size: int = 1024):
    """Create or recreate Qdrant collection."""
    # Delete if exists
    collections = [c.name for c in client.get_collections().collections]
    if collection_name in collections:
        client.delete_collection(collection_name)
        print(f"Deleted existing collection: {collection_name}")

    # Create new
    client.create_collection(
        collection_name=collection_name,
        vectors_config=VectorParams(size=vector_size, distance=Distance.COSINE)
    )
    print(f"Created collection: {collection_name}")


async def index_documents(json_path: str):
    """Index documents from JSON file."""
    # Load data
    with open(json_path) as f:
        data = json.load(f)

    documents = data["documents"]
    print(f"Loaded {len(documents)} documents from {json_path}")

    # Get embeddings
    texts = [doc["content"] for doc in documents]
    print("Getting embeddings...")
    embeddings = await get_embeddings(texts)
    print(f"Got {len(embeddings)} embeddings")

    # Create collection
    client = QdrantClient(url=QDRANT_URL, api_key=QDRANT_API_KEY or None)
    create_collection(client, COLLECTION_NAME)

    # Index points
    points = [
        PointStruct(
            id=i,
            vector=embeddings[i],
            payload={
                "id": doc["id"],
                "title": doc["title"],
                "content": doc["content"],
                **doc.get("metadata", {})
            }
        )
        for i, doc in enumerate(documents)
    ]

    client.upsert(collection_name=COLLECTION_NAME, points=points)
    print(f"Indexed {len(points)} documents into {COLLECTION_NAME}")

    # Verify
    info = client.get_collection(COLLECTION_NAME)
    print(f"Collection info: {info.points_count} points")


if __name__ == "__main__":
    json_path = sys.argv[1] if len(sys.argv) > 1 else "data/test/sample_articles.json"
    asyncio.run(index_documents(json_path))
```

**Step 2: Make executable**

Run: `chmod +x scripts/index_test_data.py`

**Step 3: Commit**

```bash
git add scripts/index_test_data.py
git commit -m "feat: add test data indexing script"
```

---

### Task 4.2: Run indexing ✅

**Step 1: Verify services are running**

Run: `curl -s http://localhost:8000/health | python3 -c "import sys,json; print(json.load(sys.stdin))"`
Expected: `{'status': 'ok', 'model_loaded': True}`

Run: `curl -s http://localhost:6333/collections`
Expected: `{"result":{"collections":[...]},"status":"ok",...}`

**Step 2: Run indexing script**

Run: `python scripts/index_test_data.py data/test/sample_articles.json`
Expected:
```
Loaded 3 documents from data/test/sample_articles.json
Getting embeddings...
Got 3 embeddings
Deleted existing collection: test_documents (if existed)
Created collection: test_documents
Indexed 3 documents into test_documents
Collection info: 3 points
```

**Step 3: Verify collection**

Run: `curl -s http://localhost:6333/collections/test_documents | python3 -c "import sys,json; d=json.load(sys.stdin); print(f'Points: {d[\"result\"][\"points_count\"]}')"`
Expected: `Points: 3`

---

### Task 4.3: Test search works ✅

**Step 1: Create quick search test script**

Run:
```bash
python3 -c "
import asyncio
import httpx
from qdrant_client import QdrantClient

async def test_search():
    # Get embedding for query
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.post('http://localhost:8000/encode/dense', json={'texts': ['покарання за крадіжку']})
        query_vec = r.json()['dense_vecs'][0]

    # Search
    qc = QdrantClient(url='http://localhost:6333')
    results = qc.search(collection_name='test_documents', query_vector=query_vec, limit=3)

    print('Search results:')
    for r in results:
        print(f'  Score: {r.score:.3f} | {r.payload.get(\"title\", \"No title\")}')

asyncio.run(test_search())
"
```

Expected:
```
Search results:
  Score: 0.8xx | Стаття 185. Крадіжка
  Score: 0.7xx | Стаття 190. Шахрайство
  Score: 0.6xx | Стаття 115. Умисне вбивство
```

---

## Phase 5: Verify All Services (3 tasks)

### Task 5.1: Test Redis cache service ✅

**Step 1: Run Redis cache test**

Run: `pytest tests/test_redis_cache.py -v`
Expected: PASSED (or skip if no Redis connection test)

If fails with connection error, verify Redis is running:
Run: `docker exec dev-redis redis-cli ping`
Expected: `PONG`

---

### Task 5.2: Test embedding service ✅

**Step 1: Create embedding service test**

Run:
```bash
python3 -c "
import asyncio
from telegram_bot.services.embeddings import EmbeddingService

async def test():
    svc = EmbeddingService('http://localhost:8000')
    emb = await svc.get_embedding('тест')
    print(f'Embedding dims: {len(emb)}')
    assert len(emb) == 1024, 'Expected 1024 dims'
    print('EmbeddingService OK')

asyncio.run(test())
"
```

Expected:
```
Embedding dims: 1024
EmbeddingService OK
```

---

### Task 5.3: Test retriever service ✅

**Step 1: Test retriever**

Run:
```bash
python3 -c "
import asyncio
from telegram_bot.services.retriever import RetrieverService
from telegram_bot.config import BotConfig

async def test():
    config = BotConfig()
    # Override URL to correct port
    config.bge_m3_url = 'http://localhost:8000'

    svc = RetrieverService(config)
    results = await svc.search('покарання за крадіжку', top_k=3)

    print(f'Found {len(results)} results')
    for r in results:
        print(f'  {r.get(\"title\", \"No title\")}')

    assert len(results) > 0, 'Expected some results'
    print('RetrieverService OK')

asyncio.run(test())
"
```

Expected:
```
Found 3 results
  Стаття 185. Крадіжка
  ...
RetrieverService OK
```

---

## Phase 6: Run Telegram Bot (2 tasks)

### Task 6.1: Test bot services integration ✅

**Step 1: Run bot services test**

Run: `python telegram_bot/test_bot_services.py`

If fails, check error and fix configuration.

---

### Task 6.2: Verify Telegram bot can start ✅

**Step 1: Verify TELEGRAM_BOT_TOKEN is set**

Run: `grep TELEGRAM_BOT_TOKEN .env.local | head -1`
Expected: `TELEGRAM_BOT_TOKEN=<some_value>`

**Step 2: Start bot**

Run: `python -m telegram_bot.main`

Expected:
```
INFO - Bot started
INFO - Polling...
```

**Step 3: Test in Telegram**

1. Open Telegram
2. Find your bot
3. Send: `/start`
4. Send: `Яке покарання за крадіжку?`
5. Verify bot responds with relevant information about Article 185

**Step 4: Stop bot**

Press `Ctrl+C`

---

## Phase 7: Final Verification (1 task)

### Task 7.1: Run all tests ✅

**Step 1: Run pytest suite**

Run: `pytest tests/ -v --ignore=tests/legacy -x`

Expected: Most tests pass (some may skip due to missing data)

**Step 2: Run make commands**

Run: `make check`
Expected: Lint and type-check pass

**Step 3: Commit any remaining changes**

```bash
git add -A
git commit -m "chore: local setup complete"
```

---

## Summary Checklist

After completing all phases:

- [x] `.env.local` has correct `BGE_M3_URL=http://localhost:8000`
- [x] `.env` symlink exists and points to `.env.local`
- [x] `QDRANT_COLLECTION=test_documents` is set
- [x] Docker health checks show all services healthy
- [x] `pytest` is installed and runs (v9.0.2)
- [x] `tests/conftest.py` exists with shared fixtures
- [x] `data/test/sample_articles.json` exists with test data
- [x] `test_documents` collection has 3 points
- [x] Search returns relevant results
- [x] Telegram bot ready to start (TELEGRAM_BOT_TOKEN set)
- [ ] `make check` passes (type errors exist - see notes)

---

## Troubleshooting

**BGE-M3 model not loaded:**
```bash
# Trigger model load
curl -X POST http://localhost:8000/encode/dense -H "Content-Type: application/json" -d '{"texts":["test"]}'
# Wait 2-3 minutes for model to load
```

**Redis connection refused:**
```bash
docker compose -f docker-compose.dev.yml restart redis
```

**Qdrant connection refused:**
```bash
docker compose -f docker-compose.dev.yml restart qdrant
```

**Import errors in src:**
```bash
pip install -e .
```

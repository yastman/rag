# Docker VPS Optimization Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Migrate from Voyage API to local Russian-optimized models (USER-bge-m3, USER2-base, bge-reranker-v2-m3) and optimize Docker build size from 37GB to <10GB.

**Architecture:** Replace external Voyage API with local embedding/reranking services. Three new Docker services: user-bge-m3 (dense retrieval), reranker (bge-reranker-v2-m3), updated user-base (USER2-base for semantic cache).

**Tech Stack:** FastAPI, sentence-transformers, PyTorch CPU-only, Docker multi-stage builds, httpx async client.

---

## Parallel Execution Strategy (tmux-swarm)

План разбит на 2 независимых воркера + финальная верификация оркестратором.

```
┌─────────────────────────────────────────────────────────────────┐
│  W1: Docker Services           │  W2: Bot Integration           │
│  (services/*, compose)         │  (telegram_bot/*, pyproject)   │
├─────────────────────────────────────────────────────────────────┤
│  Task 1: user-bge-m3 service   │  Task 5: LocalEmbeddingService │
│  Task 2: reranker service      │  Task 6: LocalRerankerService  │
│  Task 3: user-base → USER2     │  Task 7: pyproject.toml deps   │
│  Task 4: docker-compose.dev.yml│                                │
│          (все изменения)       │                                │
├─────────────────────────────────────────────────────────────────┤
│                    MERGE POINT (оркестратор)                    │
├─────────────────────────────────────────────────────────────────┤
│  Task 8: Build and test (оркестратор)                           │
│  Task 9: Full test suite (оркестратор)                          │
└─────────────────────────────────────────────────────────────────┘
```

**Файлы без конфликтов:**
- W1: `services/*`, `docker-compose.dev.yml`
- W2: `telegram_bot/services/*`, `tests/unit/*`, `pyproject.toml`, `uv.lock`

---

## Worker 1: Docker Services

### Task 1: Create user-bge-m3 Service (Dense Retrieval)

**Files:**
- Create: `services/user-bge-m3/Dockerfile`
- Create: `services/user-bge-m3/main.py`
- Create: `services/user-bge-m3/requirements.txt`

**Step 1: Create directory structure**

```bash
mkdir -p services/user-bge-m3
```

**Step 2: Create requirements.txt**

Create `services/user-bge-m3/requirements.txt`:

```
fastapi>=0.115.0
uvicorn>=0.32.0
sentence-transformers>=2.2.0
pydantic>=2.0.0
```

**Step 3: Create main.py**

Create `services/user-bge-m3/main.py`:

```python
"""USER-bge-m3 Dense Embedding Service.

FastAPI service for generating dense vectors using deepvk/USER-bge-m3.
Best-in-class Russian retrieval (73.63 on ruMTEB).
"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from pydantic import BaseModel
from sentence_transformers import SentenceTransformer


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

model: SentenceTransformer | None = None
MODEL_NAME = "deepvk/USER-bge-m3"


class EmbedRequest(BaseModel):
    """Request for single text embedding."""
    text: str


class EmbedBatchRequest(BaseModel):
    """Request for batch embeddings."""
    texts: list[str]


class EmbedResponse(BaseModel):
    """Single embedding response (1024-dim)."""
    embedding: list[float]


class EmbedBatchResponse(BaseModel):
    """Batch embeddings response."""
    embeddings: list[list[float]]
    dimension: int


class HealthResponse(BaseModel):
    """Health check response."""
    status: str
    model: str
    dimension: int


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Load model on startup."""
    global model
    logger.info(f"Loading {MODEL_NAME} model...")
    model = SentenceTransformer(MODEL_NAME)
    dim = model.get_sentence_embedding_dimension()
    logger.info(f"{MODEL_NAME} loaded (dim={dim})")
    yield
    logger.info("Shutting down USER-bge-m3 service")


app = FastAPI(
    title="USER-bge-m3 Dense Embedding Service",
    version="1.0.0",
    description="Russian retrieval embeddings (1024-dim, ruMTEB 73.63)",
    lifespan=lifespan,
)


@app.get("/health", response_model=HealthResponse)
async def health():
    """Health check endpoint."""
    return HealthResponse(
        status="healthy" if model else "loading",
        model=MODEL_NAME,
        dimension=1024,
    )


@app.post("/embed", response_model=EmbedResponse)
async def embed(request: EmbedRequest):
    """Generate embedding for single text."""
    if not model:
        raise RuntimeError("Model not loaded")
    embedding = model.encode(request.text, normalize_embeddings=True)
    return EmbedResponse(embedding=embedding.tolist())


@app.post("/embed_batch", response_model=EmbedBatchResponse)
async def embed_batch(request: EmbedBatchRequest):
    """Generate embeddings for batch of texts."""
    if not model:
        raise RuntimeError("Model not loaded")
    embeddings = model.encode(request.texts, normalize_embeddings=True)
    return EmbedBatchResponse(
        embeddings=embeddings.tolist(),
        dimension=embeddings.shape[1] if len(embeddings) > 0 else 1024,
    )
```

**Step 4: Create Dockerfile**

Create `services/user-bge-m3/Dockerfile`:

```dockerfile
FROM python:3.12-slim

WORKDIR /app

# Install PyTorch CPU-only (saves ~2GB vs CUDA)
RUN pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu

# Install other dependencies
RUN pip install --no-cache-dir \
    fastapi>=0.115.0 \
    uvicorn>=0.32.0 \
    sentence-transformers>=2.2.0 \
    pydantic>=2.0.0

# Copy service code
COPY main.py .

# Pre-download model during build
RUN python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('deepvk/USER-bge-m3')"

EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
```

**Step 5: Commit**

```bash
git add services/user-bge-m3/
git commit -m "feat(docker): add user-bge-m3 service for Russian dense retrieval

- deepvk/USER-bge-m3 model (1024-dim, ruMTEB 73.63)
- FastAPI endpoints: /embed, /embed_batch, /health
- PyTorch CPU-only (saves ~2GB)"
```

---

### Task 2: Create reranker Service

**Files:**
- Create: `services/reranker/Dockerfile`
- Create: `services/reranker/main.py`
- Create: `services/reranker/requirements.txt`

**Step 1: Create directory structure**

```bash
mkdir -p services/reranker
```

**Step 2: Create requirements.txt**

Create `services/reranker/requirements.txt`:

```
fastapi>=0.115.0
uvicorn>=0.32.0
sentence-transformers>=2.2.0
pydantic>=2.0.0
```

**Step 3: Create main.py**

Create `services/reranker/main.py`:

```python
"""BGE Reranker Service.

FastAPI service for reranking using BAAI/bge-reranker-v2-m3.
Replaces Voyage rerank API with local inference.
"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from pydantic import BaseModel
from sentence_transformers import CrossEncoder


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

model: CrossEncoder | None = None
MODEL_NAME = "BAAI/bge-reranker-v2-m3"


class RerankRequest(BaseModel):
    """Request for reranking documents."""
    query: str
    documents: list[str]
    top_k: int | None = None


class RerankResult(BaseModel):
    """Single rerank result."""
    index: int
    relevance_score: float
    document: str


class RerankResponse(BaseModel):
    """Rerank response with sorted results."""
    results: list[RerankResult]


class HealthResponse(BaseModel):
    """Health check response."""
    status: str
    model: str


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Load model on startup."""
    global model
    logger.info(f"Loading {MODEL_NAME} model...")
    model = CrossEncoder(MODEL_NAME)
    logger.info(f"{MODEL_NAME} loaded")
    yield
    logger.info("Shutting down reranker service")


app = FastAPI(
    title="BGE Reranker Service",
    version="1.0.0",
    description="Cross-encoder reranking with BAAI/bge-reranker-v2-m3",
    lifespan=lifespan,
)


@app.get("/health", response_model=HealthResponse)
async def health():
    """Health check endpoint."""
    return HealthResponse(
        status="healthy" if model else "loading",
        model=MODEL_NAME,
    )


@app.post("/rerank", response_model=RerankResponse)
async def rerank(request: RerankRequest):
    """Rerank documents by relevance to query."""
    if not model:
        raise RuntimeError("Model not loaded")

    if not request.documents:
        return RerankResponse(results=[])

    # Create query-document pairs
    pairs = [(request.query, doc) for doc in request.documents]
    scores = model.predict(pairs)

    # Sort by score (descending)
    indexed_scores = list(enumerate(zip(scores, request.documents)))
    indexed_scores.sort(key=lambda x: x[1][0], reverse=True)

    # Apply top_k if specified
    if request.top_k:
        indexed_scores = indexed_scores[:request.top_k]

    results = [
        RerankResult(
            index=idx,
            relevance_score=float(score),
            document=doc,
        )
        for idx, (score, doc) in indexed_scores
    ]

    return RerankResponse(results=results)
```

**Step 4: Create Dockerfile**

Create `services/reranker/Dockerfile`:

```dockerfile
FROM python:3.12-slim

WORKDIR /app

# Install PyTorch CPU-only
RUN pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu

# Install other dependencies
RUN pip install --no-cache-dir \
    fastapi>=0.115.0 \
    uvicorn>=0.32.0 \
    sentence-transformers>=2.2.0 \
    pydantic>=2.0.0

# Copy service code
COPY main.py .

# Pre-download model during build
RUN python -c "from sentence_transformers import CrossEncoder; CrossEncoder('BAAI/bge-reranker-v2-m3')"

EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
```

**Step 5: Commit**

```bash
git add services/reranker/
git commit -m "feat(docker): add reranker service with bge-reranker-v2-m3

- BAAI/bge-reranker-v2-m3 cross-encoder
- FastAPI endpoint: /rerank, /health
- Returns sorted results with relevance scores
- PyTorch CPU-only"
```

---

### Task 3: Update user-base to USER2-base

**Files:**
- Modify: `services/user-base/main.py:21`
- Modify: `services/user-base/Dockerfile:19`

**Step 1: Update model name in main.py**

Edit `services/user-base/main.py:21`:

```python
# OLD
MODEL_NAME = "deepvk/USER-base"

# NEW
MODEL_NAME = "deepvk/USER2-base"
```

**Step 2: Update Dockerfile model download**

Edit `services/user-base/Dockerfile:19`:

```dockerfile
# OLD
RUN python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('deepvk/USER-base')"

# NEW
RUN python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('deepvk/USER2-base')"
```

**Step 3: Update docstrings**

Edit `services/user-base/main.py:1-6`:

```python
"""USER2-base Dense Embedding Service.

FastAPI service for generating dense vectors using deepvk/USER2-base.
Best for Russian semantic matching with 8K context and Matryoshka support.
Model is loaded once at startup and reused for all requests.
"""
```

**Step 4: Commit**

```bash
git add services/user-base/
git commit -m "feat(docker): upgrade user-base to USER2-base

- deepvk/USER2-base (149M params, 768-dim, 8K context)
- Matryoshka support for variable dimensions
- Better quality than USER-base on ruMTEB"
```

---

### Task 4: Update docker-compose.dev.yml (All Changes)

**Files:**
- Modify: `docker-compose.dev.yml`

**Step 1: Add user-bge-m3 service**

Add after `user-base` service (around line 134):

```yaml
  user-bge-m3:
    build:
      context: ./services/user-bge-m3
      dockerfile: Dockerfile
    container_name: dev-user-bge-m3
    profiles: ["ai", "full"]
    ports:
      - "127.0.0.1:8004:8000"
    healthcheck:
      test: ["CMD", "python", "-c", "import urllib.request; urllib.request.urlopen('http://localhost:8000/health', timeout=5)"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 120s
    deploy:
      resources:
        limits:
          memory: 2G
```

**Step 2: Add reranker service**

Add after `user-bge-m3`:

```yaml
  reranker:
    build:
      context: ./services/reranker
      dockerfile: Dockerfile
    container_name: dev-reranker
    profiles: ["ai", "full"]
    ports:
      - "127.0.0.1:8005:8000"
    healthcheck:
      test: ["CMD", "python", "-c", "import urllib.request; urllib.request.urlopen('http://localhost:8000/health', timeout=5)"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 180s
    deploy:
      resources:
        limits:
          memory: 3G
```

**Step 3: Update bot service environment**

Add to bot service `environment` section (around line 530):

```yaml
      # Local embedding/reranking services (replaces Voyage)
      USER_BGE_M3_URL: http://user-bge-m3:8000
      RERANKER_URL: http://reranker:8000
```

**Step 4: Update bot service depends_on**

Add to bot service `depends_on` section:

```yaml
      user-bge-m3:
        condition: service_healthy
      reranker:
        condition: service_healthy
```

**Step 5: Commit**

```bash
git add docker-compose.dev.yml
git commit -m "feat(docker): add user-bge-m3, reranker services and bot deps

- user-bge-m3 on port 8004 (2GB limit)
- reranker on port 8005 (3GB limit)
- Both in 'ai' and 'full' profiles
- Bot env vars: USER_BGE_M3_URL, RERANKER_URL
- Bot depends on user-bge-m3, reranker health"
```

---

## Worker 2: Bot Integration

### Task 5: Create LocalEmbeddingService Client

**Files:**
- Create: `telegram_bot/services/local_embeddings.py`
- Create: `tests/unit/test_local_embeddings.py`

**Step 1: Write the failing test**

Create `tests/unit/test_local_embeddings.py`:

```python
"""Tests for LocalEmbeddingService."""

import pytest
from telegram_bot.services.local_embeddings import LocalEmbeddingService


@pytest.fixture
def mock_httpx(httpx_mock):
    """Configure httpx mock for embedding service."""
    httpx_mock.add_response(
        url="http://test:8000/embed",
        json={"embedding": [0.1] * 1024},
    )
    httpx_mock.add_response(
        url="http://test:8000/embed_batch",
        json={"embeddings": [[0.1] * 1024, [0.2] * 1024], "dimension": 1024},
    )
    return httpx_mock


@pytest.mark.asyncio
async def test_embed_query(mock_httpx):
    """Test single query embedding."""
    service = LocalEmbeddingService(base_url="http://test:8000")
    result = await service.embed_query("test query")
    assert len(result) == 1024
    assert result[0] == 0.1


@pytest.mark.asyncio
async def test_embed_documents(mock_httpx):
    """Test batch document embedding."""
    service = LocalEmbeddingService(base_url="http://test:8000")
    result = await service.embed_documents(["doc1", "doc2"])
    assert len(result) == 2
    assert len(result[0]) == 1024
```

**Step 2: Run test to verify it fails**

```bash
pytest tests/unit/test_local_embeddings.py -v
```

Expected: FAIL with "ModuleNotFoundError: No module named 'telegram_bot.services.local_embeddings'"

**Step 3: Write implementation**

Create `telegram_bot/services/local_embeddings.py`:

```python
"""Local embedding service client.

Async client for user-bge-m3 FastAPI service.
Replaces VoyageService for dense embeddings.
"""

import logging

import httpx


logger = logging.getLogger(__name__)


class LocalEmbeddingService:
    """Async client for local embedding service.

    Provides embeddings via user-bge-m3 container (1024-dim).
    Drop-in replacement for VoyageService embed methods.
    """

    def __init__(
        self,
        base_url: str = "http://user-bge-m3:8000",
        timeout: float = 30.0,
    ):
        """Initialize client.

        Args:
            base_url: URL of user-bge-m3 service
            timeout: Request timeout in seconds
        """
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self._client: httpx.AsyncClient | None = None
        logger.info(f"LocalEmbeddingService initialized: {base_url}")

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create async client."""
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=self.timeout)
        return self._client

    async def embed_query(self, text: str) -> list[float]:
        """Generate embedding for single query.

        Args:
            text: Query text to embed

        Returns:
            1024-dim embedding vector
        """
        client = await self._get_client()
        response = await client.post(
            f"{self.base_url}/embed",
            json={"text": text},
        )
        response.raise_for_status()
        return response.json()["embedding"]

    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        """Generate embeddings for batch of documents.

        Args:
            texts: List of document texts

        Returns:
            List of 1024-dim embedding vectors
        """
        if not texts:
            return []

        client = await self._get_client()
        response = await client.post(
            f"{self.base_url}/embed_batch",
            json={"texts": texts},
        )
        response.raise_for_status()
        return response.json()["embeddings"]

    async def close(self):
        """Close the HTTP client."""
        if self._client:
            await self._client.aclose()
            self._client = None
```

**Step 4: Run test to verify it passes**

```bash
pytest tests/unit/test_local_embeddings.py -v
```

Expected: PASS

**Step 5: Commit**

```bash
git add telegram_bot/services/local_embeddings.py tests/unit/test_local_embeddings.py
git commit -m "feat(bot): add LocalEmbeddingService client

- Async httpx client for user-bge-m3 service
- embed_query() and embed_documents() methods
- Drop-in replacement for VoyageService embeddings"
```

---

### Task 6: Create LocalRerankerService Client

**Files:**
- Create: `telegram_bot/services/local_reranker.py`
- Create: `tests/unit/test_local_reranker.py`

**Step 1: Write the failing test**

Create `tests/unit/test_local_reranker.py`:

```python
"""Tests for LocalRerankerService."""

import pytest
from telegram_bot.services.local_reranker import LocalRerankerService


@pytest.fixture
def mock_httpx(httpx_mock):
    """Configure httpx mock for reranker service."""
    httpx_mock.add_response(
        url="http://test:8000/rerank",
        json={
            "results": [
                {"index": 1, "relevance_score": 0.9, "document": "doc2"},
                {"index": 0, "relevance_score": 0.5, "document": "doc1"},
            ]
        },
    )
    return httpx_mock


@pytest.mark.asyncio
async def test_rerank(mock_httpx):
    """Test document reranking."""
    service = LocalRerankerService(base_url="http://test:8000")
    results = await service.rerank("query", ["doc1", "doc2"], top_k=2)

    assert len(results) == 2
    assert results[0]["index"] == 1
    assert results[0]["relevance_score"] == 0.9
    assert results[1]["index"] == 0


@pytest.mark.asyncio
async def test_rerank_empty(mock_httpx):
    """Test reranking with empty documents."""
    httpx_mock = mock_httpx
    httpx_mock.add_response(
        url="http://test:8000/rerank",
        json={"results": []},
    )
    service = LocalRerankerService(base_url="http://test:8000")
    results = await service.rerank("query", [], top_k=5)
    assert results == []
```

**Step 2: Run test to verify it fails**

```bash
pytest tests/unit/test_local_reranker.py -v
```

Expected: FAIL with "ModuleNotFoundError"

**Step 3: Write implementation**

Create `telegram_bot/services/local_reranker.py`:

```python
"""Local reranker service client.

Async client for bge-reranker FastAPI service.
Replaces VoyageService.rerank() with local inference.
"""

import logging

import httpx


logger = logging.getLogger(__name__)


class LocalRerankerService:
    """Async client for local reranker service.

    Provides reranking via bge-reranker-v2-m3 container.
    Drop-in replacement for VoyageService.rerank().
    """

    def __init__(
        self,
        base_url: str = "http://reranker:8000",
        timeout: float = 60.0,
    ):
        """Initialize client.

        Args:
            base_url: URL of reranker service
            timeout: Request timeout (reranking can be slow)
        """
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self._client: httpx.AsyncClient | None = None
        logger.info(f"LocalRerankerService initialized: {base_url}")

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create async client."""
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=self.timeout)
        return self._client

    async def rerank(
        self,
        query: str,
        documents: list[str],
        top_k: int | None = None,
    ) -> list[dict]:
        """Rerank documents by relevance to query.

        Args:
            query: Search query
            documents: List of document texts
            top_k: Number of top results (None = all)

        Returns:
            List of dicts with 'index', 'relevance_score', 'document' keys,
            sorted by relevance (highest first).
        """
        if not documents:
            return []

        client = await self._get_client()
        response = await client.post(
            f"{self.base_url}/rerank",
            json={"query": query, "documents": documents, "top_k": top_k},
        )
        response.raise_for_status()
        return response.json()["results"]

    async def close(self):
        """Close the HTTP client."""
        if self._client:
            await self._client.aclose()
            self._client = None
```

**Step 4: Run test to verify it passes**

```bash
pytest tests/unit/test_local_reranker.py -v
```

Expected: PASS

**Step 5: Commit**

```bash
git add telegram_bot/services/local_reranker.py tests/unit/test_local_reranker.py
git commit -m "feat(bot): add LocalRerankerService client

- Async httpx client for reranker service
- rerank() method compatible with VoyageService interface
- Returns sorted results with relevance scores"
```

---

### Task 7: Optimize pyproject.toml Dependencies

**Files:**
- Modify: `pyproject.toml:6-39`
- Regenerate: `uv.lock`

**Step 1: Remove dead dependencies**

Edit `pyproject.toml`, remove from `dependencies`:

```toml
# REMOVE these lines:
"FlagEmbedding",
"deepeval>=2.0.0",
```

**Step 2: Move evaluation deps to optional group**

Move from `dependencies` to new `[project.optional-dependencies]` section:

```toml
# REMOVE from dependencies:
"mlflow>=2.22.1",
"ragas>=0.2.10",

# ADD new optional group after [project.optional-dependencies] dev:
eval = [
    "mlflow>=2.22.1",
    "ragas>=0.2.10",
    "deepeval>=2.0.0",
]
```

**Step 3: Update all group**

Edit `pyproject.toml:65-67`:

```toml
# OLD
all = [
    "contextual-rag[dev,docs]",
]

# NEW
all = [
    "contextual-rag[dev,docs,eval]",
]
```

**Step 4: Run uv lock to verify**

```bash
uv lock
```

Expected: Success, no errors

**Step 5: Commit**

```bash
git add pyproject.toml uv.lock
git commit -m "fix(deps): remove dead deps, move eval to optional

- Remove FlagEmbedding (unused)
- Remove deepeval from core (unused)
- Move mlflow, ragas, deepeval to [eval] optional group
- Reduces core install size significantly"
```

---

## Orchestrator: Merge and Verify

### Task 8: Build and Test Services Locally

**Prerequisites:** W1 and W2 completed and merged.

**Step 1: Pull changes from both workers**

```bash
git checkout main
git merge feature/docker-services --no-edit
git merge feature/bot-integration --no-edit
```

**Step 2: Build new images (use tmux for long build)**

```bash
mkdir -p logs
tmux new-window -n "W-BUILD" -c /home/user/projects/rag-fresh
tmux send-keys -t "W-BUILD" "docker compose -f docker-compose.dev.yml build user-bge-m3 reranker user-base 2>&1 | tee logs/docker-build.log; echo '[COMPLETE]'" Enter
```

Check: `tail -f logs/docker-build.log`
Done: `grep '\[COMPLETE\]' logs/docker-build.log`

**Step 3: Start services**

```bash
docker compose -f docker-compose.dev.yml --profile ai up -d user-bge-m3 reranker user-base
```

**Step 4: Wait for healthy status**

```bash
docker compose -f docker-compose.dev.yml ps
```

Expected: All three services show "healthy"

**Step 5: Test user-bge-m3 endpoint**

```bash
curl -X POST http://localhost:8004/embed \
  -H "Content-Type: application/json" \
  -d '{"text": "тестовый запрос на русском"}'
```

Expected: JSON with `embedding` array of 1024 floats

**Step 6: Test reranker endpoint**

```bash
curl -X POST http://localhost:8005/rerank \
  -H "Content-Type: application/json" \
  -d '{"query": "квартира", "documents": ["дом в Несебре", "квартира в Бургасе", "офис в Софии"], "top_k": 2}'
```

Expected: JSON with sorted `results` array

**Step 7: Test user-base (USER2)**

```bash
curl -X POST http://localhost:8003/embed \
  -H "Content-Type: application/json" \
  -d '{"text": "семантический кеш"}'
```

Expected: JSON with `embedding` array of 768 floats

---

### Task 9: Run Full Test Suite

**Step 1: Run unit tests**

```bash
pytest tests/unit/ -v --tb=short
```

Expected: All tests pass

**Step 2: Run linting**

```bash
make check
```

Expected: No errors

**Step 3: Final commit if needed**

Fix any issues found, then:

```bash
git add -A
git commit -m "fix: address test/lint issues from migration"
```

---

## tmux-swarm Execution Commands

```bash
# Worker 1: Docker Services
spawn-claude --worktree feature/docker-services \
  --plan docs/plans/2026-02-05-docker-vps-optimization.md \
  --tasks "1,2,3,4" \
  --skill executing-plans

# Worker 2: Bot Integration
spawn-claude --worktree feature/bot-integration \
  --plan docs/plans/2026-02-05-docker-vps-optimization.md \
  --tasks "5,6,7" \
  --skill executing-plans
```

---

## Summary

| Worker | Tasks | Files | Est. Time |
|--------|-------|-------|-----------|
| W1 | 1,2,3,4 | `services/*`, `docker-compose.dev.yml` | 15 min |
| W2 | 5,6,7 | `telegram_bot/services/*`, `tests/*`, `pyproject.toml` | 10 min |
| Orchestrator | 8,9 | — (verification) | 5 min |

**Общее время:** ~20-25 мин (параллельно) вместо ~40 мин (последовательно)

**Next steps after this plan:**
1. Deploy to VPS (`git pull`, `docker compose build`, etc.)
2. Clean Qdrant collections (test data)
3. Re-run ingestion with new embeddings
4. Verify bot works end-to-end

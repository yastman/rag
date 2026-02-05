# Docker VPS Optimization Design

Оптимизация Docker-стека для VPS: миграция на локальные русскоязычные модели, удаление Voyage API.

## Проблема

1. **Размер сборки ~100GB** — build cache 37GB, тяжёлые ML deps
2. **Voyage API слаб на русском** — контент 100% русский
3. **CUDA в образах** — torch тянет GPU deps при CPU-only инференсе

## Решение

Полностью локальный стек с русскоязычными моделями deepvk.

## Архитектура

### Было (Voyage API)

```
Query → Voyage API (dense) + BM42 (sparse) → Qdrant → Voyage rerank → LLM
        ↑ слабо на русском                         ↑ слабо на русском
```

### Будет (локальные модели)

```
Query → USER-bge-m3 (dense) + BM42 (sparse) → Qdrant → bge-reranker → LLM
        ↑ 1024-dim, ruMTEB 73.63                     ↑ локально

Semantic Cache: USER2-base (768-dim, 8K context, Matryoshka)
```

## Docker-сервисы на VPS

### Ядро (core profile)

| Сервис | Образ | RAM | Назначение |
|--------|-------|-----|------------|
| postgres | pgvector:pg17 | 256MB | Метаданные |
| qdrant | qdrant:v1.16 | 512MB | Векторная БД |
| redis | redis:8.4 | 256MB | Cache |

### ML-сервисы (новые/обновлённые)

| Сервис | Модель | Размер | RAM | Назначение |
|--------|--------|--------|-----|------------|
| user-base | USER2-base (149M) | ~1.2GB | ~800MB | Semantic cache |
| user-bge-m3 | USER-bge-m3 (359M) | ~1.8GB | ~1.5GB | Dense retrieval |
| reranker | bge-reranker-v2-m3 (568M) | ~2.2GB | ~2GB | Reranking |
| bm42 | BM42 (ONNX) | ~1GB | 512MB | Sparse retrieval |

### Приложения

| Сервис | RAM | Назначение |
|--------|-----|------------|
| bot | 256MB | Telegram бот |
| litellm | 256MB | LLM proxy → Cerebras |
| ingestion | 512MB | CocoIndex + Docling |

### Итого RAM: ~6.5GB из 11GB доступных

## Новые Docker-сервисы

### 1. user-bge-m3 (Dense Retrieval)

```
services/user-bge-m3/
├── Dockerfile
├── main.py
└── requirements.txt
```

**Dockerfile:**

```dockerfile
FROM python:3.11-slim AS builder
WORKDIR /build

RUN pip install --no-cache-dir \
    torch --index-url https://download.pytorch.org/whl/cpu
RUN pip install --no-cache-dir sentence-transformers

FROM python:3.11-slim
WORKDIR /app

COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY main.py .

# Pre-download model
RUN python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('deepvk/USER-bge-m3')"

EXPOSE 8000
CMD ["python", "main.py"]
```

**main.py:**

```python
from fastapi import FastAPI
from pydantic import BaseModel
from sentence_transformers import SentenceTransformer
import uvicorn

app = FastAPI()
model = SentenceTransformer("deepvk/USER-bge-m3")

class EmbedRequest(BaseModel):
    texts: list[str]

class EmbedResponse(BaseModel):
    embeddings: list[list[float]]
    dimension: int

@app.post("/embed", response_model=EmbedResponse)
async def embed(request: EmbedRequest):
    embeddings = model.encode(request.texts, normalize_embeddings=True)
    return EmbedResponse(
        embeddings=embeddings.tolist(),
        dimension=embeddings.shape[1]
    )

@app.get("/health")
async def health():
    return {"status": "healthy", "model": "deepvk/USER-bge-m3"}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
```

### 2. reranker (Reranking)

```
services/reranker/
├── Dockerfile
├── main.py
└── requirements.txt
```

**main.py:**

```python
from fastapi import FastAPI
from pydantic import BaseModel
from sentence_transformers import CrossEncoder
import uvicorn

app = FastAPI()
model = CrossEncoder("BAAI/bge-reranker-v2-m3")

class RerankRequest(BaseModel):
    query: str
    documents: list[str]
    top_k: int = 5

class RerankResponse(BaseModel):
    scores: list[float]
    indices: list[int]

@app.post("/rerank", response_model=RerankResponse)
async def rerank(request: RerankRequest):
    pairs = [(request.query, doc) for doc in request.documents]
    scores = model.predict(pairs)

    indexed_scores = list(enumerate(scores))
    indexed_scores.sort(key=lambda x: x[1], reverse=True)

    top_indices = [i for i, _ in indexed_scores[:request.top_k]]
    top_scores = [float(s) for _, s in indexed_scores[:request.top_k]]

    return RerankResponse(scores=top_scores, indices=top_indices)

@app.get("/health")
async def health():
    return {"status": "healthy", "model": "BAAI/bge-reranker-v2-m3"}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8001)
```

### 3. user-base (обновление)

Изменить модель в `services/user-base/main.py`:

```python
# Было
MODEL_NAME = "deepvk/USER-base"

# Стало
MODEL_NAME = "deepvk/USER2-base"
```

## Изменения в docker-compose.dev.yml

### Добавить новые сервисы

```yaml
  user-bge-m3:
    build:
      context: ./services/user-bge-m3
      dockerfile: Dockerfile
    container_name: dev-user-bge-m3
    ports:
      - "127.0.0.1:8004:8000"
    profiles: ["ai", "full"]
    healthcheck:
      test: ["CMD", "python", "-c", "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')"]
      interval: 30s
      timeout: 10s
      retries: 3
    deploy:
      resources:
        limits:
          memory: 2G

  reranker:
    build:
      context: ./services/reranker
      dockerfile: Dockerfile
    container_name: dev-reranker
    ports:
      - "127.0.0.1:8005:8001"
    profiles: ["ai", "full"]
    healthcheck:
      test: ["CMD", "python", "-c", "import urllib.request; urllib.request.urlopen('http://localhost:8001/health')"]
      interval: 30s
      timeout: 10s
      retries: 3
    deploy:
      resources:
        limits:
          memory: 3G
```

### Удалить/отключить

- `bge-m3-api` — заменён на `user-bge-m3`
- `lightrag` — не используется

## Изменения в коде бота

### 1. telegram_bot/config.py

```python
# Было
voyage_model_docs: str = os.getenv("VOYAGE_MODEL_DOCS", "voyage-4-large")
voyage_model_queries: str = os.getenv("VOYAGE_MODEL_QUERIES", "voyage-4-lite")
voyage_model_rerank: str = os.getenv("VOYAGE_RERANK_MODEL", "rerank-2.5")

# Стало
embedding_service_url: str = os.getenv("EMBEDDING_SERVICE_URL", "http://user-bge-m3:8000")
reranker_service_url: str = os.getenv("RERANKER_SERVICE_URL", "http://reranker:8001")
```

### 2. telegram_bot/services/embeddings.py (новый)

```python
import httpx
from typing import List

class LocalEmbeddingService:
    def __init__(self, base_url: str = "http://user-bge-m3:8000"):
        self.base_url = base_url
        self.client = httpx.AsyncClient(timeout=30.0)

    async def embed(self, texts: List[str]) -> List[List[float]]:
        response = await self.client.post(
            f"{self.base_url}/embed",
            json={"texts": texts}
        )
        response.raise_for_status()
        return response.json()["embeddings"]

    async def embed_query(self, query: str) -> List[float]:
        embeddings = await self.embed([query])
        return embeddings[0]

    async def embed_documents(self, documents: List[str]) -> List[List[float]]:
        return await self.embed(documents)
```

### 3. telegram_bot/services/reranker.py (новый)

```python
import httpx
from typing import List, Tuple

class LocalRerankerService:
    def __init__(self, base_url: str = "http://reranker:8001"):
        self.base_url = base_url
        self.client = httpx.AsyncClient(timeout=30.0)

    async def rerank(
        self,
        query: str,
        documents: List[str],
        top_k: int = 5
    ) -> List[Tuple[int, float]]:
        response = await self.client.post(
            f"{self.base_url}/rerank",
            json={"query": query, "documents": documents, "top_k": top_k}
        )
        response.raise_for_status()
        data = response.json()
        return list(zip(data["indices"], data["scores"]))
```

## Изменения в pyproject.toml

### Удалить из core dependencies

```toml
# Удалить (мёртвый код)
"FlagEmbedding>=1.3.0",
"deepeval>=0.21.0",

# Перенести в optional [eval]
"ragas>=0.2.0",
"mlflow>=2.0.0",
```

### Добавить optional group

```toml
[project.optional-dependencies]
eval = [
    "ragas>=0.2.0",
    "mlflow>=2.0.0",
    "deepeval>=0.21.0",
]
```

## Переиндексация Qdrant

Новые embeddings (USER-bge-m3, 1024-dim) несовместимы со старыми (Voyage, 1024-dim но другое пространство).

### План переиндексации

1. Остановить бота
2. Удалить тестовые коллекции:
   ```bash
   curl -X DELETE http://localhost:6333/collections/contextual_bulgaria_voyage
   curl -X DELETE http://localhost:6333/collections/gdrive_documents_scalar
   ```
3. Создать новые коллекции с правильными параметрами
4. Запустить ingestion с новыми embeddings
5. Запустить бота

### Новая коллекция

```python
from qdrant_client import QdrantClient
from qdrant_client.models import VectorParams, Distance

client = QdrantClient("http://localhost:6333")

client.create_collection(
    collection_name="gdrive_documents",
    vectors_config={
        "dense": VectorParams(size=1024, distance=Distance.COSINE),
    },
    sparse_vectors_config={
        "bm42": models.SparseVectorParams(),
    },
)
```

## Порядок внедрения

### Фаза 1: Подготовка (локально)

1. Создать `services/user-bge-m3/`
2. Создать `services/reranker/`
3. Обновить `services/user-base/` → USER2-base
4. Обновить `docker-compose.dev.yml`
5. Создать `telegram_bot/services/embeddings.py`
6. Создать `telegram_bot/services/reranker.py`
7. Обновить `telegram_bot/config.py`
8. Оптимизировать `pyproject.toml`

### Фаза 2: Тестирование (локально)

1. Собрать образы: `docker compose build user-bge-m3 reranker user-base`
2. Запустить: `docker compose up -d user-bge-m3 reranker`
3. Тесты endpoints:
   ```bash
   curl -X POST http://localhost:8004/embed \
     -H "Content-Type: application/json" \
     -d '{"texts": ["тестовый запрос"]}'
   ```
4. Unit tests для новых сервисов

### Фаза 3: Деплой на VPS

1. Push изменений в git
2. На VPS: `git pull`
3. Очистить build cache: `docker builder prune -f`
4. Собрать образы (tmux + logs)
5. Удалить старые коллекции Qdrant
6. Запустить ingestion
7. Запустить бота

## Метрики успеха

| Метрика | Было | Цель |
|---------|------|------|
| Build cache | 37GB | <10GB |
| Образ user-base | 2.83GB | <1.5GB |
| RAM usage | N/A | <7GB |
| Качество на русском (ruMTEB) | ~60% (Voyage) | 73%+ (USER-bge-m3) |

## Риски

| Риск | Митигация |
|------|-----------|
| Latency локальных моделей | Кеширование, batch inference |
| RAM overflow | Memory limits в compose, мониторинг |
| Качество rerank | A/B тест против Voyage |

## Не входит в scope

- Langfuse/MLflow (добавим позже)
- Monitoring stack (добавим позже)
- ONNX optimization (v2)
- Matryoshka dimension reduction (v2)

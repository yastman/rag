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

| Service          | URL                             | Purpose                                   |
| ---------------- | ------------------------------- | ----------------------------------------- |
| PostgreSQL       | localhost:5432                  | Database (user: postgres, pass: postgres) |
| Redis            | localhost:6379                  | Cache                                     |
| Qdrant           | http://localhost:6333           | Vector database                           |
| Qdrant Dashboard | http://localhost:6333/dashboard | Qdrant UI                                 |
| BGE-M3           | http://localhost:8000           | Embeddings API                            |
| Docling          | http://localhost:5001           | PDF parser                                |
| LightRAG         | http://localhost:9621           | RAG API                                   |
| Langfuse         | http://localhost:3001           | LLM tracing UI                            |
| MLflow           | http://localhost:5000           | ML experiments UI                         |

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

## Setting Up Qdrant Collection

The project uses a multi-vector Qdrant collection with 3 vector types for hybrid search.

### Vector Types

| Vector      | Dimensions | Purpose                        |
| ----------- | ---------- | ------------------------------ |
| **dense**   | 1024       | Semantic search (BGE-M3)       |
| **colbert** | 1024 × N   | MaxSim reranking (multivector) |
| **bm42**    | sparse     | Keyword matching (IDF)         |

### Create Collection

```bash
# Basic setup (creates 'legal_documents' collection)
python scripts/setup_qdrant_collection.py

# Force recreate if exists
python scripts/setup_qdrant_collection.py --force

# Custom collection name
python scripts/setup_qdrant_collection.py --collection my_collection --force
```

### What Gets Created

- **Collection** with 3 vector types (dense, colbert, bm42)
- **Payload indexes** for fast filtering:
  - Keyword: `document_name`, `article_number`, `city`, `source_type`
  - Integer: `price`, `rooms`, `area`, `floor`, `floors`, `distance_to_sea`, `bathrooms`
  - Boolean: `furnished`, `year_round`
- **Optimizations**: INT8 scalar quantization, HNSW config

### Verify Collection

```bash
# Check via API
curl http://localhost:6333/collections/legal_documents

# Or use Qdrant Dashboard
open http://localhost:6333/dashboard
```

---

## Setting Up Redis Cache Indexes

The project uses Redis with vector search for semantic caching.

### Cache Tiers

| Cache              | TTL | Purpose                           |
| ------------------ | --- | --------------------------------- |
| **Semantic LLM**   | 48h | Cache answers by query similarity |
| **Embeddings**     | 7d  | Cache BGE-M3 vectors              |
| **Query Analysis** | 24h | Cache parsed queries              |
| **Search Results** | 2h  | Cache Qdrant results              |
| **Conversation**   | 1h  | Multi-turn dialogue history       |

### Create Vector Index

```bash
# Basic setup
python scripts/setup_redis_indexes.py

# Force recreate if exists
python scripts/setup_redis_indexes.py --force

# Dry run (check config only)
python scripts/setup_redis_indexes.py --dry-run
```

### Requirements

Vector search requires **Redis Stack** (includes RediSearch module).
The default `redis:8-alpine` image does NOT include RediSearch.

To use semantic caching, update `docker-compose.dev.yml`:

```yaml
redis:
  image: redis/redis-stack:latest # Instead of redis:8-alpine
  container_name: dev-redis
  ports:
    - "6379:6379"
    - "8001:8001" # RedisInsight UI
```

### Verify Index

```bash
# Check index info
docker compose -f docker-compose.dev.yml exec redis redis-cli FT.INFO idx:rag:semantic_cache
```

---

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
  - "5433:5432" # Change left side (host port)
```

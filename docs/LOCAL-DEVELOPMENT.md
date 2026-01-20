***REMOVED*** Local Development Guide

Complete guide for running the RAG bot development environment locally.

***REMOVED******REMOVED*** Requirements

- Docker 24+
- Docker Compose v2
- OpenAI API key (for LLM and embeddings)
- ~8GB RAM (BGE-M3 and Docling are memory-intensive)

***REMOVED******REMOVED*** Quick Start

***REMOVED******REMOVED******REMOVED*** 1. Clone and setup

```bash
git clone https://github.com/yastman/rag.git
cd rag
cp .env.example .env
```

***REMOVED******REMOVED******REMOVED*** 2. Configure API keys

Edit `.env` and set:
```bash
OPENAI_API_KEY=[REDACTED-OPENAI-KEY]
TELEGRAM_BOT_TOKEN=[REDACTED-TELEGRAM-TOKEN]  ***REMOVED*** optional
```

***REMOVED******REMOVED******REMOVED*** 3. Start dev stack

```bash
docker compose -f docker-compose.dev.yml up -d
```

First start takes 5-10 minutes (downloading images, loading models).

***REMOVED******REMOVED******REMOVED*** 4. Verify services

```bash
docker compose -f docker-compose.dev.yml ps
```

All services should show "healthy" status.

***REMOVED******REMOVED*** Services

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

***REMOVED******REMOVED*** Common Commands

***REMOVED******REMOVED******REMOVED*** View logs

```bash
***REMOVED*** All services
docker compose -f docker-compose.dev.yml logs -f

***REMOVED*** Specific service
docker compose -f docker-compose.dev.yml logs -f langfuse
```

***REMOVED******REMOVED******REMOVED*** Restart service

```bash
docker compose -f docker-compose.dev.yml restart langfuse
```

***REMOVED******REMOVED******REMOVED*** Stop all services

```bash
docker compose -f docker-compose.dev.yml down
```

***REMOVED******REMOVED******REMOVED*** Reset all data (clean start)

```bash
docker compose -f docker-compose.dev.yml down -v
docker compose -f docker-compose.dev.yml up -d
```

***REMOVED******REMOVED*** Running the Bot

***REMOVED******REMOVED******REMOVED*** Option 1: Local Python (recommended for development)

```bash
***REMOVED*** Activate virtual environment
source venv/bin/activate

***REMOVED*** Install dependencies
pip install -e .

***REMOVED*** Run bot
python -m telegram_bot.main
```

***REMOVED******REMOVED******REMOVED*** Option 2: Docker container

Uncomment the `bot` service in `docker-compose.dev.yml` and run:

```bash
docker compose -f docker-compose.dev.yml up -d bot
```

***REMOVED******REMOVED*** Using Langfuse for LLM Tracing

1. Open http://localhost:3001
2. Create account (first user becomes admin)
3. Create project and get API keys
4. Add to your code:

```python
from langfuse import Langfuse

langfuse = Langfuse(
    public_key="[REDACTED-LANGFUSE-KEY]
    secret_key="[REDACTED-LANGFUSE-KEY]
    host="http://localhost:3001"
)
```

***REMOVED******REMOVED*** Using MLflow for Experiments

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

***REMOVED******REMOVED*** Troubleshooting

***REMOVED******REMOVED******REMOVED*** Service won't start

```bash
***REMOVED*** Check logs
docker compose -f docker-compose.dev.yml logs <service-name>

***REMOVED*** Check resources
docker stats
```

***REMOVED******REMOVED******REMOVED*** BGE-M3 slow to start

First start downloads ~2GB model. Check progress:

```bash
docker compose -f docker-compose.dev.yml logs -f bge-m3
```

***REMOVED******REMOVED******REMOVED*** Database connection issues

Verify PostgreSQL is healthy:

```bash
docker compose -f docker-compose.dev.yml exec postgres pg_isready
```

***REMOVED******REMOVED******REMOVED*** Port conflicts

If ports are in use, modify `docker-compose.dev.yml` port mappings:

```yaml
ports:
  - "5433:5432"  ***REMOVED*** Change left side (host port)
```

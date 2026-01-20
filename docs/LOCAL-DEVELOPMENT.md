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

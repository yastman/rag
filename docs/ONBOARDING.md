***REMOVED*** Developer Onboarding Guide

Welcome to the RAG Fresh project! This guide walks you through setting up a local development environment.

***REMOVED******REMOVED*** Prerequisites

Before you begin, ensure you have:

- **Python 3.12** (recommended) or 3.11+
- **Docker & Docker Compose v2** — for local services
- **uv** package manager — `pip install uv`
- **Git** — for version control

***REMOVED******REMOVED******REMOVED*** Required Accounts & API Keys

| Service | Required | Purpose |
|---------|----------|---------|
| Telegram Bot Token | Yes | Bot functionality (`TELEGRAM_BOT_TOKEN`) |
| Langfuse | Recommended | Observability (`LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY`) |
| LiteLLM API | Yes | LLM calls (`LITELLM_API_KEY`) |
| BGE-M3 API | Optional | Embeddings (can use bundled model) |

***REMOVED******REMOVED*** Step 1: Clone and Setup

```bash
***REMOVED*** Clone the repository
git clone <repository-url>
cd rag

***REMOVED*** Install dependencies
uv sync

***REMOVED*** Copy environment template
cp .env.example .env
```

***REMOVED******REMOVED*** Step 2: Configure Environment

Edit `.env` with your API keys:

```bash
***REMOVED*** Required for bot to work
TELEGRAM_BOT_TOKEN=[REDACTED-TELEGRAM-TOKEN]

***REMOVED*** LLM provider
LITELLM_API_KEY=your_litellm_api_key

***REMOVED*** Langfuse (for observability)
LANGFUSE_PUBLIC_KEY=your_langfuse_public_key
LANGFUSE_SECRET_KEY=your_langfuse_secret_key
LANGFUSE_HOST=https://cloud.langfuse.com

***REMOVED*** BGE-M3 (embeddings)
BGE_M3_URL=http://localhost:8000  ***REMOVED*** or hosted endpoint
```

See `.env.example` for full variable documentation.

***REMOVED******REMOVED*** Step 3: Start Services

```bash
***REMOVED*** Start all Docker services (Redis, Qdrant, etc.)
make docker-up

***REMOVED*** Or with monitoring (Grafana, Loki)
make docker-full-up
```

Verify services are healthy:

```bash
make test-bot-health
make docker-ps
```

***REMOVED******REMOVED*** Step 4: Run Preflight Checks

```bash
***REMOVED*** Check all dependencies
make test-preflight

***REMOVED*** Verify embeddings service
curl -fsS http://localhost:8000/health
```

***REMOVED******REMOVED*** Step 5: Start the Bot

```bash
***REMOVED*** Start Telegram bot only
make docker-bot-up

***REMOVED*** Or run directly (requires all services running)
uv run python -m telegram_bot.main
```

***REMOVED******REMOVED******REMOVED*** Verify Bot is Connected

1. Open Telegram and search for your bot
2. Send `/start` — you should receive a welcome message
3. Send `/help` — you should receive help text

***REMOVED******REMOVED*** Step 6: Run Ingestion (Optional)

To test with real data:

```bash
***REMOVED*** Preflight checks for ingestion
make ingest-unified-preflight

***REMOVED*** Bootstrap the collection
make ingest-unified-bootstrap

***REMOVED*** Run continuous ingestion
make ingest-unified
```

***REMOVED******REMOVED*** Common First-Day Issues

***REMOVED******REMOVED******REMOVED*** Redis Connection Refused

```bash
***REMOVED*** Check Redis is running
docker compose ps redis

***REMOVED*** Restart Redis
docker compose restart redis
```

***REMOVED******REMOVED******REMOVED*** Qdrant Collection Not Found

```bash
***REMOVED*** Check Qdrant status
docker compose exec qdrant curl -s http://localhost:6333/collections

***REMOVED*** Recreate collection
make ingest-unified-bootstrap
```

***REMOVED******REMOVED******REMOVED*** Token/Authentication Errors

1. Verify `TELEGRAM_BOT_TOKEN` is valid
2. Check Langfuse keys are correct
3. Ensure `LITELLM_API_KEY` has not expired

***REMOVED******REMOVED*** Project Structure Overview

```
rag/
├── telegram_bot/         ***REMOVED*** Telegram bot implementation
│   ├── bot.py           ***REMOVED*** Main bot class (PropertyBot)
│   ├── graph/           ***REMOVED*** LangGraph pipeline (voice)
│   ├── agents/          ***REMOVED*** SDK agent & tools
│   ├── pipelines/       ***REMOVED*** Client fast-path pipeline
│   └── integrations/    ***REMOVED*** Cache, embeddings, etc.
├── src/
│   ├── api/             ***REMOVED*** RAG API (FastAPI)
│   ├── ingestion/       ***REMOVED*** Document ingestion
│   └── voice/           ***REMOVED*** Voice bot (LiveKit)
├── docs/                ***REMOVED*** Documentation
│   ├── runbooks/       ***REMOVED*** Operational runbooks
│   └── adr/            ***REMOVED*** Architecture decision records
└── tests/               ***REMOVED*** Test suite
```

***REMOVED******REMOVED*** Key Documentation Links

| Topic | Link |
|-------|------|
| Local development setup | [LOCAL-DEVELOPMENT.md](LOCAL-DEVELOPMENT.md) |
| Pipeline architecture | [PIPELINE_OVERVIEW.md](PIPELINE_OVERVIEW.md) |
| Troubleshooting | [runbooks/README.md](runbooks/README.md) |
| Feature documentation | [BOT_ARCHITECTURE.md](BOT_ARCHITECTURE.md) |

***REMOVED******REMOVED*** Next Steps

1. Read [LOCAL-DEVELOPMENT.md](LOCAL-DEVELOPMENT.md) for detailed setup
2. Review [PIPELINE_OVERVIEW.md](PIPELINE_OVERVIEW.md) to understand the architecture
3. Check [BOT_ARCHITECTURE.md](BOT_ARCHITECTURE.md) for bot internals
4. Explore `tests/` to understand testing patterns

***REMOVED******REMOVED*** Getting Help

- **Issues**: Create a GitHub issue for bugs or feature requests
- **Internal docs**: See [docs/engineering/](engineering/) for development guidelines
- **Troubleshooting**: See [runbooks/README.md](runbooks/README.md) for common issues

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
| LiteLLM Master Key | Yes | LLM proxy auth (`LITELLM_MASTER_KEY`) |
| LLM Provider | Yes | At least one of `OPENAI_API_KEY`, `CEREBRAS_API_KEY`, or `GROQ_API_KEY` |
| Langfuse | Recommended | Local observability (`LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY`, `LANGFUSE_HOST`) |
| BGE-M3 | Optional | Embeddings service started automatically by Compose |

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

Edit `.env` with your API keys. The canonical reference is `.env.example`:

```bash
***REMOVED*** Required for bot to work
TELEGRAM_BOT_TOKEN=[REDACTED-TELEGRAM-TOKEN]
LITELLM_MASTER_KEY=your_litellm_master_key

***REMOVED*** At least one LLM provider key
OPENAI_API_KEY=[REDACTED-OPENAI-KEY]
***REMOVED*** CEREBRAS_API_KEY=...
***REMOVED*** GROQ_API_KEY=[REDACTED-GROQ-KEY]

***REMOVED*** Langfuse (local observability — started by make docker-ml-up)
LANGFUSE_PUBLIC_KEY=[REDACTED-LANGFUSE-KEY]
LANGFUSE_SECRET_KEY=[REDACTED-LANGFUSE-KEY]
LANGFUSE_HOST=http://localhost:3001
```

See `.env.example` for the full variable list and [`LOCAL-DEVELOPMENT.md`](LOCAL-DEVELOPMENT.md) for the minimum env sets per profile.

***REMOVED******REMOVED*** Step 3: Start Services

Start core services and verify health:

```bash
make local-up
make test-bot-health
```

For the full service map, profile stacks, and port list, see [`DOCKER.md`](../DOCKER.md).

***REMOVED******REMOVED*** Step 4: Run Preflight Checks

```bash
make test-bot-health
```

The authoritative startup preflight runs in `telegram_bot/preflight.py` when the bot starts. See [`LOCAL-DEVELOPMENT.md`](LOCAL-DEVELOPMENT.md) for the full validation ladder.

***REMOVED******REMOVED*** Step 5: Start the Bot

```bash
***REMOVED*** Run bot natively (fast iteration, services must be running)
make run-bot

***REMOVED*** Or run everything in Docker
make docker-bot-up
```

***REMOVED******REMOVED******REMOVED*** Verify Bot is Connected

1. Open Telegram and search for your bot
2. Send `/start` — you should receive a welcome message
3. Send `/help` — you should receive help text

See [`LOCAL-DEVELOPMENT.md`](LOCAL-DEVELOPMENT.md) for the day-to-day workflow and native vs Docker trade-offs.

***REMOVED******REMOVED*** Step 6: Run Ingestion (Optional)

To test with real data, see [`INGESTION.md`](INGESTION.md) for the full ingestion workflow:

```bash
make ingest-unified-preflight
make ingest-unified-bootstrap
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
3. Ensure `LITELLM_MASTER_KEY` and at least one provider key (`OPENAI_API_KEY`, `CEREBRAS_API_KEY`, or `GROQ_API_KEY`) are set

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

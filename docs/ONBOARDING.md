# Developer Onboarding Guide

Welcome to the RAG Fresh project! This guide walks you through setting up a local development environment.

## Prerequisites

Before you begin, ensure you have:

- **Python 3.12** (recommended) or 3.11+
- **Docker & Docker Compose v2** — for local services
- **uv** package manager — `pip install uv`
- **Git** — for version control

### Required Accounts & API Keys

| Service | Required | Purpose |
|---------|----------|---------|
| Telegram Bot Token | Yes | Bot functionality (`TELEGRAM_BOT_TOKEN`) |
| LiteLLM Master Key | Yes | LLM proxy auth (`LITELLM_MASTER_KEY`) |
| LLM Provider | Yes | At least one of `OPENAI_API_KEY`, `CEREBRAS_API_KEY`, or `GROQ_API_KEY` |
| Langfuse | Recommended | Local observability (`LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY`, `LANGFUSE_HOST`) |
| BGE-M3 | Optional | Embeddings service started automatically by Compose |

## Step 1: Clone and Setup

```bash
# Clone the repository
git clone <repository-url>
cd rag

# Install dependencies
uv sync

# Copy environment template
cp .env.example .env
```

## Step 2: Configure Environment

Edit `.env` with your API keys. The canonical reference is `.env.example`:

```bash
# Required for bot to work
TELEGRAM_BOT_TOKEN=your_bot_token_from_BotFather
LITELLM_MASTER_KEY=your_litellm_master_key

# At least one LLM provider key
OPENAI_API_KEY=your_openai_key
# CEREBRAS_API_KEY=...
# GROQ_API_KEY=...

# Langfuse (local observability — started by make docker-ml-up)
LANGFUSE_PUBLIC_KEY=pk-lf-dev
LANGFUSE_SECRET_KEY=sk-lf-dev
LANGFUSE_HOST=http://localhost:3001
```

See `.env.example` for the full variable list and [`LOCAL-DEVELOPMENT.md`](LOCAL-DEVELOPMENT.md) for the minimum env sets per profile.

## Step 3: Start Services

Start core services and verify health:

```bash
make local-up
make test-bot-health
```

For the full service map, profile stacks, and port list, see [`DOCKER.md`](../DOCKER.md).

## Step 4: Run Preflight Checks

```bash
make test-bot-health
```

The authoritative startup preflight runs in `telegram_bot/preflight.py` when the bot starts. See [`LOCAL-DEVELOPMENT.md`](LOCAL-DEVELOPMENT.md) for the full validation ladder.

## Step 5: Start the Bot

```bash
# Run bot natively (fast iteration, services must be running)
make run-bot

# Or run everything in Docker
make docker-bot-up
```

### Verify Bot is Connected

1. Open Telegram and search for your bot
2. Send `/start` — you should receive a welcome message
3. Send `/help` — you should receive help text

See [`LOCAL-DEVELOPMENT.md`](LOCAL-DEVELOPMENT.md) for the day-to-day workflow and native vs Docker trade-offs.

## Step 6: Run Ingestion (Optional)

To test with real data, see [`INGESTION.md`](INGESTION.md) for the full ingestion workflow:

```bash
make ingest-unified-preflight
make ingest-unified-bootstrap
make ingest-unified
```

## Common First-Day Issues

### Redis Connection Refused

```bash
# Check Redis is running
docker compose ps redis

# Restart Redis
docker compose restart redis
```

### Qdrant Collection Not Found

```bash
# Check Qdrant status
docker compose exec qdrant curl -s http://localhost:6333/collections

# Recreate collection
make ingest-unified-bootstrap
```

### Token/Authentication Errors

1. Verify `TELEGRAM_BOT_TOKEN` is valid
2. Check Langfuse keys are correct
3. Ensure `LITELLM_MASTER_KEY` and at least one provider key (`OPENAI_API_KEY`, `CEREBRAS_API_KEY`, or `GROQ_API_KEY`) are set

## Project Structure Overview

```
rag/
├── telegram_bot/         # Telegram bot implementation
│   ├── bot.py           # Main bot class (PropertyBot)
│   ├── graph/           # LangGraph pipeline (voice)
│   ├── agents/          # SDK agent & tools
│   ├── pipelines/       # Client fast-path pipeline
│   └── integrations/    # Cache, embeddings, etc.
├── src/
│   ├── api/             # RAG API (FastAPI)
│   ├── ingestion/       # Document ingestion
│   └── voice/           # Voice bot (LiveKit)
├── docs/                # Documentation
│   ├── runbooks/       # Operational runbooks
│   └── adr/            # Architecture decision records
└── tests/               # Test suite
```

## Key Documentation Links

| Topic | Link |
|-------|------|
| Local development setup | [LOCAL-DEVELOPMENT.md](LOCAL-DEVELOPMENT.md) |
| Pipeline architecture | [PIPELINE_OVERVIEW.md](PIPELINE_OVERVIEW.md) |
| Troubleshooting | [runbooks/README.md](runbooks/README.md) |
| Feature documentation | [BOT_ARCHITECTURE.md](BOT_ARCHITECTURE.md) |

## Next Steps

1. Read [LOCAL-DEVELOPMENT.md](LOCAL-DEVELOPMENT.md) for detailed setup
2. Review [PIPELINE_OVERVIEW.md](PIPELINE_OVERVIEW.md) to understand the architecture
3. Check [BOT_ARCHITECTURE.md](BOT_ARCHITECTURE.md) for bot internals
4. Explore `tests/` to understand testing patterns

## Getting Help

- **Issues**: Create a GitHub issue for bugs or feature requests
- **Internal docs**: See [docs/engineering/](engineering/) for development guidelines
- **Troubleshooting**: See [runbooks/README.md](runbooks/README.md) for common issues

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
| Langfuse | Recommended | Observability (`LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY`) |
| LiteLLM API | Yes | LLM calls (`LITELLM_API_KEY`) |
| BGE-M3 API | Optional | Embeddings (can use bundled model) |

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

Edit `.env` with your API keys:

```bash
# Required for bot to work
TELEGRAM_BOT_TOKEN=your_bot_token_from_BotFather

# LLM provider
LITELLM_API_KEY=your_litellm_api_key

# Langfuse (for observability)
LANGFUSE_PUBLIC_KEY=your_langfuse_public_key
LANGFUSE_SECRET_KEY=your_langfuse_secret_key
LANGFUSE_HOST=https://cloud.langfuse.com

# BGE-M3 (embeddings)
BGE_M3_URL=http://localhost:8000  # or hosted endpoint
```

See `.env.example` for full variable documentation.

## Step 3: Start Services

```bash
# Start all Docker services (Redis, Qdrant, etc.)
make docker-up

# Or with monitoring (Grafana, Loki)
make docker-up-dev
```

Verify services are healthy:

```bash
make docker-health
```

## Step 4: Run Preflight Checks

```bash
# Check all dependencies
make preflight

# Verify embeddings service
make embeddings-health
```

## Step 5: Start the Bot

```bash
# Start Telegram bot only
make docker-bot-up

# Or run directly (requires all services running)
uv run python -m telegram_bot.main
```

### Verify Bot is Connected

1. Open Telegram and search for your bot
2. Send `/start` — you should receive a welcome message
3. Send `/help` — you should receive help text

## Step 6: Run Ingestion (Optional)

To test with real data:

```bash
# Preflight checks for ingestion
make ingest-unified-preflight

# Bootstrap the collection
make ingest-unified-bootstrap

# Run continuous ingestion
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
3. Ensure `LITELLM_API_KEY` has not expired

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
| Troubleshooting | [.claude/rules/troubleshooting.md](../.claude/rules/troubleshooting.md) |
| Feature documentation | [.claude/rules/features/telegram-bot.md](../.claude/rules/features/telegram-bot.md) |

## Next Steps

1. Read [LOCAL-DEVELOPMENT.md](LOCAL-DEVELOPMENT.md) for detailed setup
2. Review [PIPELINE_OVERVIEW.md](PIPELINE_OVERVIEW.md) to understand the architecture
3. Check `.claude/rules/features/telegram-bot.md` for bot internals
4. Explore `tests/` to understand testing patterns

## Getting Help

- **Issues**: Create a GitHub issue for bugs or feature requests
- **Internal docs**: See `.claude/rules/` for development guidelines
- **Troubleshooting**: See `.claude/rules/troubleshooting.md` for common issues

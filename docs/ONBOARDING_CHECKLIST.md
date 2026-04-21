# Onboarding Checklist

New developer setup guide for the contextual RAG pipeline.

## Prerequisites

- [ ] Python 3.11+ (3.12 recommended)
- [ ] [uv](https://docs.astral.sh/uv/) installed
- [ ] Docker and Docker Compose
- [ ] Telegram Bot Token (from [@BotFather](https://t.me/BotFather))
- [ ] IDE with Python support (VS Code, PyCharm, etc.)

## 1. Repository Setup

```bash
# Clone the repository
git clone https://github.com/yastman/rag.git
cd rag

# Install dependencies
uv sync
```

## 2. Environment Configuration

```bash
# Copy environment template
cp .env.example .env

# Edit .env with your values:
# Required:
# - TELEGRAM_BOT_TOKEN
# - OPENAI_API_KEY (or LLM_BASE_URL for LiteLLM)
# - REDIS_PASSWORD
# - LANGFUSE_PUBLIC_KEY
# - LANGFUSE_SECRET_KEY
# - LANGFUSE_HOST
```

## 3. Service Startup

```bash
# Start core services (Redis, Qdrant, BGE-M3)
make local-up

# Verify the published local prerequisites for native bot startup
make test-bot-health
```

## 4. Bot Startup

```bash
# Run bot in development mode
make run-bot

# Or run via uv directly
uv run python -m telegram_bot.main
```

If you do set `REDIS_URL` manually for native runs, it must include the Redis password. Otherwise the bot derives the local URL from `REDIS_PASSWORD`.

`make test-bot-health` is the local helper for Redis/Qdrant/LiteLLM plus the optional localhost Postgres note. The full startup preflight still runs in [`telegram_bot/preflight.py`](/home/user/projects/rag-fresh-issue-1198/telegram_bot/preflight.py) when the bot starts, and that runtime path keeps the repo-local BGE-M3 health contract.

## 5. Validation

```bash
# Run linting and type checking
make check

# Run unit tests
make test-unit

# Run full test suite
make test-full
```

## 6. Key Files to Understand

| File | Purpose |
|------|---------|
| `README.md` | Project overview |
| `AGENTS.md` | Developer guidelines |
| `telegram_bot/bot.py` | Main bot entry point |
| `telegram_bot/graph/graph.py` | LangGraph pipeline |
| `docs/PIPELINE_OVERVIEW.md` | Runtime flows |
| `docs/engineering/sdk-registry.md` | SDK patterns |

## 7. Understanding the Pipeline

1. Read `docs/PIPELINE_OVERVIEW.md`
2. Read `docs/BOT_ARCHITECTURE.md`
3. Read `telegram_bot/graph/graph.py` (build_graph function)
4. Trace through a query: classify → guard → cache_check → retrieve → grade → rerank/generate → respond

## 8. Common Tasks

### Run specific tests
```bash
uv run pytest tests/unit/telegram_bot/ -v -k "test_name"
```

### Add a new dependency
```bash
uv add package_name
# Then update docs/engineering/sdk-registry.md
```

### Run ingestion
```bash
make ingest-unified-preflight
make ingest-unified-bootstrap
make ingest-unified
```

### Check Langfuse traces
```bash
# Local Langfuse at http://localhost:3000
open http://localhost:3000
```

## 9. Code Patterns to Follow

- **State management:** Use TypedDict for graph state, not Pydantic
- **DI:** Use GraphContext for service dependencies
- **Tracing:** Always use `@observe` decorator on node functions
- **Error handling:** Let exceptions propagate; middleware handles user messages
- **Testing:** Unit tests for nodes, integration tests for flows

## 10. Getting Help

- Read `docs/engineering/issue-triage.md` for debugging workflow
- Check existing docs in `docs/`
- Search code with `grepai` MCP tools
- Ask in team chat with context

## Optional: Voice Agent Setup

If working on voice features:

```bash
# Start voice services
make docker-voice-up

# Set additional env vars:
# - ELEVENLABS_API_KEY
# - LIVEKIT_URL
# - LIVEKIT_API_KEY
# - LIVEKIT_API_SECRET
```

## Optional: Mini App Setup

If working on the mini app:

```bash
cd mini_app
npm install
npm run dev
```

## Troubleshooting

| Issue | Solution |
|-------|----------|
| Redis connection refused | `docker compose up -d redis` |
| Qdrant timeout | `QDRANT_TIMEOUT=30` |
| MyPy errors | `make check` to identify issues |
| Import errors | `uv sync` to ensure dependencies installed |

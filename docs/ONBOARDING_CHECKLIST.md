***REMOVED*** Onboarding Checklist

New developer setup guide for the contextual RAG pipeline.

***REMOVED******REMOVED*** Prerequisites

- [ ] Python 3.11+ (3.12 recommended)
- [ ] [uv](https://docs.astral.sh/uv/) installed
- [ ] Docker and Docker Compose
- [ ] Telegram Bot Token (from [@BotFather](https://t.me/BotFather))
- [ ] IDE with Python support (VS Code, PyCharm, etc.)

***REMOVED******REMOVED*** 1. Repository Setup

```bash
***REMOVED*** Clone the repository
git clone https://github.com/yastman/rag.git
cd rag

***REMOVED*** Install dependencies
uv sync
```

***REMOVED******REMOVED*** 2. Environment Configuration

```bash
***REMOVED*** Copy environment template
cp .env.example .env

***REMOVED*** Edit .env with your values:
***REMOVED*** Required:
***REMOVED*** - TELEGRAM_BOT_TOKEN
***REMOVED*** - OPENAI_API_KEY (or LLM_BASE_URL for LiteLLM)
***REMOVED*** - REDIS_PASSWORD
***REMOVED*** - LANGFUSE_PUBLIC_KEY
***REMOVED*** - LANGFUSE_SECRET_KEY
***REMOVED*** - LANGFUSE_HOST
```

***REMOVED******REMOVED*** 3. Service Startup

```bash
***REMOVED*** Start core services (Redis, Qdrant, BGE-M3)
make local-up

***REMOVED*** Verify the published local prerequisites for native bot startup
make test-bot-health
```

***REMOVED******REMOVED*** 4. Bot Startup

```bash
***REMOVED*** Run bot in development mode
make run-bot

***REMOVED*** Or run via uv directly
uv run python -m telegram_bot.main
```

If you do set `REDIS_URL` manually for native runs, it must include the Redis password. Otherwise the bot derives the local URL from `REDIS_PASSWORD`.

`make test-bot-health` is the local helper for Redis/Qdrant/LiteLLM plus the optional localhost Postgres note. The full startup preflight still runs in [`telegram_bot/preflight.py`](../telegram_bot/preflight.py) when the bot starts, and that runtime path keeps the repo-local BGE-M3 health contract.

***REMOVED******REMOVED*** 5. Validation

```bash
***REMOVED*** Run linting and type checking
make check

***REMOVED*** Run unit tests
make test-unit

***REMOVED*** Run full test suite
make test-full
```

For trace validation and the canonical Compose env override pattern, see [`DOCKER.md`](../DOCKER.md).

***REMOVED******REMOVED*** 6. Key Files to Understand

| File | Purpose |
|------|---------|
| `README.md` | Project overview |
| `AGENTS.md` | Developer guidelines |
| `telegram_bot/bot.py` | Main bot entry point |
| `telegram_bot/graph/graph.py` | LangGraph pipeline |
| `docs/PIPELINE_OVERVIEW.md` | Runtime flows |
| `docs/engineering/sdk-registry.md` | SDK patterns |

***REMOVED******REMOVED*** 7. Understanding the Pipeline

1. Read `docs/PIPELINE_OVERVIEW.md`
2. Read `docs/BOT_ARCHITECTURE.md`
3. Read `telegram_bot/graph/graph.py` (build_graph function)
4. Trace through a query: classify → guard → cache_check → retrieve → grade → rerank/generate → respond

***REMOVED******REMOVED*** 8. Common Tasks

***REMOVED******REMOVED******REMOVED*** Run specific tests
```bash
uv run pytest tests/unit/telegram_bot/ -v -k "test_name"
```

***REMOVED******REMOVED******REMOVED*** Add a new dependency
```bash
uv add package_name
***REMOVED*** Then update docs/engineering/sdk-registry.md
```

***REMOVED******REMOVED******REMOVED*** Run ingestion
```bash
make ingest-unified-preflight
make ingest-unified-bootstrap
make ingest-unified
```

***REMOVED******REMOVED******REMOVED*** Check Langfuse traces
```bash
***REMOVED*** Local Langfuse at http://localhost:3000
open http://localhost:3000
```

***REMOVED******REMOVED*** 9. Code Patterns to Follow

- **State management:** Use TypedDict for graph state, not Pydantic
- **DI:** Use GraphContext for service dependencies
- **Tracing:** Always use `@observe` decorator on node functions
- **Error handling:** Let exceptions propagate; middleware handles user messages
- **Testing:** Unit tests for nodes, integration tests for flows

***REMOVED******REMOVED*** 10. Getting Help

- Read `docs/engineering/issue-triage.md` for debugging workflow
- Check existing docs in `docs/`
- Search code with `grepai` MCP tools
- Ask in team chat with context

***REMOVED******REMOVED*** Optional: Voice Agent Setup

If working on voice features:

```bash
***REMOVED*** Start voice services
make docker-voice-up

***REMOVED*** Set additional env vars:
***REMOVED*** - ELEVENLABS_API_KEY
***REMOVED*** - LIVEKIT_URL
***REMOVED*** - LIVEKIT_API_KEY
***REMOVED*** - LIVEKIT_API_SECRET
```

***REMOVED******REMOVED*** Optional: Mini App Setup

If working on the mini app:

```bash
cd mini_app
npm install
npm run dev
```

***REMOVED******REMOVED*** Troubleshooting

| Issue | Solution |
|-------|----------|
| Redis connection refused | `docker compose up -d redis` |
| Qdrant timeout | `QDRANT_TIMEOUT=30` |
| MyPy errors | `make check` to identify issues |
| Import errors | `uv sync` to ensure dependencies installed |

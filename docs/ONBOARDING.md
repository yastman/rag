# Developer Onboarding

The single new-contributor guide for the RAG Fresh project. Follow it top to bottom and you will have a working local environment, understand the pipeline, and know where to look next.

---

## Prerequisites

- [ ] **Python 3.12+**
- [ ] **[uv](https://docs.astral.sh/uv/)** package manager installed
- [ ] **Docker & Docker Compose v2**
- [ ] **Git**
- [ ] **Telegram Bot Token** from [@BotFather](https://t.me/BotFather)
- [ ] **At least one LLM provider key** (OpenAI, Cerebras, or Groq)
- [ ] IDE with Python support (VS Code, PyCharm, etc.)

---

## Repository Setup

- [ ] Clone and install dependencies:

```bash
git clone https://github.com/yastman/rag.git
cd rag
uv sync
```

---

## Environment Configuration

- [ ] Copy the environment template and fill in your keys:

```bash
cp .env.example .env
```

At minimum set:

| Variable | Purpose |
|----------|---------|
| `TELEGRAM_BOT_TOKEN` | Bot functionality |
| `LITELLM_MASTER_KEY` | LLM proxy auth |
| One of `OPENAI_API_KEY` / `CEREBRAS_API_KEY` / `GROQ_API_KEY` | LLM provider |

`.env.example` is the canonical reference for all available variables. See [LOCAL-DEVELOPMENT.md](LOCAL-DEVELOPMENT.md) for minimum env sets per Compose profile.

---

## Start Services

- [ ] Start core services and confirm health:

```bash
make local-up
make test-bot-health
```

For the full service map, profile stacks, ports, and env requirements see [DOCKER.md](../DOCKER.md).

---

## Validate

- [ ] Start the bot:

```bash
make run-bot
```

- [ ] In Telegram, send `/start` to your bot and confirm you receive a welcome message.
- [ ] Send `/help` and confirm help text is returned.

The full startup preflight runs automatically in `telegram_bot/preflight.py`. See [LOCAL-DEVELOPMENT.md](LOCAL-DEVELOPMENT.md) for the complete validation ladder and native vs Docker trade-offs.

- [ ] Run linting and tests:

```bash
make check
make test-unit
```

---

## Understand the Pipeline

Work through these in order:

1. Read [PIPELINE_OVERVIEW.md](PIPELINE_OVERVIEW.md) for the high-level runtime flows.
2. Read [BOT_ARCHITECTURE.md](BOT_ARCHITECTURE.md) for the bot layer design.
3. Open `telegram_bot/graph/graph.py` and trace the `build_graph` function.
4. Follow a query through the nodes: classify, guard, cache_check, retrieve, grade, rerank/generate, respond.

---

## Key Code Patterns

- **State management** -- use `TypedDict` for graph state, not Pydantic.
- **Dependency injection** -- use `GraphContext` for service dependencies.
- **Tracing** -- always decorate node functions with `@observe`.
- **Error handling** -- let exceptions propagate; middleware handles user messages.
- **Testing** -- unit tests for nodes, integration tests for flows.

---

## Common Tasks

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

See [INGESTION.md](INGESTION.md) for the full ingestion workflow.

### Check Langfuse traces

Local Langfuse runs at `http://localhost:3001` (see [DOCKER.md](../DOCKER.md) for ports and profiles).

### Voice agent (optional)

```bash
make docker-voice-up
```

Requires additional env vars: `ELEVENLABS_API_KEY`, `LIVEKIT_URL`, `LIVEKIT_API_KEY`, `LIVEKIT_API_SECRET`.

---

## Troubleshooting

| Issue | Solution |
|-------|----------|
| Redis connection refused | `docker compose up -d redis` or `docker compose restart redis` |
| Qdrant collection not found | Run `make ingest-unified-bootstrap` |
| Qdrant timeout | Set `QDRANT_TIMEOUT=30` in `.env` |
| Token/auth errors | Verify `TELEGRAM_BOT_TOKEN`, `LITELLM_MASTER_KEY`, and at least one provider key are set |
| MyPy errors | Run `make check` to identify issues |
| Import errors | Run `uv sync` to ensure dependencies installed |

For deeper operational investigations see [runbooks/README.md](runbooks/README.md).

---

## Next Steps

1. Read [LOCAL-DEVELOPMENT.md](LOCAL-DEVELOPMENT.md) for the full day-to-day workflow.
2. Read [DEVELOPER_GUIDE.md](DEVELOPER_GUIDE.md) for development conventions.
3. Explore `tests/` to understand testing patterns.
4. Check [engineering/issue-triage.md](engineering/issue-triage.md) for the debugging workflow.
5. Browse [docs/README.md](README.md) for the full documentation index.

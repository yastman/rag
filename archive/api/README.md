# src/api/

FastAPI RAG API — HTTP wrapper around the LangGraph pipeline.

## Purpose

Exposes a single synchronous RAG endpoint (`POST /query`) and a readiness probe (`GET /health`) for external integrations (mini app, voice, third-party clients).

## Entrypoints

| Entrypoint | Role |
|------------|------|
| [`main.py`](./main.py) `app` | FastAPI application with lifespan initialization |
| [`main.py`](./main.py) `query()` | `POST /query` — runs RAG via the LangGraph pipeline |
| [`main.py`](./main.py) `health()` | `GET /health` — readiness probe |
| [`schemas.py`](./schemas.py) | Pydantic request/response models |

## Boundaries

- **Thin wrapper**: the API delegates 100 % of RAG logic to `telegram_bot.graph.graph.build_graph()`. No retrieval or generation logic lives here.
- **No Telegram imports** in request handling. The API is transport-agnostic.
- Observability parity with the bot: Langfuse traces and scores are written the same way.

## Runtime Services

- **Qdrant** — vector search
- **Redis** — semantic cache
- **BGE-M3** — embeddings
- **Langfuse** — tracing (optional)

## Focused Checks

```bash
# Type-check
make check

# API tests
pytest src/api/

# Health check (when running)
curl http://localhost:8080/health
```

## See Also

- [`../../telegram_bot/graph/`](../../telegram_bot/graph/) — LangGraph pipeline implementation
- [`../../telegram_bot/services/`](../../telegram_bot/services/) — Services reused by the API lifespan

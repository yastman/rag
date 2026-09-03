# telegram_bot/

Telegram transport layer and bot orchestration for the contextual RAG system.

## Purpose

Handles Telegram updates (text, voice, callbacks), delegates all retrieval and generation to pipelines, and surfaces answers back to users. Keeps transport concerns separate from domain logic.

## Entrypoints

| Entrypoint | Role |
|------------|------|
| [`main.py`](./main.py) `main()` | CLI entry point: configures logging, initializes observability, starts the bot runtime class with retry |
| [`bot.py`](./bot.py) `PropertyBot` | Bot lifecycle, handlers, and dispatcher wiring. The class name is legacy; the runtime is domain-adaptable. |
| [`preflight/`](./preflight/) | Startup health checks (Redis, Qdrant, external deps) |

## Boundaries

- **Transport does not absorb retrieval/domain logic.** `bot.py` handlers call into `pipeline/` (supervisor) or `agents`; they do not query Qdrant or run LLM prompts directly.
- **Ingestion determinism** is owned by `src/ingestion/`; bot code must not modify collection schemas or manifest identity.

## Related Runtime Services

- **Qdrant** — vector search (collections: documents, domain catalogs)
- **Redis** — caching, throttling, user context
- **BGE-M3** — dense + sparse embeddings (local REST API)
- Structured logging — observability (optional)
- Voice input — optional and configuration-driven (`VOICE_ENABLED` + STT key in `BotConfig`, #3240); handled in-process via `dialogs/` (catalog + demo dialogs). Unconfigured or failing voice degrades to typed input; no LiveKit sidecar

## Dependencies

There is no bot-local manifest/lock (#3210). The repo-root `pyproject.toml`
+ `uv.lock` are the single dependency authority for the Telegram runtime:
local installs use `uv sync --extra telegram`, and `telegram_bot/Dockerfile`
resolves the production image with `uv sync --locked --no-dev --extra telegram`
from the same frozen lock. Add bot runtime dependencies to the root
`telegram` extra — never reintroduce a nested `telegram_bot/pyproject.toml`.

## Focused Checks

```bash
# Lint and type-check
make check

# Core gate (fast) + no-service integration/smoke lane
make test-core
make test
```

## Directory Guide

| Directory | Concern |
|-----------|---------|
| `handlers/` | Per-feature handlers extracted from `bot.py` (#2983): commands, catalog, favorites, handoff, CRM callbacks, feedback |
| `agents/` | Agent SDK tools (RAG retrieval delegated to `src/runtime/pipeline/`) |
| `dialogs/` | aiogram-dialog packages: catalog, filter, funnel + demo/viewing/settings |
| `pipeline/` | Supervisor + pre-agent + streaming (agent orchestration) |
| `pipelines/` | Shared pre-agent state contract (`state_contract.py`) |
| `lifecycle/` | Bot startup/teardown, postgres bootstrap, service wiring |
| `integrations/` | Embeddings, cache, prompt manager, memory (several are shims to `src.runtime.integrations`) |
| `observability/` | Trace/context helpers + no-op `@observe` shim (Langfuse removed) |
| `middlewares/` | Aiogram middlewares (throttling, errors, i18n) |
| `services/` | Bot services: `rag/`, `apartment/`, `crm/`, `generation/`, `observability/`, `util/` |
| `preflight/` | Startup health checks (Redis, Qdrant, external deps) |

## See Also

- [`AGENTS.override.md`](AGENTS.override.md) — Bot-specific scope rules and validation
- [`../DOCKER.md`](../DOCKER.md) — Docker bring-up and service dependencies
- [`../docs/LOCAL-DEVELOPMENT.md`](../docs/LOCAL-DEVELOPMENT.md) — Local setup and validation ladder
- [`../docs/runbooks/README.md`](../docs/runbooks/README.md) — Operational troubleshooting
- [`../src/retrieval/`](../src/retrieval/) — Search engine implementations
- [`../src/ingestion/`](../src/ingestion/) — Document ingestion pipeline

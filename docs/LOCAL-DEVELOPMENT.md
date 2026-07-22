# Local Development

How to run and validate the RAG Q&A chatbot on your machine. Runtime is **Docker Compose
only** (no k8s). See [`../DOCKER.md`](../DOCKER.md) for the full Compose/ports/env reference
and [`README.md`](README.md) for the documentation map.

## Prerequisites

- **Python 3.12+**
- **[`uv`](https://docs.astral.sh/uv/)** — dependency + venv manager
- **Docker** with the Compose plugin

## First-time setup

### Linux / POSIX

```bash
cp .env.example .env     # fill in credentials (Telegram token, API keys)
uv sync                  # core + dev tools (PEP 735 dev group)
uv sync --extra telegram # bot dependencies (aiogram, LangGraph)
# optional: uv sync --extra docling-native   # Docling + PyMuPDF ingestion pipeline
```

### Windows (PowerShell)

```powershell
Copy-Item .env.example .env        # fill in credentials
uv sync                            # core + dev tools (Python 3.12)
uv sync --extra telegram           # bot dependencies
# optional: uv sync --extra docling-native   # Docling + PyMuPDF ingestion
# Preflight validation:
scripts/windows_preflight.ps1
```

## Bring up the sidecar stack

### Linux / POSIX

```bash
make core-min-up     # minimal: Qdrant + Redis
make core-up         # full: + BGE-M3, PostgreSQL
```

### Windows (PowerShell)

```powershell
# Minimal: Qdrant + Redis (standalone core stack)
docker compose -f compose.core.yml up -d

# Full: + BGE-M3, PostgreSQL
docker compose -f compose.yml -f compose.dev.yml up -d
```

The retrieval stack uses dense + sparse + ColBERT from the local BGE-M3. Tunables live in `.env.example` (e.g. `QDRANT_QUANTIZATION_MODE`, `REDIS_MAX_CONNECTIONS`).

## Run the bot

### Linux / POSIX

```bash
make run-bot          # run natively against the running sidecars
make docker-bot-up    # run the bot inside the Compose stack
```

### Windows (PowerShell)

```powershell
# Run natively (sidecars must be running first)
uv run python -m telegram_bot.main
```

## Validate before you push

> The `make` commands below are Linux/POSIX only. On Windows run tests via
> `uv run pytest` directly (see [`tests/README.md`](../tests/README.md)).

| Command | What it checks |
|---|---|
| `make check` | Ruff lint + MyPy |
| `make test-core` | Monolith core gate (~91 tests, ~8s) — run first for any `src/core` or `src/runtime` change |
| `make test` | Unit + critical graph paths — for adapter/service changes |
| `make test-contract` | Static contract tests (trace/schema/architecture) |
| `make test-cov` | Coverage report (`[tool.coverage]` `fail_under=80`) — currently a manual gate |
| `make e2e-core-live` | Golden E2E: indexes a fixture corpus and runs the full spine through `run_assistant_request` (needs `make core-up`) |
| `make qdrant-audit-indexes` | Audit Qdrant payload indexes |

Recommended local PR readiness: `make check && make test && make test-contract`.
Core changes → run `make test-core` first. Subsystem `AGENTS.override.md` files may pin
tighter commands — read the nearest one before editing an area.

> CI runs **static/lint guardrails only** (Ruff, MyPy, Semgrep, lockfile, Compose config).
> The pytest suites are local/manual. See [`../tests/README.md`](../tests/README.md) for the
> full tier→command map and [`engineering/test-writing-guide.md`](engineering/test-writing-guide.md)
> for conventions.

## Operational checks

See [`runbooks/README.md`](runbooks/README.md) for service health, preflight, and
infra-config runbooks.

# Local Development

How to run and validate the RAG Q&A chatbot on your machine. Runtime is **Docker Compose
only** (no k8s). See [`../DOCKER.md`](../DOCKER.md) for the full Compose/ports/env reference
and [`README.md`](README.md) for the documentation map.

## Prerequisites

- **Python 3.12+**
- **[`uv`](https://docs.astral.sh/uv/)** — dependency + venv manager
- **Docker** with the Compose plugin

## First-time setup

```bash
cp .env.example .env     # fill in credentials (Telegram token, API keys)
uv sync                  # core + dev tools (PEP 735 dev group)
# optional extras, only when needed:
uv sync --extra ml-local # local BGE-M3 / cross-encoder inference (torch)
uv sync --extra docling-native   # Docling + PyMuPDF ingestion pipeline (in-process)
```

## Bring up the sidecar stack

```bash
make core-min-up     # minimal: Qdrant + Redis
make core-up         # full: + BGE-M3, PostgreSQL
```

The retrieval stack uses dense + sparse + ColBERT from the local BGE-M3. Tunables live in `.env.example` (e.g. `QDRANT_QUANTIZATION_MODE`, `REDIS_MAX_CONNECTIONS`).

## Run the bot

```bash
make run-bot          # run natively against the running sidecars
make docker-bot-up    # run the bot inside the Compose stack
```

## Validate before you push

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

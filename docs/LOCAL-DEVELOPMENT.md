# Local Development

How to run and validate the RAG Q&A chatbot on your machine. Runtime is **Docker Compose
only** (no k8s). See [`../DOCKER.md`](../DOCKER.md) for the full Compose/ports/env reference
and [`README.md`](README.md) for the documentation map.

## Prerequisites

- **Python 3.12**
- **[`uv`](https://docs.astral.sh/uv/)** — dependency + venv manager
- **Docker** with the Compose plugin (Docker Desktop's Linux engine on Windows)

## First-time setup

### Linux / POSIX

```bash
cp .env.example .env     # fill in credentials (Telegram token, API keys)
uv sync                  # core + dev tools (PEP 735 dev group)
uv sync --extra telegram # bot dependencies (aiogram, LangGraph)
make setup-hooks         # install commit and push hooks
# optional: uv sync --extra docling-native   # Docling + PyMuPDF ingestion pipeline
```

### Windows (PowerShell)

```powershell
uv python install 3.12
Copy-Item .env.example .env        # fill in credentials
uv sync                            # core + dev tools (Python 3.12)
uv sync --extra telegram           # bot dependencies
uv run pre-commit install
uv run pre-commit install --hook-type pre-push
# optional: uv sync --extra docling-native   # Docling + PyMuPDF ingestion
# Preflight validation:
pwsh -NoProfile -ExecutionPolicy Bypass -File scripts/windows_preflight.ps1 -Mode Static
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

### Local meeting-RAG sidecars (Windows / Docker Desktop)

This isolated stack starts only Qdrant, Redis, and the existing BGE-M3 ONNX
service. Ingestion and the RAG API run as native Python; it does not start
Telegram, PostgreSQL, or an application container.

```powershell
# Set this to the directory containing model.int8.onnx and model.int8.onnx.data.
$env:BGE_M3_ONNX_MODEL_HOST_DIR = "C:\data\models\bge_m3_onnx_int8"

# Record the reused model identity before the build.
Get-FileHash "$env:BGE_M3_ONNX_MODEL_HOST_DIR\model.int8.onnx" -Algorithm SHA256
Get-FileHash "$env:BGE_M3_ONNX_MODEL_HOST_DIR\model.int8.onnx.data" -Algorithm SHA256

# Build/start, then wait until each service reports healthy.
docker compose -f compose.local-rag.yml up -d --build
docker compose -f compose.local-rag.yml ps
```

`bge-m3` builds the repository's existing `services/bge-m3-api` image and
bakes those two artifacts into it; no model is downloaded, replaced, or
bind-mounted at runtime. Its model identity is `BAAI/bge-m3` at revision
`5617a9f61b028005a4858fdac845db406aefb181`; retain the two SHA-256 outputs
with the local smoke evidence.

The checked-in local artifact evidence is:

| Artifact | SHA-256 |
|---|---|
| `model.int8.onnx` | `e4b993d0e996ab07ec5ee576d2f102af6d534381d5861bdfcbc24981efc01c80` |
| `model.int8.onnx.data` | `2976067612ae0a7c804a32b5abe64f512056655c689455c6a994029529c62c28` |

All ports are loopback-only: Qdrant `127.0.0.1:6333`, Redis
`127.0.0.1:6379`, and BGE-M3 `127.0.0.1:8000`. Check readiness directly if
`ps` has not yet reported `healthy`:

```powershell
curl.exe -fsS http://127.0.0.1:6333/readyz
docker compose -f compose.local-rag.yml exec redis redis-cli ping
curl.exe -fsS http://127.0.0.1:8000/health
```

Stop only these sidecars and retain their local data:

```powershell
docker compose -f compose.local-rag.yml down
```

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
| Commit | Automatic pre-commit hooks; `make check` runs Ruff lint + MyPy |
| Push | Automatic pre-push hooks; `make pre-push` manually runs lint + format check + core tests |
| `make test-core` | Monolith core gate (~91 tests, ~8s) — run first for any `src/core` or `src/runtime` change |
| `make test` | Unit + critical graph paths — for adapter/service changes |
| `make test-contract` | Static contract tests (trace/schema/architecture) |
| Candidate | `make candidate-check` is the authoritative local delivery gate (`check-frozen` + `test` + `test-contract`) |
| Major candidate | `make test-full` runs all local tiers manually |
| `make test-cov` | Coverage report (`[tool.coverage]` `fail_under=80`) — currently a manual gate |
| `make e2e-core-live` | Golden E2E: indexes a fixture corpus and runs the full spine through `run_assistant_request` (needs `make core-up`) |
| `make qdrant-audit-indexes` | Audit Qdrant payload indexes |

Run `make candidate-check` before delivery.
Core changes → run `make test-core` first. Subsystem `AGENTS.override.md` files may pin
tighter commands — read the nearest one before editing an area.

> GitHub runs no pytest. All pytest suites are local. On Windows the pre-push core hook invokes
> `uv run --no-sync pytest` directly, without requiring Make. Run Linux portability and release
> verification locally through WSL or a container. See [`../tests/README.md`](../tests/README.md)
> for direct commands and [`engineering/test-writing-guide.md`](engineering/test-writing-guide.md)
> for conventions.

## Operational checks

See [`runbooks/README.md`](runbooks/README.md) for service health, preflight, and
infra-config runbooks.

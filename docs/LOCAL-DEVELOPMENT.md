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
```

### Windows (PowerShell)

```powershell
uv python install 3.12
Copy-Item .env.example .env        # fill in credentials
uv sync                            # core + dev tools (Python 3.12)
uv sync --extra telegram           # bot dependencies
uv run pre-commit install
uv run pre-commit install --hook-type pre-push
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

> The `make` commands below remain Linux/POSIX only. On Windows, run the native
> full-suite equivalent; Full locates `uv` and runs `uv sync --all-extras
> --all-groups` before checking the native venv and running tests:
>
> ```powershell
> pwsh -NoProfile -ExecutionPolicy Bypass -File scripts/windows_preflight.ps1 -Mode Full
> ```

| Command | What it checks |
|---|---|
| Commit | Automatic pre-commit hooks; `make check` runs Ruff lint + MyPy |
| Push | Automatic pre-push hooks; `make pre-push` manually runs lint + format check + core tests |
| `make test-core` | Monolith core gate (~91 tests, ~8s) — run first for any `src/core` or `src/runtime` change |
| `make test` | Unit + critical graph paths — for adapter/service changes |
| `make test-contract` | Static contract tests (trace/schema/architecture) |
| Candidate | `make candidate-check` is the authoritative local delivery gate (`check-frozen` + `test` + `test-contract`) |
| Major candidate | `make test-full` runs all local tiers manually; on Windows use `scripts/windows_preflight.ps1 -Mode Full` |
| `make test-cov` | Coverage report (`[tool.coverage]` `fail_under=80`) — currently a manual gate |
| `make e2e-core-live` | Golden E2E: indexes a fixture corpus and runs the full spine through `run_assistant_request` (needs `make core-up`) |
| `make qdrant-audit-indexes` | Audit Qdrant payload indexes |
| `make qdrant-ensure-indexes` | Create missing contract payload indexes for BOTH product collections (non-destructive, #3202) |
| `make demo-bootstrap` | Idempotent demo setup/ingest/verify for BOTH Qdrant collections (#3202) |
| `make demo-verify` | Read-only readiness gate for both Qdrant collections (#3202) |

Run `make candidate-check` before delivery.
Core changes → run `make test-core` first. Subsystem `AGENTS.override.md` files may pin
tighter commands — read the nearest one before editing an area.

## Demo data readiness (Qdrant, #3202)

Startup refuses to poll unless **both** product collections are ready — the configured
knowledge collection (`QDRANT_COLLECTION`, with quantization suffix) and the hard-coded
`apartments` collection. Contracts live in `src/runtime/qdrant/readiness.py`. **Startup
enforces schema and counts only**: vector names and dimensions (`dense`/`colbert` @1024,
`bm42` sparse), payload indexes, and a non-empty point count.

The deterministic demo probes — shipped apartment rows reachable through the production
filter path, the shipped demo corpus documents present (anchor `article_115` from
`data/test/sample_articles.json`), and an intentional no-result query staying empty — run
via `make demo-bootstrap` / `make demo-verify`, not at bot startup. Note these corpus
probes prove the shipped demo data; the live known-corpus question contract-locked by
#3200 ("Сколько стоит студия у моря в Sunny Beach?", doc `sunny_beach_studio`) is a
live-probe/fixture concern and is not part of the shipped Qdrant demo corpus.

- **Fresh bootstrap**: `make demo-bootstrap` creates missing collections with the contract
  schema and ingests the shipped demo data (`data/apartments.csv`,
  `data/test/sample_articles.json`) — the ingest step needs the BGE-M3 service up.
- **Populated environments** are preserved: bootstrap never drops or rewrites data, and
  ingest only runs against an empty collection. Verification skips shipped-data probes when
  the demo points are absent (a populated catalog without the shipped sample rows is valid).
- **Missing / empty / schema-incompatible** collections stop startup with per-kind
  remediation (`make demo-bootstrap`, `make qdrant-ensure-indexes`, rollback notes below).
  A legitimate no-result search is not a readiness failure — only shipped demo queries that
  fail against otherwise-ready data are.

### Rollback

Collections are never deleted by the readiness gate or bootstrap. To roll back a demo
bootstrap: delete the freshly created collections explicitly
(`DELETE /collections/{name}` — destructive, operator-initiated) and re-run your previous
ingestion path; snapshots can be taken first via `make qdrant-backup`. To move a populated
environment off an incompatible schema: snapshot (`make qdrant-backup`), export points,
re-create the collection under the contract schema, and re-index — see
[`runbooks/`](runbooks/README.md) and [`INGESTION.md`](INGESTION.md).

> GitHub runs no pytest. All pytest suites are local. On Windows the pre-push core hook invokes
> `uv run --no-sync pytest` directly, without requiring Make. Run Linux portability and release
> verification locally through WSL or a container. See [`../tests/README.md`](../tests/README.md)
> for direct commands and [`engineering/test-writing-guide.md`](engineering/test-writing-guide.md)
> for conventions.

## Operational checks

See [`runbooks/README.md`](runbooks/README.md) for service health, preflight, and
infra-config runbooks.

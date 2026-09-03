# Tests

This directory contains the full test pyramid for the contextual RAG system.
For test-writing conventions, see [`docs/engineering/test-writing-guide.md`](../docs/engineering/test-writing-guide.md).

## Directory Structure

```
tests/
├── conftest.py          # Shared fixtures and hooks
├── unit/                # Fast, isolated tests (mocked/no external deps)
│   └── e2e_adapters/    # Unit checks for E2E adapters/config/validators (not live E2E)
├── contract/            # Static contracts: trace families, span coverage, error shapes
├── integration/         # Service-aware paths and real component interaction
├── smoke/               # Quick health checks against live services
├── eval/                # RAG evaluation (RAGAS, ground_truth.json)
├── baseline/            # (empty; Langfuse baseline metrics removed, #2844)
├── chaos/               # Resilience tests (service failures, LLM fallbacks)
├── load/                # Load/throughput and Redis eviction tests
├── e2e/                 # End-to-end pipeline and Telegram E2E tests
├── fixtures/            # Shared test data and CI env stubs (e.g., compose.ci.env)
└── data/                # Test datasets and generated assets
```

## Test Tiers

### Local-fast checks (no Docker required)
These are the default gate for PRs and local development.

| Tier | Location | What it proves | Typical duration |
|------|----------|----------------|------------------|
| Unit | `tests/unit/` | Isolated logic with mocks/fakes | Seconds |
| Contract | `tests/contract/` | Trace/schema contracts via static analysis | Seconds |

### Tier to command / CI mapping

| What | Scope | Coverage threshold |
|------|-------|--------------------|
| `make test` | core gate: `test-core` + no-service integration/smoke lane | none |
| `make test-contract` | contract only (`tests/contract/`) | none |
| Local delivery gate | `make candidate-check` (`check-frozen` + `test` + `test-contract`) | coverage remains a separate `make test-cov` check |

Commit hooks handle fast file checks. Push hooks add static/security checks and the core pytest
gate. GitHub runs no pytest; local results are authoritative. Run `make test-full` for a major
candidate and use WSL or a container for Linux portability and release verification.

### Heavy / runtime checks (services or credentials required)
Run these selectively, not on every save.

| Tier | Location | What it proves | Typical duration |
|------|----------|----------------|------------------|
| Integration | `tests/integration/` | Real service interaction (Qdrant, Redis, APIs) | Minutes |
| Smoke | `tests/smoke/` | Live service health and routing sanity | Minutes |
| Eval | `tests/eval/` | RAG quality (faithfulness, relevance) | Minutes |
| Chaos | `tests/chaos/` | Degraded-service behavior and fallbacks | Minutes |
| Load | `tests/load/` | Concurrent throughput and cache eviction | Minutes |
| E2E | `tests/e2e/` | Full-stack pipeline and Telegram flows | Slow |

Canonical E2E placement:
- Live end-to-end scenarios belong only to `tests/e2e/`.
- `tests/unit/e2e_adapters/` is unit-only coverage for E2E helper code (config, adapters, validators) and must stay in the local-fast lane.

## Commands

### Quick checks (lint + types)
```bash
make check
```

### Fast test gate (unit + critical graph paths)
```bash
make test
```

### Core unit tests (parallel, default local gate)
```bash
PYTEST_ADDOPTS='-n auto --dist=worksteal' make test-unit
```

### Focused run (preferred while developing)
```bash
uv run pytest tests/unit/test_<module>.py -q
```

### Contract tests (no Docker)
```bash
make test-contract
```

### Windows (PowerShell)
`make` and Bash examples are POSIX-only. Run the implemented preflight:

```powershell
pwsh -NoProfile -ExecutionPolicy Bypass -File scripts/windows_preflight.ps1 -Mode Static
pwsh -NoProfile -ExecutionPolicy Bypass -File scripts/windows_preflight.ps1 -Mode Tests
uv run --no-sync --python 3.12 python -m pytest tests/contract -q -n 0
```

### Integration tests (requires services)
```bash
make test-integration        # graph paths only (~5s, no Docker)
make test-integration-full   # all integration tests (requires Docker)
```

### Smoke tests (requires live services)
```bash
make test-smoke
make test-preflight          # Qdrant/Redis config checks
```

### Load / chaos / nightly
```bash
make test-load-eviction      # Redis eviction tests
make test-nightly            # chaos + smoke + slow unit
```

### E2E
```bash
make e2e-test                # pytest E2E suite (live services)
make e2e-telegram-test       # Telegram userbot runner
make bot-response-smoke      # #2192: prove make bot actually answers
```

#### Telethon E2E runner — unit tests vs live run

Unit tests (no credentials needed, no live bot required):
```bash
uv run pytest tests/unit/scripts -k e2e_runner -q
```

Live end-to-end run against a real bot (requires `.env` with valid credentials):
```bash
make e2e-telegram-test  # requires: TELEGRAM_API_ID, TELEGRAM_API_HASH, E2E_BOT_USERNAME in .env; live bot running
# or directly:
uv run python scripts/e2e/runner.py --no-judge          # passthrough mode
uv run python scripts/e2e/runner.py --group immigration # specific group
```

`make bot-response-smoke` runs five preflight stages (env vars, Telethon
session file, `getMe` username match, `getWebhookInfo` empty, polling
lock state) before delegating to `scripts.e2e.quick_test` for one safe
query. Use it to gate "make bot is healthy" against "make bot answers".

### RAG evaluation
```bash
make eval-rag                # RAGAS on ground_truth.json
make eval-rag-quick          # 10-sample subset
make eval-rag-full           # RAGAS + DeepEval
```


### Baseline / observability

> `tests/baseline/` was removed in P19 (Langfuse integration removed, #2844). The `make baseline-smoke` and `make baseline-compare` targets are no longer available. Observability is through structured logs.

### Compose validation (for runtime-impacting changes)
When changing `compose*.yml`, Dockerfiles, or service definitions, verify the effective config:

```bash
docker compose -f compose.yml -f compose.dev.yml config --services
```

CI uses `tests/fixtures/compose.ci.env` for interpolation validation:
```bash
COMPOSE_DISABLE_ENV_FILE=1 docker compose --env-file tests/fixtures/compose.ci.env -f compose.yml -f compose.dev.yml config --quiet
```

### Other useful commands
```bash
make test-cov                # coverage report
make test-lf                 # last failed only
make test-profile            # slowest tests
make test-store-durations    # update .test_durations for CI sharding
```

## Markers

Markers are defined in `pyproject.toml`. Common ones:

- `unit` — core unit tests
- `integration` — integration tests
- `slow` — tests taking > 5 seconds
- `smoke` — smoke tests
- `chaos` — resilience/failure injection
- `load` — load/performance tests
- `e2e` — end-to-end tests
- `requires_extras` — needs optional dependencies (skipped in core tier)
- `kommo` — live Kommo CRM tests (requires token)

See `pyproject.toml` for the full marker list (including exclusions for old API tests).

## Key Test Files

| File | Description |
|------|-------------|
| `unit/test_qdrant_service.py` | QdrantService with mocked client |
| `unit/test_small_to_big.py` | Small-to-big chunk expansion |
| `regression/test_rag_core_regression.py` | RAG core regression suite |
| `unit/test_local_compose_contract.py` | Compose config validation |
| `contract/test_layering_contract.py` | Architecture layering contract |
| `contract/test_no_langfuse_sdk_import_contract.py` | No Langfuse SDK imports remain |
| `integration/test_qdrant_service.py` | Real Qdrant service integration |
| `smoke/test_preflight.py` | Qdrant/Redis preflight checks |
| `eval/ground_truth.json` | Q&A pairs for RAG evaluation |


## Writing Tests

- **Default guide**: [`docs/engineering/test-writing-guide.md`](../docs/engineering/test-writing-guide.md)
- **Unit tests**: Mock external services; keep them fast and deterministic.
- **Integration tests**: Use real services; mark with `@pytest.mark.integration`.
- **Heavy tests**: Do not move live-service scenarios into the local fast lane.
- **Reuse**: Search existing coverage before adding new files (`rg -n "<behavior>" tests/`).
- **Fixtures**: Use `conftest.py` for shared setup; keep scopes narrow.

## Test Naming

```
test_<feature>.py                  # File
test_<behavior>_<expected>()       # Function
```

Example:
```python
def test_store_embedding_creates_hash():
    """Embedding storage creates unique hash key."""
    ...
```

## Notes

- The full heavy suite (chaos, load, E2E) is not required for every commit; run the fast gate (`make test` or `make test-unit`) locally.
- The old deprecated directory is no longer collected (`norecursedirs` in `pyproject.toml`).
- `docker-up` is an alias for `docker-core-up`; prefer `make local-up` for local development.

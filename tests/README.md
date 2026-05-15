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
├── baseline/            # Langfuse baseline metrics and threshold checks
├── benchmark/           # Performance comparisons (RRF vs DBSF, parser vs Docling, etc.)
├── observability/       # Trace/contract CLI and collector infrastructure tests
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

### Heavy / runtime checks (services or credentials required)
Run these selectively, not on every save.

| Tier | Location | What it proves | Typical duration |
|------|----------|----------------|------------------|
| Integration | `tests/integration/` | Real service interaction (Qdrant, Redis, APIs) | Minutes |
| Smoke | `tests/smoke/` | Live service health and routing sanity | Minutes |
| Eval | `tests/eval/` | RAG quality (faithfulness, relevance) | Minutes |
| Baseline | `tests/baseline/` | Observability metric regressions | Minutes |
| Benchmark | `tests/benchmark/` | Parser/reranker throughput comparisons | Varies |
| Observability | `tests/observability/` | Trace collector/manager infrastructure | Varies |
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
make e2e-test-traces-core    # required #1307 core Telethon trace gate
```

The `e2e-test-traces-core` target runs the required #1307 Telethon scenarios with Langfuse validation (`E2E_VALIDATE_LANGFUSE=1`). Ensure the bot is running locally (`make bot`) before executing this gate.

### RAG evaluation
```bash
make eval-rag                # RAGAS on ground_truth.json
make eval-rag-quick          # 10-sample subset
make eval-rag-full           # RAGAS + DeepEval
```

### Baseline / observability
```bash
make baseline-smoke          # smoke with Langfuse tracing
make baseline-compare        # compare against a baseline tag
```

### Compose validation (for runtime-impacting changes)
When changing `compose*.yml`, Dockerfiles, or service definitions, verify the effective config:

```bash
COMPOSE_FILE=compose.yml:compose.dev.yml docker compose --compatibility config --services
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
- `benchmark` — benchmark comparisons
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
| `unit/test_voyage_service.py` | VoyageService with mocked API |
| `unit/test_small_to_big.py` | Small-to-big chunk expansion |
| `unit/test_ragas_evaluation.py` | RAG evaluation metrics |
| `unit/test_local_compose_contract.py` | Compose config validation |
| `contract/test_trace_families_contract.py` | Required trace family coverage |
| `contract/test_span_coverage_contract.py` | Span coverage gates |
| `integration/test_graph_paths.py` | LangGraph path validation (no Docker) |
| `integration/test_qdrant_connection.py` | Real Qdrant connection |
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

- The full heavy suite (chaos, load, E2E, benchmark) is not required for every commit; run the fast gate (`make test` or `make test-unit`) locally.
- The old deprecated directory is no longer collected (`norecursedirs` in `pyproject.toml`).
- `docker-up` is an alias for `docker-core-up`; prefer `make local-up` for local development.

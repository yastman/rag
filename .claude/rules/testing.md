---
paths: "tests/**/*.py"
---

***REMOVED*** Testing Guide

Coverage: ~85% unit, 4990 tests passing. Full audit: `logs/full-pipeline-coverage-audit.txt`

**Markers:**

| Marker | Meaning |
|--------|---------|
| `legacy_api` | Pre-LangGraph API tests — excluded from CI |
| `requires_extras` | Needs optional extras (voice, ingest, eval) |
| `slow` | Heavy tests — nightly only |
| `chaos` | Service failure/resilience tests |
| `load` | Concurrency/load tests |
| `e2e` | End-to-end live service tests |
| `smoke` | Smoke/health check tests |
| `benchmark` | Performance comparison tests |
| `kommo` | Live Kommo API (requires token) |
| `xdist_group` | Prevent parallelization collisions |

***REMOVED******REMOVED*** Unit Tests

```bash
***REMOVED*** Parallel (recommended — xdist worksteal)
uv run pytest tests/unit/ -n auto --dist=worksteal -q --timeout=30 -m "not legacy_api"
make test-unit        ***REMOVED*** Same as above via Makefile
make test-unit-core   ***REMOVED*** Also skips requires_extras + slow

***REMOVED*** Single module / test
uv run pytest tests/unit/test_settings.py -v
uv run pytest tests/unit/test_file.py::test_method -v

***REMOVED*** With coverage
uv run pytest tests/unit/ --cov=src --cov=telegram_bot --cov-report=term-missing
make test-cov         ***REMOVED*** Full coverage with HTML report (htmlcov/index.html)
```

**pytest-timeout:** All tests have 30s default timeout (pyproject.toml). Override per-test with `@pytest.mark.timeout(60)`.

***REMOVED******REMOVED*** sys.modules Hygiene

**Policy:** NEVER assign to `sys.modules` at module level in test files.

| Pattern | Status |
|---------|--------|
| `sys.modules["foo"] = MagicMock()` at module level | **FORBIDDEN** |
| `monkeypatch.setitem(sys.modules, "foo", mock)` in fixture | **OK** |
| `pytest.MonkeyPatch.context()` in module-scoped fixture | **OK** |
| `sys.modules["foo"] = mock` in `pytest_configure` (conftest) | **OK** (with `pytest_unconfigure` cleanup) |

**Why:** Module-level patching leaks mocks into the session, breaks xdist isolation, and causes flaky tests from import-order dependencies.

**For collection-time mocks** (heavy ML libs): use `pytest_configure` / `pytest_unconfigure` hooks in `conftest.py`.

**Guard:** `test_module_pollution.py::test_no_module_level_sys_modules_assignment` scans all test files via AST and fails if bare module-level `sys.modules[...] = ...` is found.

***REMOVED******REMOVED*** Integration Tests

***REMOVED******REMOVED******REMOVED*** Graph Path Tests (no Docker required)

6 deterministic tests verifying all `route_grade` branches through `graph.ainvoke()` with mocked services:

```bash
uv run pytest tests/integration/test_graph_paths.py -v   ***REMOVED*** ~5s, fully mocked
```

| Test | Path |
|------|------|
| `test_path_chitchat_early_exit` | classify(CHITCHAT) → respond |
| `test_path_cache_hit` | cache_check(HIT) → respond |
| `test_path_happy_retrieve_rerank_generate` | retrieve → rerank → generate |
| `test_path_rewrite_loop_then_success` | grade(irrelevant) → rewrite → retrieve |
| `test_path_rewrite_exhausted_fallback` | rewrite_count >= 2 → generate |
| `test_path_rewrite_ineffective_fallback` | rewrite_effective=False → generate |

***REMOVED******REMOVED******REMOVED*** Service Integration Tests (require Docker)

Require Docker services: `make docker-up`

```bash
pytest tests/test_voyage*.py -v
pytest tests/test_e2e_pipeline.py -v
```

***REMOVED******REMOVED*** Smoke & Load Tests

```bash
make test-preflight        ***REMOVED*** Verify Qdrant/Redis config
make test-smoke            ***REMOVED*** 20 queries smoke suite
make test-load             ***REMOVED*** Parallel chat simulation
```

***REMOVED******REMOVED*** Chaos Tests

Tests for graceful degradation when services fail:

```bash
pytest tests/chaos/ -v                        ***REMOVED*** All chaos tests
pytest tests/chaos/test_qdrant_failures.py    ***REMOVED*** Qdrant timeout/disconnect
pytest tests/chaos/test_redis_failures.py     ***REMOVED*** Redis disconnect/pool exhaustion
pytest tests/chaos/test_llm_fallback.py       ***REMOVED*** LLM rate limits, parsing errors
```

***REMOVED******REMOVED*** Trace Validation Tests

```bash
uv run pytest tests/unit/test_validate_queries.py tests/unit/test_validate_aggregates.py -v
```

| File | Tests | Covers |
|------|-------|--------|
| `test_validate_queries.py` | 10 | Query sets, collection mapping, warmup/cache selection |
| `test_validate_aggregates.py` | 8 | p50/p95, phase split, score_rate, node latencies |

***REMOVED******REMOVED*** CI Pipeline (`.github/workflows/ci.yml`)

CI has **one job: `checks`** (self-hosted runner). Runs lint + format + type-check only.

| Step | Command |
|------|---------|
| Ruff lint | `ruff check src/ telegram_bot/ --output-format=github` |
| Ruff format | `ruff format --check src/ telegram_bot/` |
| Type check | `mypy src/ telegram_bot/ --ignore-missing-imports --no-error-summary` |
| Security scan | `bandit -r src/ telegram_bot/ -c pyproject.toml` + `vulture src/ telegram_bot/ --min-confidence 80` |

Install: `uv sync --frozen` (base deps).

**Tests run locally**, not in CI. Pre-push gate: `make check && make test-unit`.

***REMOVED******REMOVED*** pytest-split: Local Sharding

`pytest-split` (installed) + `.test_durations` enable balanced local shards:

```bash
***REMOVED*** Regenerate .test_durations after major test changes
make test-store-durations   ***REMOVED*** or:
uv run pytest tests/unit/ --store-durations -n auto --timeout=30 -m "not legacy_api" -q

***REMOVED*** Run shard 2 of 4 locally
uv run pytest tests/unit/ --splits 4 --group 2 -n auto --dist loadscope --timeout=30 -m "not legacy_api"
```

Commit updated `.test_durations` after regeneration.

***REMOVED******REMOVED*** Contract Tests

SLA/contract verification without Docker:

```bash
make test-contract   ***REMOVED*** Trace contract validation
uv run pytest tests/contract/ -v
```

| File | Covers |
|------|--------|
| `test_error_contract.py` | Error handling contracts |
| `test_span_coverage_contract.py` | Span coverage validation |
| `test_trace_families_contract.py` | Required trace families |

**Contract file:** `tests/observability/trace_contract.yaml` — defines required spans, sensitive spans, score keys.

***REMOVED******REMOVED*** Baseline Tests

Performance regression detection:

```bash
uv run pytest tests/baseline/ -v
```

`BaselineManager` compares sessions via `session_id` tag. Thresholds in `tests/baseline/thresholds.yaml`:
- LLM p95 latency: +20%
- Total cost: +10%
- Cache hit rate: -10%
- LLM calls: +15%

***REMOVED******REMOVED*** Notes

- `asyncio_mode = "auto"` — async tests don't need `@pytest.mark.asyncio`
- Integration tests require: `make docker-up`
- `--dist loadscope` groups tests by module to avoid fixture teardown/setup overhead

***REMOVED******REMOVED*** Test Dependencies

| Package | Purpose |
|---------|---------|
| `pytest>=8.3.0` | Test framework |
| `pytest-asyncio>=0.24.0` | Async test support |
| `pytest-cov>=5.0.0` | Coverage reporting |
| `pytest-httpx>=0.35.0` | HTTP request mocking |
| `pytest-xdist>=3.8.0` | Parallel test execution (`-n auto`) |
| `pytest-timeout>=2.4.0` | Per-test timeout (default 30s) |
| `pytest-split>=0.11.0` | CI shard splitting by test duration |

***REMOVED******REMOVED******REMOVED*** HTTP Mocking with pytest-httpx

```python
import pytest
from httpx import AsyncClient

@pytest.fixture
def httpx_mock():
    ***REMOVED*** Auto-provided by pytest-httpx
    pass

async def test_api_call(httpx_mock):
    httpx_mock.add_response(
        url="https://api.example.com/data",
        json={"result": "ok"}
    )
    ***REMOVED*** Your async HTTP client will use mocked response
```

---

***REMOVED*** E2E Testing (Telegram Bot)

End-to-end testing with real Telegram bot and Claude Judge evaluation.

***REMOVED******REMOVED*** Setup

```bash
***REMOVED*** 1. Get Telegram API credentials from https://my.telegram.org
***REMOVED*** 2. Add to .env:
***REMOVED***    TELEGRAM_API_ID=12345
***REMOVED***    TELEGRAM_API_HASH=abcdef...
***REMOVED***    ANTHROPIC_API_KEY=[REDACTED-ANTHROPIC-KEY]

***REMOVED*** 3. Install dependencies and generate test data
make e2e-setup
```

***REMOVED******REMOVED*** Running Tests

```bash
make e2e-test                                ***REMOVED*** All 25 tests
make e2e-test-group GROUP=price_filters      ***REMOVED*** Specific group
python scripts/e2e/runner.py --scenario 3.1  ***REMOVED*** Single test
python scripts/e2e/runner.py --skip-judge    ***REMOVED*** Skip Claude evaluation
make e2e-test-traces                         ***REMOVED*** E2E + Langfuse trace validation
E2E_VALIDATE_LANGFUSE=1 make e2e-test        ***REMOVED*** Alternative
```

***REMOVED******REMOVED*** Test Groups

| Group | Tests | Description |
|-------|-------|-------------|
| `commands` | 4 | /start, /help, /clear, /stats |
| `chitchat` | 4 | Greetings, thanks, goodbyes |
| `price_filters` | 4 | Price range queries |
| `room_filters` | 4 | Room count queries |
| `location_filters` | 3 | City and distance queries |
| `search` | 3 | Semantic and complex search |
| `edge_cases` | 3 | Empty results, long queries, special chars |

***REMOVED******REMOVED*** Reports

Reports saved to `reports/` directory:
- `e2e_YYYY-MM-DD_HH-MM-SS.json` — Machine-readable results
- `e2e_YYYY-MM-DD_HH-MM-SS.html` — Visual report with expandable details

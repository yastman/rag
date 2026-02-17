---
paths: "tests/**/*.py"
---

***REMOVED*** Testing Guide

Coverage: ~85% unit. Full audit: `logs/full-pipeline-coverage-audit.txt`

**Markers:** `legacy_api` — tests for pre-LangGraph API (excluded from CI).

***REMOVED******REMOVED*** Unit Tests

```bash
***REMOVED*** Sequential (21 min)
uv run pytest tests/unit/ -v
uv run pytest tests/unit/test_settings.py -v          ***REMOVED*** Single module
uv run pytest tests/unit/test_file.py::test_method -v ***REMOVED*** Single test

***REMOVED*** Parallel with xdist (5 min, 4.22x speedup, safe for CI)
uv run pytest tests/unit/ -n auto

***REMOVED*** With coverage
uv run pytest tests/unit/ --cov=telegram_bot/services --cov-report=term-missing
make test-cov                                          ***REMOVED*** Opens htmlcov/index.html
```

**pytest-timeout:** All tests have 30s default timeout (pyproject.toml). Override per-test with `@pytest.mark.timeout(60)`.

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

***REMOVED******REMOVED*** CI Pipeline: Sharded Unit Tests (pytest-split)

CI splits unit tests into **4 parallel shards** using `pytest-split` for ~4x faster feedback.

***REMOVED******REMOVED******REMOVED*** How it works

1. `.test_durations` (committed) contains per-test timing data
2. `pytest-split` uses durations to distribute tests evenly across shards
3. Each shard runs with `pytest-xdist` (`-n auto`) for intra-shard parallelism
4. On `main` branch, durations are re-measured and cached for future runs

***REMOVED******REMOVED******REMOVED*** CI matrix

```yaml
strategy:
  fail-fast: false
  matrix:
    group: [1, 2, 3, 4]
***REMOVED*** Each shard: --splits 4 --group ${{ matrix.group }} -n auto --dist loadscope
```

***REMOVED******REMOVED******REMOVED*** Updating `.test_durations`

Regenerate after adding/removing tests or significant refactors:

```bash
uv run pytest tests/unit/ --store-durations --timeout=30 -m "not legacy_api" -q
```

This overwrites `.test_durations` with fresh timing data. Commit the updated file.

On `main` branch, CI automatically re-measures and caches durations.

***REMOVED******REMOVED******REMOVED*** Running sharded tests locally

```bash
***REMOVED*** Run a specific shard (e.g., shard 2 of 4)
uv run pytest tests/unit/ --splits 4 --group 2 -n auto --dist loadscope --timeout=30 -m "not legacy_api"

***REMOVED*** Run all 4 shards sequentially (for debugging split balance)
for g in 1 2 3 4; do
  echo "=== Shard $g ==="
  uv run pytest tests/unit/ --splits 4 --group $g -n auto --dist loadscope --timeout=30 -m "not legacy_api" -q
done
```

***REMOVED******REMOVED******REMOVED*** Integration tests in CI

Graph path tests run as a separate CI job (no Docker, ~5s):

```bash
uv run pytest tests/integration/test_graph_paths.py -v --timeout=30
```

***REMOVED******REMOVED*** Notes

- `asyncio_mode = "auto"` — async tests don't need `@pytest.mark.asyncio`
- Integration tests require: `make docker-up`
- CI runs unit tests sharded across 4 matrix jobs (see `.github/workflows/ci.yml`)
- `--dist loadscope` groups tests by module to avoid fixture teardown/setup overhead

***REMOVED******REMOVED*** Test Dependencies

| Package | Purpose |
|---------|---------|
| `pytest>=8.3.0` | Test framework |
| `pytest-asyncio>=0.24.0` | Async test support |
| `pytest-cov>=5.0.0` | Coverage reporting |
| `pytest-httpx>=0.35.0` | HTTP request mocking |
| `pytest-xdist>=3.8.0` | Parallel test execution (`-n auto`) |
| `pytest-timeout>=2.3.0` | Per-test timeout (default 30s) |
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

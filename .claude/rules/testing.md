---
paths: "tests/**/*.py"
---

# Testing Guide

Coverage: ~85% unit. Full audit: `logs/full-pipeline-coverage-audit.txt`

**Markers:**

| Marker | Meaning |
|--------|---------|
| `legacy_api` | Pre-LangGraph API tests — excluded from CI |
| `requires_extras` | Needs optional extras (voice, ingest, eval) |
| `slow` | Heavy tests — nightly only |

## Unit Tests

```bash
# Parallel (recommended — xdist worksteal)
uv run pytest tests/unit/ -n auto --dist=worksteal -q --timeout=30 -m "not legacy_api"
make test-unit        # Same as above via Makefile
make test-unit-core   # Also skips requires_extras + slow

# Single module / test
uv run pytest tests/unit/test_settings.py -v
uv run pytest tests/unit/test_file.py::test_method -v

# With coverage
uv run pytest tests/unit/ --cov=src --cov=telegram_bot --cov-report=term-missing
make test-cov         # Full coverage with HTML report (htmlcov/index.html)
```

**pytest-timeout:** All tests have 30s default timeout (pyproject.toml). Override per-test with `@pytest.mark.timeout(60)`.

## sys.modules Hygiene

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

## Integration Tests

### Graph Path Tests (no Docker required)

6 deterministic tests verifying all `route_grade` branches through `graph.ainvoke()` with mocked services:

```bash
uv run pytest tests/integration/test_graph_paths.py -v   # ~5s, fully mocked
```

| Test | Path |
|------|------|
| `test_path_chitchat_early_exit` | classify(CHITCHAT) → respond |
| `test_path_cache_hit` | cache_check(HIT) → respond |
| `test_path_happy_retrieve_rerank_generate` | retrieve → rerank → generate |
| `test_path_rewrite_loop_then_success` | grade(irrelevant) → rewrite → retrieve |
| `test_path_rewrite_exhausted_fallback` | rewrite_count >= 2 → generate |
| `test_path_rewrite_ineffective_fallback` | rewrite_effective=False → generate |

### Service Integration Tests (require Docker)

Require Docker services: `make docker-up`

```bash
pytest tests/test_voyage*.py -v
pytest tests/test_e2e_pipeline.py -v
```

## Smoke & Load Tests

```bash
make test-preflight        # Verify Qdrant/Redis config
make test-smoke            # 20 queries smoke suite
make test-load             # Parallel chat simulation
```

## Chaos Tests

Tests for graceful degradation when services fail:

```bash
pytest tests/chaos/ -v                        # All chaos tests
pytest tests/chaos/test_qdrant_failures.py    # Qdrant timeout/disconnect
pytest tests/chaos/test_redis_failures.py     # Redis disconnect/pool exhaustion
pytest tests/chaos/test_llm_fallback.py       # LLM rate limits, parsing errors
```

## Trace Validation Tests

```bash
uv run pytest tests/unit/test_validate_queries.py tests/unit/test_validate_aggregates.py -v
```

| File | Tests | Covers |
|------|-------|--------|
| `test_validate_queries.py` | 10 | Query sets, collection mapping, warmup/cache selection |
| `test_validate_aggregates.py` | 8 | p50/p95, phase split, score_rate, node latencies |

## CI Pipeline (`.github/workflows/ci.yml`)

CI has **one job: `checks`** (self-hosted runner). Runs lint + format + type-check only.

| Step | Command |
|------|---------|
| Ruff lint | `ruff check src/ telegram_bot/ tests/` |
| Ruff format | `ruff format --check src/ telegram_bot/ tests/` |
| Type check | `mypy src/ telegram_bot/ --ignore-missing-imports` |

Install: `uv sync --frozen` (base deps).

**Tests run locally**, not in CI. Pre-push gate: `make check && make test-unit`.

## pytest-split: Local Sharding

`pytest-split` (installed) + `.test_durations` enable balanced local shards:

```bash
# Regenerate .test_durations after major test changes
make test-store-durations   # or:
uv run pytest tests/unit/ --store-durations -n auto --timeout=30 -m "not legacy_api" -q

# Run shard 2 of 4 locally
uv run pytest tests/unit/ --splits 4 --group 2 -n auto --dist loadscope --timeout=30 -m "not legacy_api"
```

Commit updated `.test_durations` after regeneration.

## Notes

- `asyncio_mode = "auto"` — async tests don't need `@pytest.mark.asyncio`
- Integration tests require: `make docker-up`
- CI runs unit tests sharded across 4 matrix jobs (see `.github/workflows/ci.yml`)
- `--dist loadscope` groups tests by module to avoid fixture teardown/setup overhead

## Test Dependencies

| Package | Purpose |
|---------|---------|
| `pytest>=8.3.0` | Test framework |
| `pytest-asyncio>=0.24.0` | Async test support |
| `pytest-cov>=5.0.0` | Coverage reporting |
| `pytest-httpx>=0.35.0` | HTTP request mocking |
| `pytest-xdist>=3.8.0` | Parallel test execution (`-n auto`) |
| `pytest-timeout>=2.4.0` | Per-test timeout (default 30s) |
| `pytest-split>=0.11.0` | CI shard splitting by test duration |

### HTTP Mocking with pytest-httpx

```python
import pytest
from httpx import AsyncClient

@pytest.fixture
def httpx_mock():
    # Auto-provided by pytest-httpx
    pass

async def test_api_call(httpx_mock):
    httpx_mock.add_response(
        url="https://api.example.com/data",
        json={"result": "ok"}
    )
    # Your async HTTP client will use mocked response
```

---

# E2E Testing (Telegram Bot)

End-to-end testing with real Telegram bot and Claude Judge evaluation.

## Setup

```bash
# 1. Get Telegram API credentials from https://my.telegram.org
# 2. Add to .env:
#    TELEGRAM_API_ID=12345
#    TELEGRAM_API_HASH=abcdef...
#    ANTHROPIC_API_KEY=sk-ant-...

# 3. Install dependencies and generate test data
make e2e-setup
```

## Running Tests

```bash
make e2e-test                                # All 25 tests
make e2e-test-group GROUP=price_filters      # Specific group
python scripts/e2e/runner.py --scenario 3.1  # Single test
python scripts/e2e/runner.py --skip-judge    # Skip Claude evaluation
make e2e-test-traces                         # E2E + Langfuse trace validation
E2E_VALIDATE_LANGFUSE=1 make e2e-test        # Alternative
```

## Test Groups

| Group | Tests | Description |
|-------|-------|-------------|
| `commands` | 4 | /start, /help, /clear, /stats |
| `chitchat` | 4 | Greetings, thanks, goodbyes |
| `price_filters` | 4 | Price range queries |
| `room_filters` | 4 | Room count queries |
| `location_filters` | 3 | City and distance queries |
| `search` | 3 | Semantic and complex search |
| `edge_cases` | 3 | Empty results, long queries, special chars |

## Reports

Reports saved to `reports/` directory:
- `e2e_YYYY-MM-DD_HH-MM-SS.json` — Machine-readable results
- `e2e_YYYY-MM-DD_HH-MM-SS.html` — Visual report with expandable details

---
paths: "tests/**/*.py"
---

# Testing Guide

Coverage: 91% (~1670 unit tests)

## Unit Tests

```bash
# Fast, no Docker needed
pytest tests/unit/ -v
pytest tests/unit/test_settings.py -v          # Single module
pytest tests/unit/test_file.py::test_method -v # Single test

# With coverage
pytest tests/unit/ --cov=telegram_bot/services --cov-report=term-missing
make test-cov                                   # Opens htmlcov/index.html
```

## Integration Tests

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
pytest tests/chaos/test_qdrant_failures.py    ***REMOVED*** timeout/disconnect
pytest tests/chaos/test_redis_failures.py     # Redis disconnect/pool exhaustion
pytest tests/chaos/test_llm_fallback.py       # LLM rate limits, parsing errors
```

## Notes

- `asyncio_mode = "auto"` — async tests don't need `@pytest.mark.asyncio`
- Integration tests require: `make docker-up`

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

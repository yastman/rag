---
paths: "tests/**/*.py"
---

***REMOVED*** Testing Guide

Coverage: 91% (~1670 unit tests)

***REMOVED******REMOVED*** Unit Tests

```bash
***REMOVED*** Fast, no Docker needed
pytest tests/unit/ -v
pytest tests/unit/test_settings.py -v          ***REMOVED*** Single module
pytest tests/unit/test_file.py::test_method -v ***REMOVED*** Single test

***REMOVED*** With coverage
pytest tests/unit/ --cov=telegram_bot/services --cov-report=term-missing
make test-cov                                   ***REMOVED*** Opens htmlcov/index.html
```

***REMOVED******REMOVED*** Integration Tests

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

***REMOVED******REMOVED*** Notes

- `asyncio_mode = "auto"` — async tests don't need `@pytest.mark.asyncio`
- Integration tests require: `make docker-up`

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

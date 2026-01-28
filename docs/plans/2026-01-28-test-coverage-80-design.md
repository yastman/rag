# Design: Test Coverage 80%

**Goal:** Increase test coverage from 53% to 80%
**Strategy:** Parallel workers via spawn-claude, each covering independent modules

## Current State

- **Coverage:** 53.36% (4451 statements, 2074 uncovered)
- **Target:** 80%
- **Gap:** ~1200 statements to cover

## Modules to Cover (by priority)

### Batch 1: High Impact (0% coverage, 500+ stmts total)

| Module | Stmts | Worker |
|--------|-------|--------|
| `src/evaluation/run_ab_test.py` | 246 | W1 |
| `src/evaluation/search_engines.py` | 150 | W1 |
| `src/evaluation/evaluate_with_ragas.py` | 116 | W1 |

### Batch 2: Core + Ingestion (0% coverage)

| Module | Stmts | Worker |
|--------|-------|--------|
| `src/core/pipeline.py` | 85 | W2 |
| `src/ingestion/voyage_indexer.py` | 124 | W2 |
| `src/retrieval/reranker.py` | 37 | W2 |

### Batch 3: MLflow/Langfuse (0% coverage)

| Module | Stmts | Worker |
|--------|-------|--------|
| `src/evaluation/mlflow_integration.py` | 91 | W3 |
| `src/evaluation/mlflow_experiments.py` | 81 | W3 |
| `src/evaluation/langfuse_integration.py` | 56 | W3 |
| `src/evaluation/smoke_test.py` | 88 | W3 |

### Batch 4: Telegram Bot gaps (partial coverage)

| Module | Current | Target | Worker |
|--------|---------|--------|--------|
| `telegram_bot/services/cache.py` | 65% | 85% | W4 |
| `telegram_bot/services/qdrant.py` | 55% | 85% | W4 |
| `telegram_bot/services/cesc.py` | 25% | 80% | W4 |
| `telegram_bot/bot.py` | 41% | 70% | W4 |

### Batch 5: Remaining (0% or low coverage)

| Module | Stmts | Worker |
|--------|-------|--------|
| `src/evaluation/generate_test_queries.py` | 95 | W5 |
| `src/evaluation/ragas_evaluation.py` | 58 | W5 |
| `src/evaluation/create_golden_set.py` | 28 | W5 |
| `telegram_bot/logging_config.py` | 53 | W5 |
| `telegram_bot/main.py` | 24 | W5 |

## Test File Structure

```
tests/unit/
├── evaluation/
│   ├── test_run_ab_test.py          # W1
│   ├── test_search_engines_eval.py  # W1
│   ├── test_evaluate_with_ragas.py  # W1
│   ├── test_mlflow_integration.py   # W3
│   ├── test_mlflow_experiments.py   # W3
│   ├── test_langfuse_integration.py # W3
│   ├── test_smoke_test.py           # W3
│   ├── test_generate_test_queries.py # W5
│   ├── test_ragas_evaluation.py     # W5
│   └── test_create_golden_set.py    # W5
├── core/
│   └── test_pipeline.py             # W2
├── ingestion/
│   └── test_voyage_indexer.py       # W2
├── retrieval/
│   └── test_reranker.py             # W2
└── telegram_bot/
    ├── test_cache_extended.py       # W4
    ├── test_qdrant_extended.py      # W4
    ├── test_cesc_extended.py        # W4
    ├── test_bot_extended.py         # W4
    ├── test_logging_config.py       # W5
    └── test_main.py                 # W5
```

## Worker Commands

```bash
PROJECT="/mnt/c/Users/user/Documents/Сайты/rag-fresh"

# Worker 1: Evaluation (A/B, search engines, RAGAS)
spawn-claude "W1: Test coverage for src/evaluation - run_ab_test.py, search_engines.py, evaluate_with_ragas.py.
Create tests in tests/unit/evaluation/. Use mocks for MLflow, Qdrant, external APIs.
Target: cover all functions, edge cases.
VERIFY: pytest tests/unit/evaluation/test_run_ab_test.py tests/unit/evaluation/test_search_engines_eval.py tests/unit/evaluation/test_evaluate_with_ragas.py -v
git commit after each file." "$PROJECT"

# Worker 2: Core + Ingestion
spawn-claude "W2: Test coverage for src/core/pipeline.py, src/ingestion/voyage_indexer.py, src/retrieval/reranker.py.
Create tests in tests/unit/core/, tests/unit/ingestion/, tests/unit/retrieval/.
Mock Qdrant, VoyageService, external calls.
VERIFY: pytest tests/unit/core/ tests/unit/ingestion/test_voyage_indexer.py tests/unit/retrieval/test_reranker.py -v
git commit after each file." "$PROJECT"

# Worker 3: MLflow/Langfuse
spawn-claude "W3: Test coverage for MLflow and Langfuse integration.
Files: mlflow_integration.py, mlflow_experiments.py, langfuse_integration.py, smoke_test.py.
Create tests in tests/unit/evaluation/. Mock all external services.
VERIFY: pytest tests/unit/evaluation/test_mlflow*.py tests/unit/evaluation/test_langfuse*.py tests/unit/evaluation/test_smoke_test.py -v
git commit after each file." "$PROJECT"

# Worker 4: Telegram Bot services
spawn-claude "W4: Extend test coverage for telegram_bot/services/.
Files: cache.py (65%→85%), qdrant.py (55%→85%), cesc.py (25%→80%), bot.py (41%→70%).
Add tests to existing files or create *_extended.py.
Mock Redis, Qdrant, LLM calls.
VERIFY: pytest tests/unit/telegram_bot/ -v --cov=telegram_bot/services --cov-report=term-missing
git commit after each file." "$PROJECT"

# Worker 5: Remaining modules
spawn-claude "W5: Test coverage for remaining modules.
Files: generate_test_queries.py, ragas_evaluation.py, create_golden_set.py, logging_config.py, main.py.
Create appropriate test files. Mock all external dependencies.
VERIFY: pytest tests/unit/ -v --cov=src --cov=telegram_bot -q | tail -50
git commit after each file." "$PROJECT"
```

## Testing Patterns

### Mocking External Services

```python
from unittest.mock import AsyncMock, MagicMock, patch

***REMOVED***
@patch('module.QdrantClient')
def test_something(mock_qdrant):
    mock_qdrant.return_value.query_points.return_value = MagicMock(points=[])

# Async services
@patch('module.VoyageService')
async def test_async(mock_voyage):
    mock_voyage.return_value.embed_query = AsyncMock(return_value=[0.1] * 1024)

# MLflow
@patch('mlflow.start_run')
@patch('mlflow.log_metric')
def test_mlflow(mock_log, mock_run):
    mock_run.return_value.__enter__ = MagicMock()
```

### Fixtures (conftest.py)

```python
@pytest.fixture
def mock_qdrant_client():
    with patch('qdrant_client.QdrantClient') as mock:
        mock.return_value.query_points.return_value = MagicMock(points=[])
        yield mock

@pytest.fixture
def mock_voyage_service():
    with patch('telegram_bot.services.VoyageService') as mock:
        mock.return_value.embed_query = AsyncMock(return_value=[0.1] * 1024)
        mock.return_value.rerank = AsyncMock(return_value=[])
        yield mock
```

## Verification

After all workers complete:

```bash
# Full coverage check
pytest tests/unit/ --cov=src --cov=telegram_bot --cov-report=term-missing -q

# Should show >= 80%
```

## Timeline

- **Batch 1-3:** Can run in parallel (no file conflicts)
- **Batch 4:** Depends on existing test structure, may need coordination
- **Batch 5:** Final cleanup after main batches

## Notes

- Each worker commits after completing each test file
- Workers don't touch each other's files
- Main orchestrator merges and verifies final coverage

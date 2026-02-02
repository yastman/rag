# Tests

## Directory Structure

```
tests/
├── conftest.py          # Shared fixtures
├── unit/                # Fast tests, no external deps (mocked)
├── integration/         # Require running services (Qdrant, Redis, etc.)
├── e2e/                 # End-to-end pipeline tests
├── smoke/               # Quick health checks
├── benchmark/           # Performance comparisons (RRF vs DBSF, etc.)
├── baseline/            # Langfuse baseline metrics
├── eval/                # RAG evaluation (RAGAS, ground_truth.json)
├── load/                # Load testing
├── legacy/              # Deprecated tests
└── data/                # Test fixtures and datasets
```

## Commands

```bash
# Run all tests
make test

# Unit tests only (fast, no deps)
make test-unit
# or
pytest tests/unit/ -v

# Integration tests (requires services)
pytest tests/integration/ -v

# Specific test file
pytest tests/unit/test_cache_service.py -v

# Run failed tests only
pytest --lf

# With coverage
make test-cov
```

## Test Categories

| Category | Location | Requires | Speed |
|----------|----------|----------|-------|
| Unit | `tests/unit/` | Nothing (mocked) | Fast |
| Integration | `tests/integration/` | Docker services | Medium |
| E2E | `tests/e2e/` | Full stack | Slow |
| Smoke | `tests/smoke/` | Services | Fast |
| Benchmark | `tests/benchmark/` | Services | Varies |
| Eval | `tests/eval/` | LLM + Qdrant | Slow |
| Baseline | `tests/baseline/` | Langfuse | Medium |

## Running Services

```bash
make docker-up    # Start Qdrant, Redis, LiteLLM, etc.
make docker-down  # Stop services
```

## Key Test Files

| File | Description |
|------|-------------|
| `unit/test_cache_service.py` | CacheService with mocked Redis |
| `unit/test_qdrant_service.py` | QdrantService with mocked client |
| `unit/test_voyage_service.py` | VoyageService with mocked API |
| `unit/test_small_to_big.py` | Small-to-big chunk expansion |
| `unit/test_ragas_evaluation.py` | RAG evaluation metrics |
| `integration/test_qdrant_connection.py` | Real Qdrant connection |
| `eval/ground_truth.json` | 55 Q&A pairs for evaluation |

## Writing Tests

- **Unit tests**: Mock external services with `pytest-mock`
- **Integration tests**: Use real services, mark with `@pytest.mark.integration`
- Use fixtures from `conftest.py` for common setup
- Follow AAA pattern: Arrange, Act, Assert

## Test Naming

```
test_<module>_<behavior>.py       # File
test_<method>_<scenario>()        # Function
```

Example:
```python
# tests/unit/test_cache_service.py
def test_store_embedding_creates_hash():
    """Embedding storage creates unique hash key."""
    ...
```

---

**Last Updated**: 2026-02-02

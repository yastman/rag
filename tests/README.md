***REMOVED*** Tests

***REMOVED******REMOVED*** Directory Structure

```
tests/
├── conftest.py          ***REMOVED*** Shared fixtures
├── unit/                ***REMOVED*** Fast tests, no external deps (mocked)
├── integration/         ***REMOVED*** Require running services (Qdrant, Redis, etc.)
├── e2e/                 ***REMOVED*** End-to-end pipeline tests
├── smoke/               ***REMOVED*** Quick health checks
├── benchmark/           ***REMOVED*** Performance comparisons (RRF vs DBSF, etc.)
├── baseline/            ***REMOVED*** Langfuse baseline metrics
├── eval/                ***REMOVED*** RAG evaluation (RAGAS, ground_truth.json)
├── load/                ***REMOVED*** Load testing
├── legacy/              ***REMOVED*** Deprecated tests
└── data/                ***REMOVED*** Test fixtures and datasets
```

***REMOVED******REMOVED*** Commands

```bash
***REMOVED*** Run all tests
make test

***REMOVED*** Unit tests only (fast, no deps)
make test-unit
***REMOVED*** or
pytest tests/unit/ -v

***REMOVED*** Integration tests (requires services)
pytest tests/integration/ -v

***REMOVED*** Specific test file
pytest tests/unit/test_cache_service.py -v

***REMOVED*** Run failed tests only
pytest --lf

***REMOVED*** With coverage
make test-cov
```

***REMOVED******REMOVED*** Test Categories

| Category | Location | Requires | Speed |
|----------|----------|----------|-------|
| Unit | `tests/unit/` | Nothing (mocked) | Fast |
| Integration | `tests/integration/` | Docker services | Medium |
| E2E | `tests/e2e/` | Full stack | Slow |
| Smoke | `tests/smoke/` | Services | Fast |
| Benchmark | `tests/benchmark/` | Services | Varies |
| Eval | `tests/eval/` | LLM + Qdrant | Slow |
| Baseline | `tests/baseline/` | Langfuse | Medium |

***REMOVED******REMOVED*** Running Services

```bash
make docker-up    ***REMOVED*** Start Qdrant, Redis, LiteLLM, etc.
make docker-down  ***REMOVED*** Stop services
```

***REMOVED******REMOVED*** Key Test Files

| File | Description |
|------|-------------|
| `unit/test_cache_service.py` | CacheService with mocked Redis |
| `unit/test_qdrant_service.py` | QdrantService with mocked client |
| `unit/test_voyage_service.py` | VoyageService with mocked API |
| `unit/test_small_to_big.py` | Small-to-big chunk expansion |
| `unit/test_ragas_evaluation.py` | RAG evaluation metrics |
| `integration/test_qdrant_connection.py` | Real Qdrant connection |
| `eval/ground_truth.json` | 55 Q&A pairs for evaluation |

***REMOVED******REMOVED*** Writing Tests

- **Unit tests**: Mock external services with `pytest-mock`
- **Integration tests**: Use real services, mark with `@pytest.mark.integration`
- Use fixtures from `conftest.py` for common setup
- Follow AAA pattern: Arrange, Act, Assert

***REMOVED******REMOVED*** Test Naming

```
test_<module>_<behavior>.py       ***REMOVED*** File
test_<method>_<scenario>()        ***REMOVED*** Function
```

Example:
```python
***REMOVED*** tests/unit/test_cache_service.py
def test_store_embedding_creates_hash():
    """Embedding storage creates unique hash key."""
    ...
```

---

**Last Updated**: 2026-02-02

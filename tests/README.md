***REMOVED*** 🧪 Tests

Automated tests for Contextual RAG Pipeline.

---

***REMOVED******REMOVED*** 📁 Test Structure

```
tests/
├── README.md                          ***REMOVED*** This file
├── data/                              ***REMOVED*** Test data
│   └── golden_test_set.json           ***REMOVED*** 93 queries for evaluation
├── legacy/                            ***REMOVED*** Deprecated tests
│
├── test_basic_connection.py           ***REMOVED*** Basic connectivity tests
├── test_qdrant_connection.py          ***REMOVED*** Qdrant connection tests
├── test_qdrant_read.py                ***REMOVED*** Qdrant read operations
│
├── test_chunking_smoke.py             ***REMOVED*** Chunking smoke tests
├── test_chunking_quality.py           ***REMOVED*** Chunking quality tests
│
├── test_docling_metadata_deep.py      ***REMOVED*** Docling metadata extraction
├── test_docling_vs_pymupdf.py         ***REMOVED*** Docling vs PyMuPDF comparison
│
├── test_redis_url.py                  ***REMOVED*** Redis URL generation (no connection)
└── test_redis_cache.py                ***REMOVED*** Redis cache integration tests
```

---

***REMOVED******REMOVED*** 🚀 Running Tests

***REMOVED******REMOVED******REMOVED*** All Tests
```bash
cd /srv/rag-fresh
source venv/bin/activate
pytest tests/
```

***REMOVED******REMOVED******REMOVED*** Specific Test File
```bash
pytest tests/test_redis_url.py -v
```

***REMOVED******REMOVED******REMOVED*** With Coverage
```bash
pytest tests/ --cov=src --cov-report=html
```

***REMOVED******REMOVED******REMOVED*** Smoke Tests (Fast)
```bash
pytest tests/test_chunking_smoke.py tests/test_basic_connection.py
```

---

***REMOVED******REMOVED*** 📊 Test Categories

***REMOVED******REMOVED******REMOVED*** 1. Connectivity Tests
**Purpose**: Verify infrastructure connections

| Test | File | Requires |
|------|------|----------|
| Basic connectivity | `test_basic_connection.py` | Qdrant, Redis |
| Qdrant connection | `test_qdrant_connection.py` | Qdrant running |
| Qdrant read ops | `test_qdrant_read.py` | Qdrant + data |
| Redis URL generation | `test_redis_url.py` | None (pure logic) |
| Redis cache | `test_redis_cache.py` | Redis running |

**Run connectivity tests**:
```bash
pytest tests/test_*_connection.py tests/test_redis_*.py
```

---

***REMOVED******REMOVED******REMOVED*** 2. Ingestion Tests
**Purpose**: Document parsing and chunking

| Test | File | Tests |
|------|------|-------|
| Chunking smoke | `test_chunking_smoke.py` | Basic chunking works |
| Chunking quality | `test_chunking_quality.py` | Chunking strategies comparison |
| Docling deep | `test_docling_metadata_deep.py` | Metadata extraction |
| Docling vs PyMuPDF | `test_docling_vs_pymupdf.py` | Parser comparison |

**Run ingestion tests**:
```bash
pytest tests/test_chunking_*.py tests/test_docling_*.py
```

---

***REMOVED******REMOVED******REMOVED*** 3. Evaluation Tests
**Purpose**: Quality metrics and golden test set

| Location | Purpose |
|----------|---------|
| `data/golden_test_set.json` | 93 test queries with ground truth |
| `src/evaluation/create_golden_set.py` | Generator script |

**Evaluate on golden set**:
```bash
source venv/bin/activate
python src/evaluation/ragas_evaluation.py
```

---

***REMOVED******REMOVED*** 🧩 Test Dependencies

***REMOVED******REMOVED******REMOVED*** Required Infrastructure
```bash
***REMOVED*** Check services are running
docker ps | grep -E "qdrant|redis"

***REMOVED*** Expected output:
***REMOVED*** ai-qdrant-secure    ***REMOVED*** Port 6333
***REMOVED*** ai-redis-secure     ***REMOVED*** Port 6379
```

***REMOVED******REMOVED******REMOVED*** Python Dependencies
```bash
pip install pytest pytest-asyncio pytest-cov
```

---

***REMOVED******REMOVED*** 📝 Test Conventions

***REMOVED******REMOVED******REMOVED*** File Naming
- `test_*.py` - test files
- `test_*_smoke.py` - fast smoke tests
- `test_*_integration.py` - integration tests
- `test_*_unit.py` - unit tests

***REMOVED******REMOVED******REMOVED*** Function Naming
```python
def test_redis_url_generation():  ***REMOVED*** Good: descriptive
    ...

def test_cache():  ***REMOVED*** Bad: too vague
    ...
```

***REMOVED******REMOVED******REMOVED*** Test Structure
```python
def test_something():
    """Test description."""
    ***REMOVED*** Arrange (setup)
    cache = RedisSemanticCache(index_version="1.0.0")

    ***REMOVED*** Act (execute)
    result = cache.get_embedding("test query")

    ***REMOVED*** Assert (verify)
    assert result is None  ***REMOVED*** First time should be cache miss
```

---

***REMOVED******REMOVED*** 🔍 Test Types

***REMOVED******REMOVED******REMOVED*** Unit Tests
**Test isolated components without external dependencies**

Example: `test_redis_url.py`
```python
def test_redis_url_generation():
    """Test URL generation logic without actual connection."""
    ***REMOVED*** No Redis connection needed - pure logic test
    ...
```

***REMOVED******REMOVED******REMOVED*** Integration Tests
**Test components with real external services**

Example: `test_redis_cache.py`
```python
async def test_redis_connection():
    """Test actual Redis connection and operations."""
    cache = RedisSemanticCache()
    await cache.redis.ping()  ***REMOVED*** Requires Redis running
```

***REMOVED******REMOVED******REMOVED*** Smoke Tests
**Quick tests to verify basic functionality**

Example: `test_chunking_smoke.py`
```python
def test_chunker_creates_chunks():
    """Verify chunker produces output."""
    chunker = DocumentChunker()
    chunks = chunker.chunk_text("test", "doc", "art1")
    assert len(chunks) > 0
```

---

***REMOVED******REMOVED*** 🎯 Test Coverage Goals

| Component | Current | Target | Priority |
|-----------|---------|--------|----------|
| `src/cache/` | ~60% | 80% | 🔴 High |
| `src/ingestion/` | ~70% | 85% | 🟡 Medium |
| `src/retrieval/` | ~50% | 80% | 🔴 High |
| `src/security/` | ~40% | 90% | 🔴 High |
| `src/evaluation/` | ~80% | 90% | 🟢 Low |
| `src/config/` | ~90% | 95% | 🟢 Low |

**Check current coverage**:
```bash
pytest tests/ --cov=src --cov-report=term-missing
```

---

***REMOVED******REMOVED*** 🚨 Troubleshooting

***REMOVED******REMOVED******REMOVED*** Issue: Redis connection errors
**Solution**: Check Redis is running
```bash
docker ps | grep redis
docker logs ai-redis-secure
```

***REMOVED******REMOVED******REMOVED*** Issue: Qdrant connection errors
**Solution**: Check Qdrant is running
```bash
docker ps | grep qdrant
curl http://localhost:6333/health
```

***REMOVED******REMOVED******REMOVED*** Issue: Tests fail with "ModuleNotFoundError"
**Solution**: Activate venv
```bash
source /srv/app/venv/bin/activate
pip install -e .
```

***REMOVED******REMOVED******REMOVED*** Issue: Slow tests
**Solution**: Run only fast tests
```bash
pytest tests/ -m "not slow"  ***REMOVED*** Requires @pytest.mark.slow decorator
```

---

***REMOVED******REMOVED*** 📚 Adding New Tests

***REMOVED******REMOVED******REMOVED*** 1. Create Test File
```bash
touch tests/test_new_feature.py
```

***REMOVED******REMOVED******REMOVED*** 2. Write Tests
```python
***REMOVED***!/usr/bin/env python3
"""Tests for new feature."""

import pytest
from src.my_module import MyClass

def test_new_feature():
    """Test new feature works."""
    obj = MyClass()
    result = obj.do_something()
    assert result == expected_value
```

***REMOVED******REMOVED******REMOVED*** 3. Run Tests
```bash
pytest tests/test_new_feature.py -v
```

***REMOVED******REMOVED******REMOVED*** 4. Add to CI/CD
Update `.github/workflows/test.yml` (if exists)

---

***REMOVED******REMOVED*** 🎓 Testing Best Practices

***REMOVED******REMOVED******REMOVED*** ✅ DO
- Write descriptive test names
- Test one thing per test function
- Use fixtures for common setup
- Mock external dependencies when possible
- Add docstrings to test functions
- Keep tests fast (unit tests < 100ms)

***REMOVED******REMOVED******REMOVED*** ❌ DON'T
- Write tests that depend on each other
- Use hardcoded paths (use `Path(__file__)`)
- Test implementation details
- Leave commented-out tests
- Ignore test failures
- Skip writing tests for critical code

---

***REMOVED******REMOVED*** 📊 Test Metrics

***REMOVED******REMOVED******REMOVED*** Current State (2025-10-30)
- **Total tests**: 9 files
- **Golden test set**: 93 queries
- **Categories**: Connectivity, Ingestion, Evaluation
- **Infrastructure**: Qdrant + Redis integration tests

***REMOVED******REMOVED******REMOVED*** Goals
- [ ] Add 50+ unit tests for core modules
- [ ] Increase coverage to 80%+ overall
- [ ] Add performance benchmarks
- [ ] Add regression tests with golden set
- [ ] Add load tests (100+ concurrent queries)

---

***REMOVED******REMOVED*** 🔗 Related Documentation

- `/srv/app/README.md` - Main project guide
- `src/evaluation/README.md` - Evaluation framework
- `src/cache/README.md` - Caching architecture
- `IMPLEMENTATION_PLAN.md` - Future test requirements

---

**Last Updated**: 2025-10-30
**Maintainer**: Contextual RAG Team

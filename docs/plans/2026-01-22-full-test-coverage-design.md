# Full Test Coverage Design

**Date:** 2026-01-22
**Goal:** Achieve 80% test coverage for entire project using TDD approach
**Approach:** Sequential by criticality, hybrid mocking strategy

## Summary

- **Target coverage:** 80% for `src/` and `telegram_bot/`
- **Approach:** Sequential (one module at a time, fully covered before next)
- **Mocking:** Unit tests with mocks + integration tests with real services
- **Markers:** `@pytest.mark.unit`, `@pytest.mark.integration`, `@pytest.mark.slow`

## Prioritized Module List

### Tier 1: Critical (core bot functionality)

| # | Module | Lines | Criticality |
|---|--------|-------|-------------|
| 1 | `telegram_bot/services/llm.py` | ~100 | Response generation, streaming |
| 2 | `telegram_bot/services/embeddings.py` | ~200 | Query vectorization |
| 3 | `telegram_bot/services/filter_extractor.py` | ~150 | Filter parsing from queries |
| 4 | `telegram_bot/services/query_analyzer.py` | ~120 | Query intent analysis |

### Tier 2: Important (configuration and LLM contextualization)

| # | Module | Lines | Reason |
|---|--------|-------|--------|
| 5 | `src/config/settings.py` | ~150 | All services depend on settings |
| 6 | `src/contextualization/base.py` | ~100 | Base contextualizer class |
| 7 | `src/contextualization/claude.py` | ~80 | Anthropic integration |
| 8 | `src/contextualization/groq.py` | ~80 | Groq integration |

### Tier 3: Utilities

| # | Module | Lines | Reason |
|---|--------|-------|--------|
| 9 | `src/models/embedding_model.py` | ~150 | BGE-M3 singleton |
| 10 | `src/security/pii_redaction.py` | ~100 | Data security |
| 11 | `src/utils/structure_parser.py` | ~100 | Structure parsing |
| 12 | `src/config/constants.py` | ~50 | Constants |

## Test Structure

```
tests/
├── unit/                          # Unit tests with mocks
│   ├── services/
│   │   ├── test_llm.py
│   │   ├── test_embeddings.py
│   │   ├── test_filter_extractor.py
│   │   └── test_query_analyzer.py
│   ├── config/
│   │   ├── test_settings.py
│   │   └── test_constants.py
│   ├── contextualization/
│   │   ├── test_base.py
│   │   ├── test_claude.py
│   │   └── test_groq.py
│   └── utils/
│       ├── test_embedding_model.py
│       ├── test_pii_redaction.py
│       └── test_structure_parser.py
├── integration/                   # Integration tests (require Docker/API)
│   ├── test_llm_integration.py
│   └── test_contextualization_integration.py
├── conftest.py                    # Shared fixtures
└── ... (existing tests)
```

## Naming Conventions

```python
# File: test_{module_name}.py
# Class: Test{ClassName}
# Method: test_{method}_{scenario}_{expected}

class TestLLMService:
    async def test_generate_response_valid_input_returns_text(self):
        ...
    async def test_generate_response_empty_context_raises_error(self):
        ...
```

## Mocking Strategy

### Voyage AI (embeddings, rerank)

```python
@pytest.fixture
def mock_voyage_client():
    with patch("httpx.AsyncClient.post") as mock:
        mock.return_value = httpx.Response(
            200,
            json={"data": [{"embedding": [0.1] * 1024}]}
        )
        yield mock
```

### OpenAI-compatible LLM (zai-glm-4.7)

```python
@pytest.fixture
def mock_llm_client():
    with patch("openai.AsyncOpenAI") as mock:
        mock.return_value.chat.completions.create = AsyncMock(
            return_value=Mock(choices=[Mock(message=Mock(content="response"))])
        )
        yield mock
```

### Qdrant (unit tests)

```python
@pytest.fixture
def mock_qdrant():
    with patch("qdrant_client.AsyncQdrantClient") as mock:
        mock.return_value.search = AsyncMock(return_value=[
            Mock(id=1, score=0.95, payload={"text": "chunk"})
        ])
        yield mock
```

### Redis (unit tests)

```python
@pytest.fixture
def mock_redis():
    with patch("redis.asyncio.Redis.from_url") as mock:
        mock.return_value.get = AsyncMock(return_value=None)
        mock.return_value.set = AsyncMock(return_value=True)
        yield mock
```

## TDD Process

### Red-Green-Refactor Cycle

```
1. RED:    Write failing test for method
2. GREEN:  Minimal code to pass test
3. REFACTOR: Improve code, tests stay green
```

### Test Template per Module

```python
# Step 1: Public methods (happy path)
class TestLLMService:
    async def test_generate_response_returns_string(self):
        """Basic call returns string."""

    async def test_generate_stream_yields_chunks(self):
        """Streaming returns chunks."""

# Step 2: Edge cases
    async def test_generate_response_empty_messages_raises(self):
        """Empty message list raises error."""

    async def test_generate_response_timeout_returns_fallback(self):
        """Timeout returns fallback response."""

# Step 3: Error handling
    async def test_generate_response_api_error_logs_and_raises(self):
        """API error is logged and raised."""

    async def test_generate_response_rate_limit_retries(self):
        """Rate limit triggers retry."""
```

### Module Checklist

- [ ] All public methods covered
- [ ] Happy path works
- [ ] Edge cases (empty inputs, None, large data)
- [ ] Error handling (exceptions, timeouts, retries)
- [ ] Coverage >= 80% for module

## First Module: llm.py

### Test Plan

```python
class TestLLMServiceInit:
    def test_init_with_api_key_succeeds(self)
    def test_init_without_api_key_raises(self)
    def test_init_custom_model_sets_model(self)

class TestGenerateResponse:
    async def test_valid_input_returns_response(self)
    async def test_empty_messages_raises_value_error(self)
    async def test_api_timeout_raises_timeout_error(self)
    async def test_rate_limit_triggers_retry(self)
    async def test_invalid_api_key_raises_auth_error(self)

class TestGenerateStream:
    async def test_stream_yields_chunks(self)
    async def test_stream_empty_response_yields_nothing(self)
    async def test_stream_connection_error_raises(self)

class TestFallbackBehavior:
    async def test_api_failure_returns_fallback_from_context(self)
    async def test_no_context_no_fallback_raises(self)
```

**Expected:** 12-15 tests, ~85% coverage for llm.py

## CI/CD Integration

### pyproject.toml Updates

```toml
[tool.pytest.ini_options]
markers = [
    "unit: Unit tests with mocks (fast)",
    "integration: Integration tests (requires Docker)",
    "slow: Tests taking > 5 seconds",
]

[tool.coverage.run]
source = ["src", "telegram_bot"]  # Add telegram_bot
branch = true                      # Branch coverage

[tool.coverage.report]
fail_under = 80                    # CI fails if < 80%
```

### Makefile Commands

```makefile
test-unit:        pytest tests/ -m "not integration" -v
test-integration: pytest tests/ -m integration -v
test-all:         pytest tests/ -v --cov --cov-fail-under=80
```

### GitHub Actions Pipeline

```yaml
jobs:
  unit-tests:
    runs-on: ubuntu-latest
    steps:
      - run: make test-unit          # No Docker, fast

  integration-tests:
    runs-on: ubuntu-latest
    services: [qdrant, redis]
    steps:
      - run: make test-integration   # With Docker
```

## Success Metrics

- Coverage >= 80% for `src/` and `telegram_bot/`
- All 12 modules covered with unit tests
- Integration tests for critical paths
- CI passes in < 5 minutes (unit) / < 15 minutes (full)

## Implementation Order

1. Setup: Create `tests/unit/` structure, update conftest.py with fixtures
2. Module 1: `llm.py` - 12-15 tests
3. Module 2: `embeddings.py` - 10-12 tests
4. Module 3: `filter_extractor.py` - 8-10 tests
5. Module 4: `query_analyzer.py` - 8-10 tests
6. Module 5: `settings.py` - 6-8 tests
7. Module 6-8: Contextualization modules - 15-20 tests total
8. Module 9-12: Utilities - 15-20 tests total
9. Integration tests for critical paths
10. CI/CD pipeline setup

**Total estimated tests:** 80-100 new tests

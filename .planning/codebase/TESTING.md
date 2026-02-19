# Testing Patterns

**Analysis Date:** 2026-02-19

## Test Framework

**Runner:**
- **pytest** >= 8.3.0
- Configuration: `pyproject.toml` [tool.pytest.ini_options]
- asyncio_mode: auto (async tests don't need @pytest.mark.asyncio)
- Default timeout: 30 seconds per test (overridable with @pytest.mark.timeout(N))

**Assertion Library:**
- Standard `assert` statements
- Pytest provides: `assert x in y`, `assert x == y`, introspection

**Run Commands:**

```bash
# All unit tests (fast, ~5 min with -n auto)
uv run pytest tests/unit/ -v

# Parallel execution (4x speedup, recommended)
uv run pytest tests/unit/ -n auto

# Watch mode (continuous re-run)
uv run pytest tests/unit/ --looponfail

# With coverage
uv run pytest tests/unit/ --cov=telegram_bot/services --cov-report=term-missing
make test-cov                    # Opens htmlcov/index.html in browser

# Single test file
uv run pytest tests/unit/test_bot_scores.py -v

# Single test
uv run pytest tests/unit/test_bot_scores.py::TestScoreWriting::test_scores_written_full_pipeline -v

# Skip slow tests
uv run pytest tests/unit/ -m "not slow" -v

# Integration tests (requires Docker)
uv run pytest tests/integration/ -v

# Graph path tests (6 deterministic routing paths, no Docker)
uv run pytest tests/integration/test_graph_paths.py -v
```

## Test File Organization

**Location:** Tests follow source structure
- Source: `telegram_bot/services/qdrant.py`
- Tests: `tests/unit/test_qdrant_service.py`
- Source: `telegram_bot/graph/nodes/retrieve.py`
- Tests: `tests/unit/graph/test_retrieve_node.py`

**Naming:**
- Test files: `test_*.py` (pytest auto-discovery)
- Test classes: `Test*` (optional, groups related tests)
- Test functions: `test_*` (mandatory)
- Helper functions: `_helper_name()` (private, not discovered)

**Directory Structure:**

```
tests/
├── unit/                       # Fast unit tests (~5 min, -n auto)
│   ├── conftest.py             # Isolation fixture (disable Langfuse/OTEL)
│   ├── test_bot_scores.py      # 14 tests
│   ├── test_query_preprocessor.py
│   ├── graph/                  # 31 tests (nodes, edges, assembly)
│   │   ├── test_retrieve_node.py
│   │   ├── test_agentic_nodes.py
│   │   ├── test_edges.py
│   │   ├── test_graph.py
│   │   └── conftest.py         # Graph fixture helpers
│   ├── services/               # 21 tests (kommo, qdrant, etc.)
│   │   ├── test_kommo_client_*.py
│   │   └── test_qdrant_service.py
│   └── contextualization/      # 12 tests (LLM providers)
│       ├── test_openai.py
│       ├── test_groq.py
│       └── test_claude.py
├── integration/                # Deterministic graph path tests
│   ├── test_graph_paths.py     # 6 routing paths
│   └── conftest.py
├── chaos/                      # Resilience tests (service failures)
│   ├── test_qdrant_failures.py
│   ├── test_redis_failures.py
│   └── test_llm_fallback.py
├── e2e/                        # End-to-end pipeline tests
│   ├── test_rag_pipeline.py
│   └── conftest.py
├── baseline/                   # Regression detection
│   ├── test_manager.py         # 8 tests
│   ├── test_collector.py       # 4 tests
│   └── thresholds.yaml         # Regression thresholds
└── legacy/                     # Pre-LangGraph tests (excluded from CI)
    ├── test_api_comparison.py
    └── ...
```

## Test Structure

**Suite Organization:**

All tests follow arrange-act-assert (AAA) pattern:

```python
def test_scores_written_full_pipeline():
    """All scores should be written for a full pipeline result."""
    # ARRANGE: Set up data and mocks
    mock_lf = MagicMock()
    result = {**FULL_PIPELINE_RESULT, "checkpointer_overhead_proxy_ms": 39.0}

    # ACT: Call the function under test
    _run_score_writer(result, mock_lf)

    # ASSERT: Verify behavior
    score_calls = mock_lf.create_score.call_args_list
    score_names = [call.kwargs["name"] for call in score_calls]
    assert "faithfulness" in score_names
    assert "latency_total_ms" in score_names
```

**Patterns:**

**Setup pattern (fixtures):**

```python
@pytest.fixture
def mock_config():
    """Create mock bot config."""
    return BotConfig(
        telegram_token="test-token",
        voyage_api_key="voyage-key",
        llm_api_key="llm-key",
        llm_base_url="https://api.example.com/v1",
        llm_model="gpt-4o-mini",
        qdrant_url="http://localhost:6333",
        redis_url="redis://localhost:6379",
        rerank_provider="none",
    )
```

**Teardown pattern (context manager):**

```python
@contextmanager
def mock_graph_services(**overrides):
    """Patch all graph services for testing."""
    patches = [
        patch("telegram_bot.graph.config.GraphConfig.create_llm"),
        patch("telegram_bot.integrations.cache.CacheLayerManager"),
        patch("telegram_bot.services.qdrant.QdrantService"),
    ]

    with ExitStack() as stack:
        mocks = {p.target.split(".")[-1]: stack.enter_context(p) for p in patches}
        mocks.update(overrides)
        yield mocks
```

**Async test pattern:**

```python
async def test_hybrid_search_returns_results():
    """Hybrid search should return documents and metadata."""
    # asyncio_mode=auto, no decorator needed
    qdrant = QdrantService(url="http://localhost:6333")

    results, metadata = await qdrant.hybrid_search_rrf(
        dense_vector=[0.1] * 1024,
        sparse_vector={"indices": [1, 5], "values": [0.5, 0.3]},
        top_k=5,
    )

    assert len(results) > 0
    assert "backend_error" in metadata
```

**Assertion pattern:**

```python
# Value assertions
assert user.name == "John"
assert 0.85 <= score <= 0.95
assert documents is not None
assert len(documents) == 5

# Collection assertions
assert "chat_id" in response
assert all(doc["score"] > 0.3 for doc in documents)

# Mock call assertions
mock_client.create_lead.assert_called_once()
assert mock_client.create_lead.call_args[1]["lead"].budget == 50000

# Exception assertions
with pytest.raises(RuntimeError, match="Unexpected response"):
    await kommo.create_lead(invalid_lead)
```

## Mocking

**Framework:** unittest.mock (built-in)

**Patterns:**

**AsyncMock for async functions:**

```python
from unittest.mock import AsyncMock, MagicMock

# Async function returning value
mock_qdrant = MagicMock()
mock_qdrant.hybrid_search_rrf = AsyncMock(
    return_value=([doc1, doc2], {"backend_error": False})
)

result = await mock_qdrant.hybrid_search_rrf(...)
```

**Mocking entry points (not deep internals):**

```python
# GOOD: Mock the service factory
patch("telegram_bot.graph.config.GraphConfig.create_llm", return_value=mock_llm)

# AVOID: Mocking low-level libraries
# AVOID: patch("openai.AsyncOpenAI") — patches too low

# GOOD: Mock get_client() wrapper
patch("telegram_bot.services.observability.get_client", return_value=mock_lf)
```

**Patching patterns:**

```python
# Single patch
with patch("module.function", return_value=value):
    result = call_function()

# Multiple patches
with patch("service.KommoClient") as mock_kommo, \
     patch("service.QdrantService") as mock_qdrant:
    # Both mocks available

# Patch with side_effect (callable or exception)
mock_client.request = AsyncMock(side_effect=httpx.TimeoutError())

# Patch with side_effect function
async def fake_download(file_path, destination):
    destination.write(b"fake-data")

message.bot.download_file = AsyncMock(side_effect=fake_download)
```

**What to Mock:**
- External services: Qdrant, Redis, Kommo API, OpenAI, Langfuse
- HTTP clients: `httpx.AsyncClient`, `AsyncOpenAI`
- Heavy ML models: embeddings, rerankers (use lightweight fakes)
- Database: use fixtures with test DB or in-memory mock

**What NOT to Mock:**
- Business logic: test real implementations
- Data structures: test real Pydantic models
- Utility functions: test real implementations
- Observability decorators: mock the service they call, not the decorator itself

## Fixtures and Factories

**Test Data:**

Constants for reusable test data:

```python
# Typical graph result for a full RAG pipeline
FULL_PIPELINE_RESULT = {
    "response": "Вот квартиры до 100000 евро...",
    "query_type": "STRUCTURED",
    "cache_hit": False,
    "cached_response": None,
    "search_results_count": 5,
    "rerank_applied": True,
    "documents_relevant": True,
    "latency_stages": {
        "classify": 0.001,
        "retrieve": 0.200,
        "generate": 0.500,
    },
}

# Cache hit result (short-circuit)
CACHE_HIT_RESULT = {
    "response": "Cached answer here",
    "cache_hit": True,
    "cached_response": "Cached answer here",
    "search_results_count": 0,
    "latency_stages": {
        "classify": 0.001,
        "cache_check": 0.020,
    },
}
```

**Factory functions (private helpers):**

```python
def _make_message(text="квартиры до 100000 евро", user_id=123456789):
    """Create mock Telegram message."""
    message = MagicMock()
    message.text = text
    message.from_user = MagicMock(id=user_id)
    message.chat = MagicMock(id=987654321)
    message.bot = MagicMock()
    message.answer = AsyncMock()
    return message

def _make_llm_completion(content: str) -> MagicMock:
    """Create a mock OpenAI ChatCompletion response."""
    completion = MagicMock()
    completion.choices = [MagicMock(message=MagicMock(content=content))]
    completion.model = "test-model"
    completion.usage = None
    return completion

def _mock_agent_result(**overrides):
    """Create a standard SDK agent result dict."""
    base = {"messages": [MagicMock(content="Response")]}
    base.update(overrides)
    return base
```

**Location:**
- Fixtures: `tests/unit/conftest.py`, `tests/integration/conftest.py`
- Factory functions: in test module or shared conftest
- Test data constants: at top of test module (UPPERCASE_NAME)

## Coverage

**Requirements:** 80% minimum (enforced in `pyproject.toml` fail_under = 80)

**View Coverage:**

```bash
# Generate HTML report
uv run pytest tests/unit/ --cov=telegram_bot/services --cov-report=html

# Open in browser
open htmlcov/index.html

# Terminal report
uv run pytest tests/unit/ --cov=telegram_bot/services --cov-report=term-missing
```

**Configuration (pyproject.toml):**

```toml
[tool.coverage.run]
source = ["src", "telegram_bot"]
branch = true
omit = ["*/tests/*", "*/legacy/*", "scripts/*"]

[tool.coverage.report]
fail_under = 80
exclude_lines = [
    "pragma: no cover",
    "def __repr__",
    "if TYPE_CHECKING:",
    "@abstractmethod",
]
```

**Omit from coverage:**
- Test files: `*/tests/*`
- Legacy code: `*/legacy/*`
- Scripts: `scripts/*`, evaluation scripts
- Setup scripts: `telegram_bot/setup_qdrant_indexes.py`

## Test Types

**Unit Tests:**
- Scope: Single function/method in isolation
- Mocking: All external dependencies (services, HTTP, DB)
- Speed: <1 second per test
- Count: ~130 tests in `tests/unit/`
- Location: `tests/unit/`, `tests/unit/services/`, `tests/unit/graph/`

**Integration Tests:**
- Scope: Multiple components working together
- Mocking: Only external services, not local components
- Speed: <5 seconds per test
- Graph path tests: 6 tests verifying all routing logic without Docker
- Location: `tests/integration/test_graph_paths.py`

**E2E Tests:**
- Scope: Full pipeline from Telegram to LLM response
- Mocking: None (use real services)
- Speed: ~60 seconds total
- Requirements: Docker services running, Telegram API creds
- Location: `tests/e2e/test_rag_pipeline.py`

## Common Patterns

**Async Testing (pytest-asyncio):**

```python
# No decorator needed — asyncio_mode="auto"
async def test_kommo_create_lead():
    """Test async Kommo API call."""
    mock_token_store = AsyncMock()
    mock_token_store.get_valid_token = AsyncMock(return_value="token-123")

    client = KommoClient(subdomain="mycompany", token_store=mock_token_store)

    with patch.object(client, "_request", new_callable=AsyncMock) as mock_request:
        mock_request.return_value = {"_embedded": {"leads": [{"id": 1, "name": "Deal"}]}}
        lead = await client.create_lead(LeadCreate(name="Deal"))

    assert lead.id == 1
    assert lead.name == "Deal"
```

**Error Testing:**

```python
def test_kommo_retries_on_429():
    """Should retry on rate limit (429)."""
    mock_client = MagicMock()
    mock_client.request = AsyncMock(
        side_effect=[
            httpx.Response(429, json={"error": "rate_limit"}),
            httpx.Response(200, json={"_embedded": {"leads": [...]}}),
        ]
    )

    # tenacity retry should convert 429 to success on second attempt
    # (actual test uses the @_kommo_retry decorator on _request method)

def test_qdrant_timeout_raises():
    """Should raise RuntimeError when Qdrant times out."""
    mock_qdrant = MagicMock()
    mock_qdrant.query_points = AsyncMock(
        side_effect=httpx.ReadTimeout("Timeout after 30s")
    )

    with pytest.raises(httpx.ReadTimeout):
        await qdrant.hybrid_search_rrf(...)
```

**Parameterized Tests:**

```python
@pytest.mark.parametrize("query,expected_type", [
    ("Привет", "CHITCHAT"),
    ("Квартиры до 100000", "STRUCTURED"),
    ("Помощь", "CHITCHAT"),
])
def test_classify_query_type(query, expected_type):
    """Test query classification."""
    classifier = QueryClassifier(llm=mock_llm)
    result = classifier.classify(query)
    assert result.query_type == expected_type
```

**Pytest Markers:**

```python
@pytest.mark.unit
def test_fast():
    pass

@pytest.mark.slow
def test_slow():
    pass

@pytest.mark.asyncio
async def test_async_pattern_old():  # Not needed with asyncio_mode="auto"
    pass

@pytest.mark.timeout(60)  # Override default 30s
def test_long_running():
    pass

@pytest.mark.skip(reason="WIP")
def test_not_ready():
    pass

@pytest.mark.xfail(reason="Known issue #123")
def test_expected_failure():
    pass

@pytest.mark.parametrize("arg", [1, 2, 3])
def test_with_params(arg):
    pass
```

## Isolation & Test Hygiene

**sys.modules Hygiene (critical for xdist):**

Policy: **NEVER assign to `sys.modules` at module level in test files.**

```python
# FORBIDDEN at module level
sys.modules["foo"] = MagicMock()

# OK in fixture (uses monkeypatch)
@pytest.fixture
def mock_module(monkeypatch):
    monkeypatch.setitem(sys.modules, "foo", MagicMock())

# OK in conftest pytest_configure hook (with cleanup)
def pytest_configure(config):
    sys.modules["heavy_lib"] = MagicMock()

def pytest_unconfigure(config):
    sys.modules.pop("heavy_lib", None)
```

**Why:** Module-level patching leaks mocks into the session, breaks xdist worker isolation, causes flaky tests from import-order dependencies.

**Guard:** `test_module_pollution.py::test_no_module_level_sys_modules_assignment` scans all test files via AST and fails if bare module-level `sys.modules[...] = ...` is found.

**Langfuse/OTEL Isolation:**

Unit tests disable Langfuse and OTEL to avoid network calls:

```python
# tests/unit/conftest.py
@pytest.fixture(autouse=True)
def isolate_otel_langfuse(monkeypatch):
    """Block OTEL/Langfuse network calls in unit tests."""
    monkeypatch.setenv("OTEL_SDK_DISABLED", "true")
    monkeypatch.setenv("LANGFUSE_ENABLED", "false")
    monkeypatch.delenv("LANGFUSE_SECRET_KEY", raising=False)

    # Patch entry points
    with patch("src.observability.otel_setup.setup_opentelemetry"), \
         patch("telegram_bot.services.observability.get_client"):
        yield
```

## Dependencies

| Package | Version | Purpose |
|---------|---------|---------|
| pytest | >=8.3.0 | Test framework |
| pytest-asyncio | >=0.24.0 | Async test support |
| pytest-cov | >=5.0.0 | Coverage reporting |
| pytest-httpx | >=0.35.0 | HTTP request mocking |
| pytest-xdist | >=3.8.0 | Parallel test execution (-n auto) |
| pytest-timeout | >=2.3.0 | Per-test timeout enforcement |
| pytest-split | >=0.11.0 | CI test sharding by duration |

## CI Pipeline & Sharding

**CI Jobs (GitHub Actions):**

1. **lint** (ruff + mypy) — runs on all Python files
2. **test** (sharded unit tests) — 4 parallel jobs splitting tests by duration
3. **baseline-compare** (PR only) — regression detection via Langfuse

**Sharding with pytest-split:**

Splits `tests/unit/` across 4 workers using test durations in `.test_durations`:

```bash
# Run shard 2 of 4 (as in CI)
uv run pytest tests/unit/ --splits 4 --group 2 -n auto --dist loadscope

# Regenerate durations after refactors
uv run pytest tests/unit/ --store-durations --timeout=30 -m "not legacy_api" -q
```

**Graph path tests (separate CI job):**

```bash
# No Docker required, ~5s
uv run pytest tests/integration/test_graph_paths.py -v
```

## Troubleshooting

| Problem | Fix |
|---------|-----|
| xdist worker isolation failure | Check for module-level `sys.modules` assignment |
| Async test hangs | Verify `asyncio_mode = "auto"` in pyproject.toml |
| Mock not being called | Check patch target path: `patch("actual.import.path")` not just `patch("function_name")` |
| Flaky test | Check for timing assumptions, use `AsyncMock(return_value=...)` not `MagicMock()` for async |
| Langfuse network call in unit test | Ensure isolate_otel_langfuse fixture is active (autouse=True) |
| Test timeout (30s) | Use `@pytest.mark.timeout(60)` to override or refactor test |
| Coverage gaps | Run `pytest --cov-report=html` and check htmlcov/index.html |

---

*Testing analysis: 2026-02-19*

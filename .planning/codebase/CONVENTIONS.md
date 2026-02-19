# Coding Conventions

**Analysis Date:** 2026-02-19

## Naming Patterns

**Files:**
- Snake case: `bot.py`, `qdrant_service.py`, `query_preprocessor.py`
- Pattern: descriptive lowercase with underscores
- Services: `{name}_service.py` (e.g., `llm_service.py`, `qdrant_service.py`, `lead_scoring_service.py`)
- Clients: `{name}_client.py` (e.g., `kommo_client.py`, `bge_m3_client.py`)
- Models: `{name}_models.py` (e.g., `kommo_models.py`)
- Stores: `{name}_store.py` (e.g., `lead_scoring_store.py`, `funnel_analytics_store.py`)
- Graph nodes: `{node_name}.py` in `telegram_bot/graph/nodes/` (e.g., `retrieve.py`, `grade.py`, `rerank.py`)

**Functions:**
- Snake case: `async def retrieve_node()`, `def hybrid_search_rrf()`, `async def create_lead()`
- Private functions: prefix with single underscore `_get_collection_name()`, `_request()`
- Module-level private constants: `_kommo_retry`, `_bge_retry`, `RETRYABLE_ERRORS` (uppercase for public constants)
- Async functions: descriptive verb-noun pairs: `await qdrant.hybrid_search_rrf()`, `await kommo.create_lead()`

**Variables:**
- Snake case: `query_embedding`, `sparse_embedding`, `cache_hit`, `llm_response`
- Boolean flags: prefix with verb `is_`, `has_`, `should_`: `is_relevant`, `has_documents`, `should_rerank`
- List/dict containers: plural names: `documents`, `results`, `latency_stages`, `scores`
- Internal state in classes: `_client`, `_base_url`, `_token_store`

**Types & Classes:**
- PascalCase: `QdrantService`, `KommoClient`, `BGEM3HybridEmbeddings`, `LeadScoreRecord`, `DenseResult`
- Exception classes: `ConfigError`, `ValidationError` (inherit from built-in exceptions or custom base)
- Dataclasses: `@dataclass DenseResult`, `@dataclass RerankResult`, `@dataclass HybridResult`
- TypedDict: `RAGState = TypedDict("RAGState", {"query": str, "documents": list})`
- Pydantic models: `class LeadCreate(BaseModel)`, `class ContactCreate(BaseModel)` with `model_dump(exclude_none=True, by_alias=True)`

## Code Style

**Formatting:**
- Line length: **100 characters** (configured in `pyproject.toml`)
- Indentation: **4 spaces** (no tabs)
- String quotes: **double quotes** (`"string"` not `'string'`)
- Trailing commas: respected (magic trailing comma) for multi-line structures
- Line ending: auto-detected (LF on Linux, CRLF on Windows)

**Imports:**
- Tool: **Ruff** (replaces flake8, black, isort, pyupgrade, autoflake)
- Order (isort replacement):
  1. Standard library imports: `import asyncio`, `from typing import Any`
  2. Third-party imports: `import httpx`, `import pytest`, `from qdrant_client import AsyncQdrantClient`
  3. First-party imports: `from telegram_bot.services.qdrant import QdrantService`, `from src.retrieval.search_engines import BaseSearchEngine`
  4. Blank line between groups
- Single-line imports preferred: `from x import a` not `from x import (a, b, c)` unless line exceeds 100 chars
- Force single-line: disabled (allow grouped imports for related items)
- Lines after imports: **2 blank lines** before module-level code
- Unused imports in `__init__.py`: allowed with `# type: ignore[import]`
- Wildcard imports: forbidden except in `__init__.py` for barrel exports

**Linting with Ruff:**
- Run: `ruff check --fix` (auto-fixes buggy patterns)
- Rules enabled: E, W, F, B, I, UP, SIM, C4, PIE, T20, RET, ARG, PTH, PERF, RUF, FURB, ASYNC
- Rules disabled: E501 (handled by formatter), PTH (pathlib migration not critical), ARG002 (interface methods)
- Per-file ignores in `telegram_bot/config.py`: `E402` (late imports)
- Pre-commit: ruff-check runs FIRST (--fix --exit-non-zero-on-fix), then ruff-format

**Type Checking:**
- Tool: **MyPy** (strict Python 3.12)
- Configuration: `pyproject.toml` [tool.mypy]
- Explicit types on function signatures: `async def create_lead(self, lead: LeadCreate) -> Lead:`
- Type hints: required for public API, encouraged for internal helpers
- TYPE_CHECKING blocks: import types to avoid circular imports at runtime
- Ignore missing imports: `ignore_missing_imports = true` (for untyped packages)
- Legacy modules with ignored errors: `src.ingestion.*`, `src.contextualization.*`, `src.retrieval.*`

## Import Organization

**Order (ruff isort):**

```python
from __future__ import annotations  # Always first if used

# Standard library
import asyncio
import json
import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, cast

# Third-party
import httpx
import numpy as np
import pytest
from pydantic import BaseModel
from qdrant_client import AsyncQdrantClient
from tenacity import retry, stop_after_attempt

# First-party
from telegram_bot.config import BotConfig
from telegram_bot.services.kommo_client import KommoClient
from src.retrieval.search_engines import BaseSearchEngine

if TYPE_CHECKING:
    from telegram_bot.services.kommo_token_store import KommoTokenStore

logger = logging.getLogger(__name__)
```

**Path aliases:**
- `src` → absolute imports: `from src.retrieval.search_engines import BaseSearchEngine`
- `telegram_bot` → absolute imports: `from telegram_bot.services.qdrant import QdrantService`
- No relative imports (except in __init__.py for barrel exports)

## Error Handling

**Pattern: Exception types and context:**

```python
# Raise RuntimeError for unexpected API responses
if not isinstance(response_json, dict):
    msg = "Unexpected Kommo API response shape."
    raise RuntimeError(msg) from None

# Raise HTTPStatusError via raise_for_status() (httpx pattern)
response = await self._client.request(method, path, headers=headers)
response.raise_for_status()  # Raises httpx.HTTPStatusError on 4xx/5xx

# Catch specific exceptions and retry with tenacity
RETRYABLE_ERRORS = (
    httpx.ConnectError,
    httpx.ReadTimeout,
    httpx.ConnectTimeout,
    httpx.PoolTimeout,
)

_kommo_retry = retry(
    retry=retry_if_exception_type(RETRYABLE_ERRORS) | retry_if_exception(_retryable_http_status),
    wait=wait_exponential_jitter(initial=1, max=8, jitter=2),
    stop=stop_after_attempt(3),
    before_sleep=before_sleep_log(logger, logging.WARNING),
    reraise=True,
)
```

**No empty except clauses:**
- Use `except SpecificException as e:` to catch and log
- Use `with contextlib.suppress(Exception):` for expected failure cases (used sparingly in test fixtures)

**Async error handling:**
- Don't swallow exceptions in async context managers
- Return False from `__aexit__` to propagate exceptions: `mock_cm.__aexit__ = AsyncMock(return_value=False)`

**Logging errors:**

```python
logger = logging.getLogger(__name__)
logger.error(f"Failed to sync lead {lead_id}: {e}", exc_info=True)
logger.warning(f"Retrying request to Kommo API (attempt {attempt})")
```

## Logging

**Framework:** Python `logging` module + `getLogger(__name__)`

**Pattern:**

```python
import logging

logger = logging.getLogger(__name__)

# Module-level logger in each file
# Logging level controlled by environment

logger.info("Starting RAG pipeline")
logger.warning(f"Kommo OAuth2 token refresh, remaining ttl={remaining_ms}ms")
logger.error(f"Qdrant timeout after {timeout}s: {e}", exc_info=True)
```

**Levels:**
- `INFO`: major flow events (started graph, cache hit/miss, results found)
- `WARNING`: retries, degraded operation (missing optional config), oauth2 refresh
- `ERROR`: exceptions, failed requests, service unavailability
- `DEBUG`: not used (prefer explicit logging)

**PII Masking:** `telegram_bot/observability.py` has masking helpers for user_id, phone, email

## Comments

**When to Comment:**
- Explain WHY, not WHAT (code should be self-explanatory)
- Complex algorithms: explain the logic
- Non-obvious design decisions: e.g., why we retry on 429/5xx but not 400/401
- Workarounds: document known issues and upstream tracking
- Edge cases: explain boundary conditions

**Example:**

```python
# RRF scores use 1/(k+rank) formula where k=60
# This produces scores in range ~0.001-0.016 for typical top-20 results
# Threshold 0.005 filters out low-signal matches
if top_score > relevance_threshold_rrf:
    documents_relevant = True
```

**Avoid:**

```python
# Get the embedding  ← This is obvious from code
embedding = await embeddings.aembed_query(query)

# NOT USEFUL: Loop over documents ← Code already shows this
for doc in documents:
    ...
```

**JSDoc/Docstrings:** Google style for public APIs

```python
def hybrid_search_rrf(
    self, *, dense_vector: list[float], sparse_vector: dict, top_k: int = 20
) -> tuple[list[dict], dict]:
    """Search using RRF fusion of dense and sparse embeddings.

    Combines dense (semantic) and sparse (keyword) similarity scores
    using Reciprocal Rank Fusion (RRF) to balance both signals.

    Args:
        dense_vector: 1024-dim dense embedding from BGE-M3
        sparse_vector: Sparse embedding dict with 'indices' and 'values'
        top_k: Number of results to return (default 20)

    Returns:
        Tuple of (documents, metadata_dict) where:
        - documents: list of dicts with text, score, id, metadata
        - metadata_dict: {'backend_error': bool, 'error_type': str | None}

    Raises:
        RuntimeError: If Qdrant connection fails after retries
    """
```

## Function Design

**Size:** Aim for <50 LOC per function, max 100 LOC

**Parameters:**
- Use keyword-only args for services and optional params: `async def retrieve_node(..., *, cache, qdrant, embeddings)`
- Max 5 positional args before requiring keyword-only
- Use dataclasses for complex parameter sets: `@dataclass class SearchParams:` rather than many args

**Return Values:**
- Return typed values (not `Any` unless necessary)
- Async functions return the same type as sync equivalents: `async def create_lead(...) -> Lead:`
- When returning multiple values, use tuple or dataclass: `return (documents, metadata)` or `return SearchResult(...)`
- Never return `None` when empty collection expected; return empty list/dict: `return []` not `return None`

**Async/Await:**
- Use `async def` for I/O-bound operations: `async def hybrid_search_rrf()`, `async def create_lead()`
- Use `await` consistently; no fire-and-forget without `asyncio.create_task()`
- Use `asyncio.gather(*tasks)` for parallel awaits: `results = await asyncio.gather(emb1, emb2)`
- Use `async with` for context managers: `async with redis.pipeline() as pipe:`

## Module Design

**Exports:** Barrel exports in `__init__.py` for public API

```python
# telegram_bot/services/__init__.py
from telegram_bot.services.kommo_client import KommoClient
from telegram_bot.services.qdrant import QdrantService

__all__ = ["KommoClient", "QdrantService"]
```

**Barrel Files:** Minimize re-exports; prefer explicit imports in consumer code

**No module-level side effects:**
- Avoid module-level `logger.info()` calls (logs on import)
- Avoid top-level service initialization (use factories or lazy loading)
- OK: `logger = logging.getLogger(__name__)` (just creates logger, doesn't log)

**Class Responsibilities:**
- Single responsibility per service class
- `KommoClient`: HTTP adapter with OAuth2 auto-refresh
- `KommoTokenStore`: Redis-backed token management
- `LeadScoringStore`: Async database operations (upsert, query)
- `NurturingService`: Business logic (scheduling, state transitions)

**Dependency Injection:**
- Constructor injection preferred: `def __init__(self, redis: Redis, api_key: str):`
- Service factories in `GraphConfig`: `llm = gc.create_llm()`, `embeddings = gc.create_hybrid_embeddings()`
- Avoid global singletons (use fixtures in tests)

## Dataclass & Pydantic Patterns

**Dataclasses (for simple data transfer):**

```python
from dataclasses import dataclass, field

@dataclass
class DenseResult:
    vectors: list[list[float]]
    processing_time: float | None = None

@dataclass
class SearchResult:
    documents: list[dict] = field(default_factory=list)
    elapsed_ms: float = 0.0
```

**Pydantic v2 models (for API validation):**

```python
from pydantic import BaseModel, Field

class LeadCreate(BaseModel):
    name: str
    budget: int | None = None
    custom_fields: dict[str, Any] = Field(default_factory=dict)

    class Config:
        alias_generator = to_camel  # Use camelCase in JSON

    def model_dump(self, exclude_none=True, by_alias=True) -> dict:
        """Serialize with field aliases (camelCase for API)."""
```

## Async Patterns

**Context managers:**

```python
async with httpx.AsyncClient(timeout=30.0) as client:
    response = await client.get(url)

async with redis.pipeline() as pipe:
    pipe.set(key, value)
    await pipe.execute()
```

**Gathering parallel tasks:**

```python
dense_task = embeddings.aembed_query(query)
sparse_task = sparse_embeddings.aembed_query(query)
dense_vec, sparse_vec = await asyncio.gather(dense_task, sparse_task)
```

**No blocking calls in async context:**
- Use `httpx.AsyncClient` not `requests.get()`
- Use `AsyncQdrantClient` not `QdrantClient`
- Avoid `time.sleep()` (use `asyncio.sleep()`)

## Testing Patterns

**Test file naming:**
- `test_*.py` in `tests/unit/`, `tests/integration/`, `tests/chaos/`, `tests/e2e/`
- Match source structure: `telegram_bot/services/qdrant.py` → `tests/unit/test_qdrant_service.py`

**Fixtures:**
- Use `@pytest.fixture` for setup/teardown
- Auto-use: `@pytest.fixture(autouse=True)` for isolation (e.g., mocking Langfuse)
- Scope: `scope="session"` for expensive setup, `scope="function"` for test isolation

**Mocking patterns:**
- Mock at entry points, not deep in call chain: patch `get_client()` not `langfuse.Langfuse`
- Use `AsyncMock()` for async functions
- Use `patch.object()` for class methods: `patch.object(MyClass, "method")`
- Avoid patching `sys.modules` at module level (causes xdist isolation issues)

---

*Convention analysis: 2026-02-19*

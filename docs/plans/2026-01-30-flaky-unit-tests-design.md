# Design: Fix Flaky Unit Tests After uv Migration

**Date:** 2026-01-30
**Status:** Draft
**Author:** W3 (Claude)

## Problem Statement

After migrating dependencies to uv + dependency-groups, 4 unit tests fail when running the full suite but pass individually (flaky):

1. `tests/unit/test_bot_scores.py::TestHandleQueryScores::test_scores_query_type`
2. `tests/unit/test_main.py::TestMainFunction::test_main_success_flow`
3. `tests/unit/test_main.py::TestMainFunction::test_main_no_telegram_token_exits_early`
4. `tests/unit/test_otel_setup.py::test_setup_opentelemetry`

**Observed behavior:** Tests hang for minutes (not fail fast) — indicates blocking initialization, not assertion failures.

## Root Cause Analysis

### 1. OTEL/Langfuse Blocking Initialization (Primary)

**Symptom:** `test_otel_setup` runs 5+ minutes without completing.

**Cause:** `BatchSpanProcessor` and `OTLPSpanExporter` attempt network connections during initialization. Environment variables (`OTEL_SDK_DISABLED=true`) are set in `conftest.py` but:
- Set via `setdefault()` — doesn't override if already set
- Applied after some modules already imported
- OTEL SDK may ignore these flags once providers are created

**Evidence:** Process hangs on pytest collection/first test, not on assertions.

### 2. sys.modules MagicMock Without __spec__ (Secondary)

**Symptom:** Import-order-dependent failures, `ValueError: module.__spec__ is not set`.

**Cause:** `tests/conftest.py` lines 48-57 insert `MagicMock()` into `sys.modules` for `sentence_transformers` and `FlagEmbedding`. These mocks lack `__spec__` attribute, breaking `importlib.util.find_spec()` checks used by ML libraries.

**Code:**
```python
# Current (broken)
mock_st = MagicMock()
sys.modules["sentence_transformers"] = mock_st
```

### 3. Shared State Between Tests (Secondary)

**Symptom:** `test_scores_query_type` returns `query_type=1.0` (SIMPLE) instead of `2.0` (COMPLEX).

**Cause:** `classify_query` mock not called because earlier test polluted:
- Global Langfuse client state
- Module-level singletons in `telegram_bot.bot`
- `sys.modules` cache for `telegram_bot.main`

The `cleanup_modules` fixture in `test_main.py` only clears `telegram_bot.main*`, not related modules.

## Design

### Architecture

```
tests/
├── conftest.py              # Shared fixtures (HTTP mocks, sample data)
├── unit/
│   ├── conftest.py          # NEW: Unit-specific isolation fixtures
│   ├── test_main.py         # Uses unit/conftest.py autouse fixtures
│   ├── test_otel_setup.py   # Uses unit/conftest.py autouse fixtures
│   └── test_bot_scores.py   # Uses unit/conftest.py autouse fixtures
└── integration/             # Not affected by unit isolation
```

### Component 1: Unit-Level Isolation Fixture

**File:** `tests/unit/conftest.py` (new)

**Purpose:** Block all network I/O and reset global state before each unit test.

**Approach:**
```python
import pytest
from unittest.mock import MagicMock, patch

@pytest.fixture(autouse=True)
def isolate_unit_test(monkeypatch):
    """Block OTEL/Langfuse network calls and reset state for unit tests."""
    # 1. Force environment (override, not setdefault)
    monkeypatch.setenv("OTEL_SDK_DISABLED", "true")
    monkeypatch.setenv("OTEL_TRACES_EXPORTER", "none")
    monkeypatch.setenv("OTEL_METRICS_EXPORTER", "none")
    monkeypatch.setenv("LANGFUSE_ENABLED", "false")
    monkeypatch.setenv("LANGFUSE_HOST", "")

    # 2. Patch OTEL exporters before any module imports them
    with patch("opentelemetry.exporter.otlp.proto.grpc.trace_exporter.OTLPSpanExporter", MagicMock()):
        with patch("opentelemetry.exporter.otlp.proto.grpc.metric_exporter.OTLPMetricExporter", MagicMock()):
            with patch("opentelemetry.sdk.trace.export.BatchSpanProcessor", MagicMock()):
                yield
```

**Why autouse:** Every unit test gets isolation without explicit fixture usage.

**Why monkeypatch.setenv:** Properly restored after each test, unlike `os.environ`.

### Component 2: Fix sys.modules Mocking

**File:** `tests/conftest.py` (modify)

**Option A (Recommended): Remove sys.modules mocks entirely**

```python
# DELETE lines 40-61 (_setup_mock_heavy_imports)
# DELETE lines 64-88 (_setup_mock_optional_telegram_deps)

# Tests needing these libraries use:
# - pytest.importorskip("sentence_transformers")
# - @pytest.mark.skipif(not HAS_AIOGRAM, ...)
```

**Option B (Minimal): Use proper ModuleType with __spec__**

```python
import types
import importlib.machinery

def _create_stub_module(name: str) -> types.ModuleType:
    """Create a stub module with proper __spec__ for importlib compatibility."""
    mod = types.ModuleType(name)
    mod.__spec__ = importlib.machinery.ModuleSpec(name, loader=None)
    mod.__file__ = f"<stub:{name}>"
    return mod

def _setup_mock_heavy_imports():
    if "sentence_transformers" in sys.modules:
        return

    mock_st = _create_stub_module("sentence_transformers")
    mock_st.CrossEncoder = MagicMock()
    mock_st.SentenceTransformer = MagicMock()
    sys.modules["sentence_transformers"] = mock_st

    mock_flag = _create_stub_module("FlagEmbedding")
    mock_flag.BGEM3FlagModel = MagicMock()
    sys.modules["FlagEmbedding"] = mock_flag
```

### Component 3: Enhanced Module Cleanup for test_main.py

**File:** `tests/unit/test_main.py` (modify)

**Current:** Only cleans `telegram_bot.main*`

**Proposed:** Clean all related modules to ensure fresh import:

```python
@pytest.fixture(autouse=True)
def cleanup_modules(self):
    """Clear module cache for fresh imports."""
    prefixes = (
        "telegram_bot.main",
        "telegram_bot.bot",
        "telegram_bot.config",
        "telegram_bot.logging_config",
        "src.observability",
    )

    def _clear():
        for key in list(sys.modules.keys()):
            if key.startswith(prefixes):
                del sys.modules[key]

    _clear()
    yield
    _clear()
```

### Component 4: Fresh Import for test_otel_setup.py

**File:** `tests/unit/test_otel_setup.py` (modify)

**Current:** Calls `reset_otel_mocks()` at module level (line 34), then imports `otel_setup`.

**Problem:** Module-level execution happens once at collection, not per-test.

**Proposed:** Move to fixture with importlib.reload:

```python
@pytest.fixture(autouse=True)
def fresh_otel_module():
    """Ensure fresh otel_setup module for each test."""
    mocks = reset_otel_mocks()

    # Remove cached module
    import sys
    sys.modules.pop("src.observability.otel_setup", None)

    yield

    # Cleanup mocks
    for name in mocks:
        sys.modules.pop(name, None)

# Then import inside test function or use importlib
def test_setup_opentelemetry(fresh_otel_module):
    from src.observability.otel_setup import setup_opentelemetry
    # ... test code
```

### Component 5: Fix test_bot_scores.py Fixture

**File:** `tests/unit/test_bot_scores.py` (modify)

**Problem:** `BotConfig` fixture missing fields that `handle_query` reads before `classify_query`.

**Proposed:** Add missing config fields and assertion:

```python
@pytest.fixture
def bot_handler(self):
    from telegram_bot.bot import PropertyBot
    from telegram_bot.config import BotConfig

    handler = PropertyBot.__new__(PropertyBot)
    handler.config = BotConfig(
        telegram_token="test",
        voyage_api_key="test",
        llm_api_key="test",
        llm_model="test-model",
        cesc_enabled=False,
        # Add missing fields that handle_query accesses:
        voyage_model_queries="voyage-3-lite",
        voyage_model_rerank="rerank-2",
        qdrant_collection="test",
    )
    # ... rest of fixture

# In test, add verification:
async def test_scores_query_type(self, bot_handler, mock_message):
    # ... existing code ...
    await bot_handler.handle_query(mock_message)

    # Verify mock was actually called
    mock_classify_query.assert_called_once()
    # ... rest of assertions
```

## Implementation Order

| Priority | Task | File(s) | Criteria |
|----------|------|---------|----------|
| P0 | Create unit isolation fixture | `tests/unit/conftest.py` | `test_otel_setup` completes in <5s |
| P0 | Fix sys.modules mocking | `tests/conftest.py` | No `__spec__` errors |
| P1 | Expand module cleanup | `tests/unit/test_main.py` | Tests pass in any order |
| P1 | Fresh import per test | `tests/unit/test_otel_setup.py` | 5x runs same result |
| P1 | Fix bot_handler fixture | `tests/unit/test_bot_scores.py` | `query_type=2.0` stable |
| P2 | Final verification | - | `uv run pytest tests/unit -v` passes 5x |

## Verification

```bash
# Step 1: Single test no longer hangs
timeout 10 uv run pytest tests/unit/test_otel_setup.py::test_setup_opentelemetry -v

# Step 2: All 4 tests pass
uv run pytest tests/unit/test_bot_scores.py::TestHandleQueryScores::test_scores_query_type \
  tests/unit/test_main.py::TestMainFunction::test_main_success_flow \
  tests/unit/test_main.py::TestMainFunction::test_main_no_telegram_token_exits_early \
  tests/unit/test_otel_setup.py::test_setup_opentelemetry -v

# Step 3: Full unit suite passes
uv run pytest tests/unit/ -v

# Step 4: Stability (5 runs)
for i in {1..5}; do uv run pytest tests/unit/ -q || echo "FAIL $i"; done
```

## Risks and Mitigations

| Risk | Mitigation |
|------|------------|
| Unit isolation breaks integration tests | `tests/unit/conftest.py` only applies to `tests/unit/**` |
| Over-mocking hides real bugs | Keep mocks minimal; integration tests use real OTEL |
| ModuleType stubs behave differently | Option A (remove mocks) preferred over Option B |

## Not in Scope

- Changes to production code (`telegram_bot/bot.py`, `src/observability/otel_setup.py`)
- Integration or E2E test changes
- Performance optimization of test suite

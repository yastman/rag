# Fix Flaky Unit Tests Implementation Plan

**Goal:** Make 4 flaky unit tests pass reliably after uv migration by isolating OTEL/Langfuse initialization and fixing sys.modules mocking.

**Architecture:** Create unit-specific conftest.py with autouse fixture that blocks OTEL network calls via monkeypatch. Replace MagicMock sys.modules entries with proper ModuleType stubs that include `__spec__`. Expand module cleanup in test files.

**Tech Stack:** pytest, unittest.mock, monkeypatch, types.ModuleType, importlib.machinery.ModuleSpec

**Prerequisites:**
- pytest-timeout NOT installed — use shell `timeout` command instead of `--timeout` flag
- All commands use `timeout 30 uv run pytest ...` pattern

---

## Task 1: Create Unit-Level Isolation Fixture

**Files:**
- Create: `tests/unit/conftest.py`

**Step 1: Create the conftest file with OTEL isolation**

```python
"""Unit test specific fixtures for isolation."""

import sys
from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture(autouse=True)
def isolate_otel_langfuse(monkeypatch):
    """Block OTEL/Langfuse network calls in unit tests.

    This fixture runs automatically before each unit test to prevent:
    - OTEL exporters from attempting network connections
    - Langfuse from initializing real clients
    - Test hangs due to blocking network I/O
    """
    # Force environment variables (override, not setdefault)
    monkeypatch.setenv("OTEL_SDK_DISABLED", "true")
    monkeypatch.setenv("OTEL_TRACES_EXPORTER", "none")
    monkeypatch.setenv("OTEL_METRICS_EXPORTER", "none")
    monkeypatch.setenv("OTEL_LOGS_EXPORTER", "none")
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "")
    monkeypatch.setenv("LANGFUSE_ENABLED", "false")
    monkeypatch.setenv("LANGFUSE_HOST", "")
    monkeypatch.setenv("LANGFUSE_TRACING_ENABLED", "false")

    # Create no-op mocks
    mock_noop = MagicMock()

    # Patch at entry points to prevent any network initialization
    patches = [
        # OTEL entry point - make setup_opentelemetry a no-op
        patch("src.observability.otel_setup.setup_opentelemetry", mock_noop),
        # Langfuse entry point - return mock client
        patch("langfuse.Langfuse", mock_noop),
        patch("telegram_bot.services.observability.get_client", lambda: mock_noop),
        # Fallback: patch low-level OTEL exporters in case setup_opentelemetry is called
        patch(
            "opentelemetry.exporter.otlp.proto.grpc.trace_exporter.OTLPSpanExporter",
            mock_noop,
        ),
        patch(
            "opentelemetry.exporter.otlp.proto.grpc.metric_exporter.OTLPMetricExporter",
            mock_noop,
        ),
        patch("opentelemetry.sdk.trace.export.BatchSpanProcessor", mock_noop),
        patch(
            "opentelemetry.sdk.metrics.export.PeriodicExportingMetricReader",
            mock_noop,
        ),
    ]

    for p in patches:
        try:
            p.start()
        except Exception:
            pass  # Module may not be imported yet

    yield

    for p in patches:
        try:
            p.stop()
        except Exception:
            pass
```

**Step 2: Verify file exists**

Run: `ls -la tests/unit/conftest.py`
Expected: File exists with correct permissions

**Step 3: Commit**

```bash
git add tests/unit/conftest.py
git commit -m "test(unit): add OTEL isolation fixture for unit tests"
```

---

## Task 2: Fix sys.modules Mocking in Root conftest.py

**Files:**
- Modify: `tests/conftest.py:40-61`

**Decision on pandas:** Do NOT mock pandas via sys.modules. Let it be absent naturally.
Tests requiring pandas use `@pytest.mark.skipif` or `pytest.importorskip("pandas")`.

**Step 1: Replace MagicMock with ModuleType stubs**

Replace lines 40-61 in `tests/conftest.py`:

```python
def _setup_mock_heavy_imports():
    """Mock slow-to-import ML libraries at startup.

    Uses proper ModuleType with __spec__ to avoid breaking importlib.util.find_spec().

    NOTE: Do NOT mock pandas here. Let it be absent naturally, and tests that need
    it should use pytest.importorskip("pandas") or @needs_pandas marker.
    """
    import importlib.machinery
    import types

    def _create_stub_module(name: str) -> types.ModuleType:
        """Create a stub module with proper __spec__ for importlib compatibility."""
        mod = types.ModuleType(name)
        mod.__spec__ = importlib.machinery.ModuleSpec(name, loader=None)
        mod.__file__ = f"<stub:{name}>"
        mod.__loader__ = None
        mod.__package__ = name.rsplit(".", 1)[0] if "." in name else name
        return mod

    # Skip if already mocked with real module
    if "sentence_transformers" in sys.modules and hasattr(
        sys.modules["sentence_transformers"], "__spec__"
    ):
        return

    # Mock sentence_transformers with proper module stub
    mock_st = _create_stub_module("sentence_transformers")
    mock_st.CrossEncoder = MagicMock()
    mock_st.SentenceTransformer = MagicMock()
    sys.modules["sentence_transformers"] = mock_st

    # Mock FlagEmbedding with proper module stub
    mock_flag = _create_stub_module("FlagEmbedding")
    mock_flag.BGEM3FlagModel = MagicMock()
    sys.modules["FlagEmbedding"] = mock_flag
```

**Step 2: Run test to verify no __spec__ errors**

Run: `timeout 30 uv run pytest tests/unit/test_settings.py -v`
Expected: PASS (no `__spec__ is not set` errors)

**Step 3: Commit**

```bash
git add tests/conftest.py
git commit -m "fix(test): use ModuleType with __spec__ for sys.modules mocks"
```

---

## Task 3: Fix test_otel_setup.py Fresh Import

**Files:**
- Modify: `tests/unit/test_otel_setup.py`

**Approach:** Do NOT replace entire file or mock opentelemetry hierarchy in sys.modules.
Instead: clear only `src.observability.otel_setup` module before each test, keep targeted patches.

**Step 1: Add autouse fixture to clear otel_setup module only**

Add this fixture at the top of the file (after imports, before `reset_otel_mocks`):

```python
@pytest.fixture(autouse=True)
def fresh_otel_setup_module():
    """Clear src.observability.otel_setup from cache to ensure fresh import.

    NOTE: We do NOT mock opentelemetry hierarchy in sys.modules - that's fragile.
    Instead, we rely on targeted patches inside test functions.
    """
    # Clear only our module, not opentelemetry itself
    sys.modules.pop("src.observability.otel_setup", None)
    sys.modules.pop("src.observability", None)
    yield
    sys.modules.pop("src.observability.otel_setup", None)
    sys.modules.pop("src.observability", None)
```

**Step 2: Keep the existing `reset_otel_mocks()` call at module level**

The existing `reset_otel_mocks()` at line 34 provides fallback mocks for the OTEL namespace.
Keep it as-is, but the autouse fixture ensures fresh `otel_setup` import per test.

**Step 3: Verify tests work with patching**

The key is that `test_setup_opentelemetry` already patches all imports inside `otel_setup`:
- `patch("src.observability.otel_setup.OTLPSpanExporter", ...)` — this is the right approach
- No need to mock the entire opentelemetry tree in sys.modules

**Step 4: Run test with timeout**

Run: `timeout 30 uv run pytest tests/unit/test_otel_setup.py -v`
Expected: PASS in <10 seconds

**Step 3: Commit**

```bash
git add tests/unit/test_otel_setup.py
git commit -m "fix(test): use fixture for fresh OTEL state per test"
```

---

## Task 4: Expand Module Cleanup in test_main.py

**Files:**
- Modify: `tests/unit/test_main.py:17-32`

**Step 1: Expand cleanup_modules fixture**

Replace lines 17-32:

```python
    @pytest.fixture(autouse=True)
    def cleanup_modules(self):
        """Clear module cache before and after each test.

        Clears all telegram_bot and src.observability modules to ensure
        fresh imports and prevent state pollution between tests.
        """
        prefixes = (
            "telegram_bot.main",
            "telegram_bot.bot",
            "telegram_bot.config",
            "telegram_bot.logging_config",
            "telegram_bot.services",
            "src.observability",
        )

        def _clear():
            for key in list(sys.modules.keys()):
                if key.startswith(prefixes):
                    sys.modules.pop(key, None)

        _clear()
        yield
        _clear()
```

**Step 2: Run test**

Run: `timeout 30 uv run pytest tests/unit/test_main.py -v`
Expected: PASS

**Step 3: Commit**

```bash
git add tests/unit/test_main.py
git commit -m "fix(test): expand module cleanup in test_main.py"
```

---

## Task 5: Fix bot_handler Fixture and Add Mock Verification

**Files:**
- Modify: `tests/unit/test_bot_scores.py:38-62` (bot_handler fixture)
- Modify: `tests/unit/test_bot_scores.py:86-107` (test_scores_query_type method)

**Root cause:** `query_type=1.0` instead of `2.0` likely means `classify_query` was NOT called
(exception before it), causing default SIMPLE value. The fixture's BotConfig may be missing
fields that `handle_query` accesses before `classify_query`.

**Step 1: Fix bot_handler fixture with complete BotConfig**

Replace lines 38-62 (bot_handler fixture) - add all fields used by handle_query before classify_query:

```python
    @pytest.fixture
    def bot_handler(self):
        """Create PropertyBot handler with mocked services."""
        from telegram_bot.bot import PropertyBot
        from telegram_bot.config import BotConfig
        from telegram_bot.services import QueryType

        handler = PropertyBot.__new__(PropertyBot)
        # BotConfig with ALL fields that handle_query accesses before classify_query
        handler.config = BotConfig(
            telegram_token="test",
            voyage_api_key="test",
            llm_api_key="test",
            llm_model="test-model",
            cesc_enabled=False,
            # Fields used for context_fingerprint / cache key before classify_query:
            voyage_model_queries="voyage-3-lite",
            voyage_model_rerank="rerank-2",
            qdrant_collection="test-collection",
            qdrant_url="http://localhost:6333",
            redis_url="redis://localhost:6379",
        )
        handler._cache_initialized = True

        handler.cache_service = MagicMock()
        handler.cache_service.initialize = AsyncMock()
        handler.cache_service.get_cached_embedding = AsyncMock(return_value=[0.1] * 1024)
        handler.cache_service.check_semantic_cache = AsyncMock(return_value="Cached answer")
        handler.cache_service.log_metrics = MagicMock()

        handler._test_query_type = QueryType.COMPLEX
        return handler
```

**Step 2: Add assert_called verification to test**

Replace lines 86-107 (test_scores_query_type method):

```python
    @pytest.mark.asyncio
    async def test_scores_query_type(self, bot_handler, mock_message):
        """Should score query_type based on classification."""
        with (
            patch("telegram_bot.bot.get_client") as mock_get_client,
            patch("telegram_bot.bot.classify_query", autospec=True) as mock_classify_query,
        ):
            mock_langfuse = MagicMock()
            mock_get_client.return_value = mock_langfuse
            mock_classify_query.return_value = bot_handler._test_query_type

            await bot_handler.handle_query(mock_message)

            # Verify classify_query was actually called (catches early exception)
            mock_classify_query.assert_called_once()

            # Find the query_type score call
            score_calls = [
                c
                for c in mock_langfuse.score_current_trace.call_args_list
                if c.kwargs.get("name") == "query_type"
            ]
            assert len(score_calls) == 1, (
                f"Expected 1 query_type score, got {len(score_calls)}. "
                f"All scores: {[c.kwargs.get('name') for c in mock_langfuse.score_current_trace.call_args_list]}"
            )
            # COMPLEX = 2.0
            assert score_calls[0].kwargs["value"] == 2.0, (
                f"Expected query_type=2.0 (COMPLEX), got {score_calls[0].kwargs['value']}"
            )
```

**Step 3: Run test**

Run: `timeout 30 uv run pytest tests/unit/test_bot_scores.py::TestHandleQueryScores::test_scores_query_type -v`
Expected: PASS

**Step 3: Commit**

```bash
git add tests/unit/test_bot_scores.py
git commit -m "fix(test): add mock verification to test_scores_query_type"
```

---

## Task 6: Verify All 4 Target Tests Pass

**Files:**
- None (verification only)

**Step 1: Run all 4 originally failing tests**

Run:
```bash
timeout 60 uv run pytest \
  tests/unit/test_bot_scores.py::TestHandleQueryScores::test_scores_query_type \
  tests/unit/test_main.py::TestMainFunction::test_main_success_flow \
  tests/unit/test_main.py::TestMainFunction::test_main_no_telegram_token_exits_early \
  tests/unit/test_otel_setup.py::test_setup_opentelemetry \
  -v
```
Expected: 4 passed

**Step 2: Run full unit test suite**

Run: `timeout 180 uv run pytest tests/unit/ -v`
Expected: All tests pass

**Step 3: Run 5x stability check**

Run:
```bash
for i in {1..5}; do
  echo "=== Run $i ==="
  timeout 180 uv run pytest tests/unit/ -q || echo "FAILED on run $i"
done
```
Expected: All 5 runs pass

---

## Task 7: Final Commit and Cleanup

**Files:**
- None

**Step 1: Verify git status clean**

Run: `git status`
Expected: Working tree clean (all changes committed)

**Step 2: Delete design document (merged into this plan)**

Run: `rm docs/plans/2026-01-30-flaky-unit-tests-design.md`

**Step 3: Commit plan and cleanup**

```bash
git add -A
git commit -m "docs(plans): finalize flaky unit tests fix plan"
```

---

## Verification Checklist

- [ ] `tests/unit/conftest.py` exists with `isolate_otel_langfuse` autouse fixture
- [ ] `tests/conftest.py` uses `ModuleType` + `__spec__` for sys.modules mocks
- [ ] `tests/unit/test_otel_setup.py` uses fixture for fresh OTEL state
- [ ] `tests/unit/test_main.py` clears all related modules
- [ ] `tests/unit/test_bot_scores.py` verifies mock was called
- [ ] All 4 target tests pass
- [ ] Full unit suite passes 5x consecutively

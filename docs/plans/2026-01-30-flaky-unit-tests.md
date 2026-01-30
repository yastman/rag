# Fix Flaky Unit Tests Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Make 4 flaky unit tests pass reliably after uv migration by isolating OTEL/Langfuse initialization and fixing sys.modules mocking.

**Architecture:** Create unit-specific conftest.py with autouse fixture that blocks OTEL network calls via monkeypatch. Replace MagicMock sys.modules entries with proper ModuleType stubs that include `__spec__`. Expand module cleanup in test files.

**Tech Stack:** pytest, unittest.mock, monkeypatch, types.ModuleType, importlib.machinery.ModuleSpec

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

    # Patch OTEL exporters to prevent any initialization
    mock_exporter = MagicMock()
    mock_processor = MagicMock()

    patches = [
        patch(
            "opentelemetry.exporter.otlp.proto.grpc.trace_exporter.OTLPSpanExporter",
            mock_exporter,
        ),
        patch(
            "opentelemetry.exporter.otlp.proto.grpc.metric_exporter.OTLPMetricExporter",
            mock_exporter,
        ),
        patch("opentelemetry.sdk.trace.export.BatchSpanProcessor", mock_processor),
        patch(
            "opentelemetry.sdk.metrics.export.PeriodicExportingMetricReader",
            mock_processor,
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

**Step 1: Replace MagicMock with ModuleType stubs**

Replace lines 40-61 in `tests/conftest.py`:

```python
def _setup_mock_heavy_imports():
    """Mock slow-to-import ML libraries at startup.

    Uses proper ModuleType with __spec__ to avoid breaking importlib.util.find_spec().
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

Run: `uv run pytest tests/unit/test_settings.py -v --timeout=30`
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

**Step 1: Replace module-level mock with fixture**

Replace the entire file content:

```python
"""Unit tests for OTEL setup."""

import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


def _create_otel_mocks():
    """Create fresh OpenTelemetry mocks."""
    import importlib.machinery
    import types

    def _stub(name):
        mod = types.ModuleType(name)
        mod.__spec__ = importlib.machinery.ModuleSpec(name, loader=None)
        return mod

    mocks = {}
    otel_modules = [
        "opentelemetry",
        "opentelemetry.metrics",
        "opentelemetry.trace",
        "opentelemetry.exporter",
        "opentelemetry.exporter.otlp",
        "opentelemetry.exporter.otlp.proto",
        "opentelemetry.exporter.otlp.proto.grpc",
        "opentelemetry.exporter.otlp.proto.grpc.metric_exporter",
        "opentelemetry.exporter.otlp.proto.grpc.trace_exporter",
        "opentelemetry.instrumentation",
        "opentelemetry.instrumentation.aiohttp_client",
        "opentelemetry.instrumentation.redis",
        "opentelemetry.sdk",
        "opentelemetry.sdk.metrics",
        "opentelemetry.sdk.metrics.export",
        "opentelemetry.sdk.resources",
        "opentelemetry.sdk.trace",
        "opentelemetry.sdk.trace.export",
    ]
    for name in otel_modules:
        mock = _stub(name)
        # Add common attributes as MagicMock
        for attr in ["TracerProvider", "MeterProvider", "Resource", "BatchSpanProcessor"]:
            setattr(mock, attr, MagicMock())
        mocks[name] = mock

    return mocks


@pytest.fixture(autouse=True)
def fresh_otel_environment():
    """Ensure fresh OTEL module state for each test."""
    # Clear any cached otel_setup module
    modules_to_clear = [k for k in list(sys.modules.keys()) if "otel_setup" in k]
    for mod in modules_to_clear:
        sys.modules.pop(mod, None)

    # Install fresh mocks
    mocks = _create_otel_mocks()
    sys.modules.update(mocks)

    yield mocks

    # Cleanup
    for name in mocks:
        sys.modules.pop(name, None)
    for mod in modules_to_clear:
        sys.modules.pop(mod, None)


def test_setup_opentelemetry(fresh_otel_environment):
    """Test OpenTelemetry setup creates providers and configures exporters."""
    # Import fresh after mocks installed
    from src.observability.otel_setup import setup_opentelemetry

    with (
        patch("src.observability.otel_setup.trace") as mock_trace,
        patch("src.observability.otel_setup.metrics"),
        patch("src.observability.otel_setup.TracerProvider") as mock_tracer_provider,
        patch("src.observability.otel_setup.MeterProvider"),
        patch("src.observability.otel_setup.OTLPSpanExporter") as mock_span_exporter,
        patch("src.observability.otel_setup.OTLPMetricExporter"),
        patch("src.observability.otel_setup.BatchSpanProcessor"),
        patch("src.observability.otel_setup.PeriodicExportingMetricReader"),
        patch("src.observability.otel_setup.Resource"),
        patch("src.observability.otel_setup.AioHttpClientInstrumentor") as mock_aiohttp,
        patch("src.observability.otel_setup.RedisInstrumentor") as mock_redis,
    ):
        setup_opentelemetry("test-service")

        mock_tracer_provider.assert_called_once()
        mock_trace.set_tracer_provider.assert_called_once()
        mock_span_exporter.assert_called_with(endpoint="http://localhost:4317", insecure=True)
        mock_aiohttp.return_value.instrument.assert_called_once()
        mock_redis.return_value.instrument.assert_called_once()


@pytest.mark.asyncio
async def test_traced_pipeline_query(fresh_otel_environment):
    """Test TracedRAGPipeline query method."""
    from src.observability.otel_setup import TracedRAGPipeline

    pipeline = TracedRAGPipeline()

    with patch.object(pipeline, "_embed", new_callable=AsyncMock) as mock_embed:
        with patch.object(pipeline, "_search", new_callable=AsyncMock) as mock_search:
            with patch.object(pipeline, "_rerank", new_callable=AsyncMock) as mock_rerank:
                mock_embed.return_value = [0.1] * 10
                mock_search.return_value = [{"score": 0.9, "text": "result"}]
                mock_rerank.return_value = [{"score": 0.9, "text": "result"}]

                mock_span = MagicMock()
                mock_start_span = pipeline.tracer.start_as_current_span
                mock_start_span.return_value.__enter__.return_value = mock_span

                result = await pipeline.query("test query", top_k=5)

                assert len(result["results"]) == 1
                mock_embed.assert_called_once()
                mock_search.assert_called_once()
                pipeline.embedding_latency.record.assert_called()
                pipeline.search_latency.record.assert_called()
                pipeline.query_counter.add.assert_called()
```

**Step 2: Run test with timeout**

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

Run: `uv run pytest tests/unit/test_main.py -v --timeout=30`
Expected: PASS

**Step 3: Commit**

```bash
git add tests/unit/test_main.py
git commit -m "fix(test): expand module cleanup in test_main.py"
```

---

## Task 5: Add Mock Verification to test_bot_scores.py

**Files:**
- Modify: `tests/unit/test_bot_scores.py:86-107`

**Step 1: Add assert_called verification**

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

            # Verify classify_query was actually called (catches import path issues)
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

**Step 2: Run test**

Run: `uv run pytest tests/unit/test_bot_scores.py::TestHandleQueryScores::test_scores_query_type -v --timeout=30`
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
uv run pytest \
  tests/unit/test_bot_scores.py::TestHandleQueryScores::test_scores_query_type \
  tests/unit/test_main.py::TestMainFunction::test_main_success_flow \
  tests/unit/test_main.py::TestMainFunction::test_main_no_telegram_token_exits_early \
  tests/unit/test_otel_setup.py::test_setup_opentelemetry \
  -v --timeout=60
```
Expected: 4 passed

**Step 2: Run full unit test suite**

Run: `uv run pytest tests/unit/ -v --timeout=120`
Expected: All tests pass

**Step 3: Run 5x stability check**

Run:
```bash
for i in {1..5}; do
  echo "=== Run $i ==="
  uv run pytest tests/unit/ -q --timeout=120 || echo "FAILED on run $i"
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

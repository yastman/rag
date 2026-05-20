"""Unit test specific fixtures for isolation."""

import contextlib
import importlib.util
import sys
from unittest.mock import MagicMock, patch

import pytest


# =============================================================================
# MOCK HEAVY IMPORTS FOR UNIT TESTS
# =============================================================================
# These modules are slow to import due to model loading.  Mocks are installed
# in ``pytest_configure`` (earliest hook, before collection) and removed in
# ``pytest_unconfigure`` so that no MagicMock leaks into sys.modules after the
# session ends.
#
# Policy: NEVER assign to sys.modules at module level.  Use
# ``monkeypatch.setitem(sys.modules, ...)`` inside fixtures, or register mocks
# via ``pytest_configure`` for collection-time needs.  See
# ``.claude/rules/testing.md`` § "sys.modules hygiene".

_saved_modules: dict[str, object] = {}
_mocked_module_names: list[str] = []


def pytest_configure(config):
    """Install lightweight mocks for heavy ML libs before test collection."""
    # -- sentence_transformers / FlagEmbedding (slow model loading) ----------
    # Skip if: (a) real module already loaded, or (b) re-entry (already mocked).
    _already_mocked = "sentence_transformers" in _mocked_module_names
    _real_module_loaded = "sentence_transformers" in sys.modules and not isinstance(
        sys.modules["sentence_transformers"], MagicMock
    )
    if not _already_mocked and not _real_module_loaded:
        for mod_name in ("sentence_transformers", "FlagEmbedding"):
            _saved_modules[mod_name] = sys.modules.get(mod_name)

        mock_st = MagicMock()
        mock_st.CrossEncoder = MagicMock()
        mock_st.SentenceTransformer = MagicMock()
        sys.modules["sentence_transformers"] = mock_st
        _mocked_module_names.append("sentence_transformers")

        mock_flag = MagicMock()
        mock_flag.BGEM3FlagModel = MagicMock()
        sys.modules["FlagEmbedding"] = mock_flag
        _mocked_module_names.append("FlagEmbedding")

    # -- aiogram (optional Telegram runtime dep) -----------------------------
    try:
        if importlib.util.find_spec("aiogram") is None:
            raise ModuleNotFoundError("aiogram not installed")
    except ModuleNotFoundError:
        for mod_name in ("aiogram", "aiogram.filters", "aiogram.types"):
            _saved_modules[mod_name] = sys.modules.get(mod_name)

        mock_aiogram = MagicMock()
        mock_aiogram.Bot = MagicMock()
        mock_aiogram.Dispatcher = MagicMock()
        mock_aiogram.F = MagicMock()

        mock_filters = MagicMock()
        mock_filters.Command = MagicMock()

        mock_types = MagicMock()
        mock_types.Message = MagicMock()

        sys.modules["aiogram"] = mock_aiogram
        sys.modules["aiogram.filters"] = mock_filters
        sys.modules["aiogram.types"] = mock_types
        _mocked_module_names.extend(["aiogram", "aiogram.filters", "aiogram.types"])


def pytest_unconfigure(config):
    """Restore original modules after test session."""
    for mod_name in _mocked_module_names:
        original = _saved_modules.get(mod_name)
        if original is None:
            sys.modules.pop(mod_name, None)
        else:
            sys.modules[mod_name] = original  # type: ignore[assignment]
    _mocked_module_names.clear()
    _saved_modules.clear()


@pytest.fixture(autouse=True)
def mock_get_client(isolate_otel_langfuse):
    """Mock telegram_bot.bot.get_client for unit tests that already imported it.

    Autouse fixture — no test signature changes needed.
    Uses a shared MagicMock that tests can inspect via
    ``telegram_bot.bot.get_client`` if they need the reference.

    Lazy-patch behavior (#conftest-coverage-blocker fix): the fixture skips
    patching when ``telegram_bot.bot`` is NOT already in ``sys.modules``.

    Why: Eagerly resolving ``"telegram_bot.bot.get_client"`` triggers the
    full ``telegram_bot.bot`` import chain (langgraph, qdrant_client,
    numpy, …). Under ``pytest --cov`` the numpy C-extension
    (``numpy._core._multiarray_umath``) raises
    ``ImportError: cannot load module more than once per process`` because
    coverage's PEP 669 / pkgutil walk re-traverses the package tree. The
    failure surfaces as ``AttributeError: module 'telegram_bot' has no
    attribute 'bot'`` for every unit test in this directory.

    Tests that actually exercise ``telegram_bot.bot.get_client`` already
    import the module before this fixture runs (via ``from
    telegram_bot.bot import …`` at module top), so the lazy gate is
    invisible to them. Tests that never touch the bot module (the vast
    majority) no longer pay the cost of triggering the heavy import chain.

    ``isolate_otel_langfuse`` is requested first so OTEL/Langfuse env
    vars are set BEFORE we attempt the patch, in case a future bot import
    introduces OTEL initialization side effects.

    ``create=True`` keeps the patch safe even if a future refactor moves
    ``get_client`` out of ``telegram_bot.bot``.
    """
    if "telegram_bot.bot" not in sys.modules:
        # Bot module not loaded — no test in this run is exercising it,
        # so patching is unnecessary and would re-trigger the import chain.
        yield MagicMock()
        return

    mock = MagicMock()
    with patch("telegram_bot.bot.get_client", return_value=mock, create=True):
        yield mock


@pytest.fixture(autouse=True)
def isolate_otel_langfuse(monkeypatch):
    """Block OTEL/Langfuse network calls in unit tests.

    Uses env vars + targeted patches only.  Does NOT manipulate sys.modules
    because deleting/replacing modules breaks import references in other
    tests running in the same xdist worker process.
    """
    # Reset prompt_manager singleton so it uses fresh env vars each test
    from telegram_bot.integrations.prompt_manager import _reset_client

    _reset_client()

    # Force environment variables (override, not setdefault)
    monkeypatch.setenv("OTEL_SDK_DISABLED", "true")
    monkeypatch.setenv("OTEL_TRACES_EXPORTER", "none")
    monkeypatch.setenv("OTEL_METRICS_EXPORTER", "none")
    monkeypatch.setenv("OTEL_LOGS_EXPORTER", "none")
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "")
    monkeypatch.setenv("LANGFUSE_ENABLED", "false")
    monkeypatch.setenv("LANGFUSE_HOST", "")
    monkeypatch.setenv("LANGFUSE_TRACING_ENABLED", "false")
    monkeypatch.delenv("LANGFUSE_SECRET_KEY", raising=False)

    # Create no-op mocks
    mock_noop = MagicMock()

    # Patch at entry points to prevent any network initialization.
    # Do NOT patch "langfuse.Langfuse" — the patch() call itself imports
    # langfuse and can corrupt module state on stop().  Instead, patch the
    # higher-level wrappers that our code actually calls.
    patches = [
        # Langfuse — patch our wrapper, not the SDK class directly
        patch("telegram_bot.services.observability.get_client", lambda: mock_noop),
        # Fallback: patch low-level OTEL exporters
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
        with contextlib.suppress(Exception):
            p.start()

    yield

    for p in patches:
        with contextlib.suppress(Exception):
            p.stop()

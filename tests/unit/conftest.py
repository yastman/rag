"""Unit test specific fixtures for isolation."""

import contextlib
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
    _aiogram_real = "aiogram" in sys.modules and not isinstance(sys.modules["aiogram"], MagicMock)
    if not _aiogram_real:
        # Build proper State/StatesGroup stubs that support class-level State attrs.
        class _State:
            """Minimal aiogram.fsm.state.State stub."""

            def __init__(self) -> None:
                self._state: str = ""

            def __set_name__(self, owner: type, name: str) -> None:
                self._state = f"{owner.__name__}:{name}"

            def __repr__(self) -> str:
                return f"<State {self._state!r}>"

        class _StatesGroupMeta(type):
            """Metaclass that resolves State descriptors at class creation time."""

            def __new__(mcs, name: str, bases: tuple, namespace: dict) -> type:
                return super().__new__(mcs, name, bases, namespace)

        class _StatesGroup(metaclass=_StatesGroupMeta):
            """Minimal aiogram.fsm.state.StatesGroup stub."""

        _fsm_state_mod = MagicMock()
        _fsm_state_mod.State = _State
        _fsm_state_mod.StatesGroup = _StatesGroup

        _fsm_context_mod = MagicMock()
        _fsm_mod = MagicMock()
        _fsm_mod.state = _fsm_state_mod
        _fsm_mod.context = _fsm_context_mod

        # Real stubs needed for isinstance() checks in production code
        class _TelegramBadRequest(Exception):
            """Minimal TelegramBadRequest stub."""

            def __init__(self, method: object = None, message: str = "") -> None:
                super().__init__(message)
                self.message = message

        class _ExceptionTypeFilter:
            """Minimal ExceptionTypeFilter stub."""

            def __init__(self, *exception_types: type) -> None:
                self.exception_types = exception_types

        _aiogram_exceptions_mod = MagicMock()
        _aiogram_exceptions_mod.TelegramBadRequest = _TelegramBadRequest

        _aiogram_filters_mod = MagicMock()
        _aiogram_filters_mod.ExceptionTypeFilter = _ExceptionTypeFilter

        _aiogram_submodules = [
            "aiogram",
            "aiogram.dispatcher",
            "aiogram.dispatcher.flags",
            "aiogram.enums",
            "aiogram.filters.callback_data",
            "aiogram.types",
            "aiogram.utils",
            "aiogram.utils.callback_answer",
            "aiogram.utils.chat_action",
            "aiogram.utils.keyboard",
            "aiogram.utils.token",
        ]
        for mod_name in _aiogram_submodules:
            _saved_modules[mod_name] = sys.modules.get(mod_name)
            sys.modules[mod_name] = MagicMock()
        # Register modules with real stubs where isinstance() checks are needed
        for mod_name in ("aiogram.exceptions", "aiogram.filters"):
            _saved_modules[mod_name] = sys.modules.get(mod_name)
        sys.modules["aiogram.exceptions"] = _aiogram_exceptions_mod
        sys.modules["aiogram.filters"] = _aiogram_filters_mod
        _aiogram_submodules.extend(["aiogram.exceptions", "aiogram.filters"])
        # Register fsm submodules with proper stubs
        for mod_name in ("aiogram.fsm", "aiogram.fsm.context", "aiogram.fsm.state"):
            _saved_modules[mod_name] = sys.modules.get(mod_name)
        sys.modules["aiogram.fsm"] = _fsm_mod
        sys.modules["aiogram.fsm.context"] = _fsm_context_mod
        sys.modules["aiogram.fsm.state"] = _fsm_state_mod
        _aiogram_submodules.extend(["aiogram.fsm", "aiogram.fsm.context", "aiogram.fsm.state"])
        _mocked_module_names.extend(_aiogram_submodules)

    # -- aiogram_dialog (optional dialog framework dep) ----------------------
    _dialog_real = "aiogram_dialog" in sys.modules and not isinstance(
        sys.modules["aiogram_dialog"], MagicMock
    )
    if not _dialog_real:

        class _UnknownIntent(Exception):
            """Minimal UnknownIntent stub for isinstance() checks."""

        _dialog_exceptions_mod = MagicMock()
        _dialog_exceptions_mod.UnknownIntent = _UnknownIntent

        _dialog_submodules = [
            "aiogram_dialog",
            "aiogram_dialog.api",
            "aiogram_dialog.api.entities",
            "aiogram_dialog.api.entities.events",
            "aiogram_dialog.api.protocols",
            "aiogram_dialog.widgets",
            "aiogram_dialog.widgets.kbd",
            "aiogram_dialog.widgets.text",
        ]
        for mod_name in _dialog_submodules:
            _saved_modules[mod_name] = sys.modules.get(mod_name)
            sys.modules[mod_name] = MagicMock()
        # Register exceptions module with real UnknownIntent stub
        _saved_modules["aiogram_dialog.api.exceptions"] = sys.modules.get(
            "aiogram_dialog.api.exceptions"
        )
        sys.modules["aiogram_dialog.api.exceptions"] = _dialog_exceptions_mod
        _dialog_submodules.append("aiogram_dialog.api.exceptions")
        _mocked_module_names.extend(_dialog_submodules)

    # -- langgraph (removed dep — tests use Runtime as a context container) --
    _langgraph_real = "langgraph" in sys.modules and not isinstance(
        sys.modules["langgraph"], MagicMock
    )
    if not _langgraph_real:
        _langgraph_submodules = [
            "langgraph",
            "langgraph.runtime",
            "langgraph.types",
            "langgraph.checkpoint",
            "langgraph.checkpoint.base",
            "langgraph.checkpoint.memory",
            "langgraph.checkpoint.redis",
            "langgraph.checkpoint.redis.aio",
            "langgraph.checkpoint.serde",
            "langgraph.checkpoint.serde.jsonplus",
        ]
        for mod_name in _langgraph_submodules:
            _saved_modules[mod_name] = sys.modules.get(mod_name)
            sys.modules[mod_name] = MagicMock()
        _mocked_module_names.extend(_langgraph_submodules)

    # -- asyncpg (optional postgres dep) ------------------------------------
    _asyncpg_real = "asyncpg" in sys.modules and not isinstance(sys.modules["asyncpg"], MagicMock)
    if not _asyncpg_real:
        _saved_modules["asyncpg"] = sys.modules.get("asyncpg")
        sys.modules["asyncpg"] = MagicMock()
        _mocked_module_names.append("asyncpg")

    # -- anthropic (optional Claude dep) ------------------------------------
    _anthropic_real = "anthropic" in sys.modules and not isinstance(
        sys.modules["anthropic"], MagicMock
    )
    if not _anthropic_real:
        _saved_modules["anthropic"] = sys.modules.get("anthropic")
        sys.modules["anthropic"] = MagicMock()
        _mocked_module_names.append("anthropic")

    # -- fluent_compiler / fluentogram (optional i18n dep) ------------------
    _fluent_real = "fluent_compiler" in sys.modules and not isinstance(
        sys.modules["fluent_compiler"], MagicMock
    )
    if not _fluent_real:
        _fluent_mods = [
            "fluent_compiler",
            "fluent_compiler.bundle",
            "fluentogram",
        ]
        for mod_name in _fluent_mods:
            _saved_modules[mod_name] = sys.modules.get(mod_name)
            sys.modules[mod_name] = MagicMock()
        _mocked_module_names.extend(_fluent_mods)

    # -- cachetools (optional caching dep) ----------------------------------
    _cachetools_real = "cachetools" in sys.modules and not isinstance(
        sys.modules["cachetools"], MagicMock
    )
    if not _cachetools_real:
        _saved_modules["cachetools"] = sys.modules.get("cachetools")
        sys.modules["cachetools"] = MagicMock()
        _mocked_module_names.append("cachetools")


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
    # Disable the uvicorn-based metrics server in unit tests (#2139).
    # bot.start() would otherwise try to bind a real listening port
    # (TELEGRAM_BOT_METRICS_PORT / 9092 — see #2190), causing SystemExit
    # when the port is unavailable (e.g. in CI with concurrent workers).
    monkeypatch.setenv("TELEGRAM_BOT_METRICS_ENABLED", "0")

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
        # #1601: narrow suppression — only swallow expected optional-import
        # failures (the patched module/class is intentionally missing in some
        # envs) and lazy-attribute resolution misses (telegram_bot.services
        # raises AttributeError from its lazy import handler when the target
        # symbol is provided by a sibling package, not the package itself).
        # Anything else (TypeError, ValueError, etc.) is a real isolation
        # bug we want to surface.
        with contextlib.suppress(ModuleNotFoundError, ImportError, AttributeError):
            p.start()

    yield

    for p in patches:
        # RuntimeError is raised by mock.patch when the start failed
        # earlier and stop has no original to restore. AttributeError
        # mirrors the start-time guard above.
        with contextlib.suppress(ModuleNotFoundError, ImportError, AttributeError, RuntimeError):
            p.stop()

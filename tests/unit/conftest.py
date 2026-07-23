"""Unit test specific fixtures for isolation."""

import contextlib
import importlib
import sys
from unittest.mock import MagicMock


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
    _aiogram_real = False
    try:
        import aiogram  # noqa: F401 — use real module if installed

        _aiogram_real = True
    except ImportError:
        _aiogram_real = "aiogram" in sys.modules and not isinstance(
            sys.modules["aiogram"], MagicMock
        )
    if not _aiogram_real:
        # Build proper State/StatesGroup stubs that support class-level State attrs.
        class _State:
            """Minimal aiogram.fsm.state.State stub."""

            def __init__(self) -> None:
                self._state: str = ""

            def __set_name__(self, owner: type, name: str) -> None:
                self._state = f"{owner.__name__}:{name}"

            @property
            def state(self) -> str:
                return self._state

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

        class _FSMContext:
            """Minimal FSMContext stub for isinstance() checks."""

        _fsm_context_mod = MagicMock()
        _fsm_context_mod.FSMContext = _FSMContext
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

        class _InaccessibleMessage:
            """Minimal InaccessibleMessage stub for isinstance() checks."""

        _aiogram_exceptions_mod = MagicMock()
        _aiogram_exceptions_mod.TelegramBadRequest = _TelegramBadRequest

        _aiogram_types_mod = MagicMock()
        _aiogram_types_mod.InaccessibleMessage = _InaccessibleMessage

        _aiogram_filters_mod = MagicMock()
        _aiogram_filters_mod.ExceptionTypeFilter = _ExceptionTypeFilter

        _aiogram_submodules = [
            "aiogram",
            "aiogram.dispatcher",
            "aiogram.dispatcher.flags",
            "aiogram.enums",
            "aiogram.filters.callback_data",
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
        for mod_name in ("aiogram.exceptions", "aiogram.filters", "aiogram.types"):
            _saved_modules[mod_name] = sys.modules.get(mod_name)
        sys.modules["aiogram.exceptions"] = _aiogram_exceptions_mod
        sys.modules["aiogram.filters"] = _aiogram_filters_mod
        sys.modules["aiogram.types"] = _aiogram_types_mod
        _aiogram_submodules.extend(["aiogram.exceptions", "aiogram.filters", "aiogram.types"])
        # Register fsm submodules with proper stubs
        for mod_name in ("aiogram.fsm", "aiogram.fsm.context", "aiogram.fsm.state"):
            _saved_modules[mod_name] = sys.modules.get(mod_name)
        sys.modules["aiogram.fsm"] = _fsm_mod
        sys.modules["aiogram.fsm.context"] = _fsm_context_mod
        sys.modules["aiogram.fsm.state"] = _fsm_state_mod
        _aiogram_submodules.extend(["aiogram.fsm", "aiogram.fsm.context", "aiogram.fsm.state"])
        _mocked_module_names.extend(_aiogram_submodules)
    # -- aiogram_dialog (optional dialog framework dep) ----------------------
    _dialog_real = False
    try:
        import aiogram_dialog  # noqa: F401 — use real module if installed

        _dialog_real = True
    except ImportError:
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
            "aiogram_dialog.utils",
            "aiogram_dialog.widgets",
            "aiogram_dialog.widgets.input",
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
    _langgraph_real = False
    try:
        import langgraph  # noqa: F401 — use real module if installed

        _langgraph_real = True
    except ImportError:
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
        _asyncpg_mock = MagicMock()

        class _InvalidCatalogNameError(Exception):
            """Minimal asyncpg.InvalidCatalogNameError stub for isinstance() checks."""

        _asyncpg_mock.InvalidCatalogNameError = _InvalidCatalogNameError
        sys.modules["asyncpg"] = _asyncpg_mock
        _mocked_module_names.append("asyncpg")

    # -- anthropic (optional Claude dep) ------------------------------------
    _anthropic_real = "anthropic" in sys.modules and not isinstance(
        sys.modules["anthropic"], MagicMock
    )
    if not _anthropic_real:
        _saved_modules["anthropic"] = sys.modules.get("anthropic")
        sys.modules["anthropic"] = MagicMock()
        _mocked_module_names.append("anthropic")

    # Force real import so the check below doesn't mock an installed dep.
    with contextlib.suppress(ImportError):
        import fluent_compiler  # noqa: F401
    with contextlib.suppress(ImportError):
        import fluentogram  # noqa: F401
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
    # -- langchain_core detection without static import ----------------------
    # Use importlib.util.find_spec to check availability instead of a direct
    # static import, avoiding unnecessary module loading in the core gate.
    _langchain_core_spec = importlib.util.find_spec("langchain_core")
    _langchain_core_real = (
        "langchain_core" in sys.modules and not isinstance(sys.modules["langchain_core"], MagicMock)
    ) or _langchain_core_spec is not None
    if _langchain_core_real and "langchain_core" not in sys.modules:
        import langchain_core  # noqa: F401 — register in sys.modules so CRM tools can import it

        _saved_modules["langchain_core"] = None
    # -- langchain_core (optional archived CRM dep) -------------------------
    if not _langchain_core_real:
        _lc_mods = [
            "langchain_core",
            "langchain_core.runnables",
            "langchain_core.tools",
            "langchain_core.messages",
            "langchain_core.callbacks",
        ]
        for mod_name in _lc_mods:
            _saved_modules[mod_name] = sys.modules.get(mod_name)
            sys.modules[mod_name] = MagicMock()
        _mocked_module_names.extend(_lc_mods)


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

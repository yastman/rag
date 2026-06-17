# tests/integration/conftest.py
"""Integration test configuration."""

import sys
from unittest.mock import MagicMock


_saved: dict[str, object] = {}
_mocked: list[str] = []


def pytest_configure(config):
    """Mock optional heavy deps for integration test collection."""
    _aiogram_real = "aiogram" in sys.modules and not isinstance(sys.modules["aiogram"], MagicMock)
    if not _aiogram_real:
        _mods = [
            "aiogram",
            "aiogram.dispatcher",
            "aiogram.dispatcher.flags",
            "aiogram.enums",
            "aiogram.exceptions",
            "aiogram.filters",
            "aiogram.filters.callback_data",
            "aiogram.fsm",
            "aiogram.fsm.context",
            "aiogram.fsm.state",
            "aiogram.types",
            "aiogram.utils",
            "aiogram.utils.callback_answer",
            "aiogram.utils.chat_action",
            "aiogram.utils.keyboard",
            "aiogram.utils.token",
        ]
        for mod in _mods:
            _saved[mod] = sys.modules.get(mod)
            sys.modules[mod] = MagicMock()
        _mocked.extend(_mods)

    _dialog_real = "aiogram_dialog" in sys.modules and not isinstance(
        sys.modules["aiogram_dialog"], MagicMock
    )
    if not _dialog_real:
        _dialog_mods = [
            "aiogram_dialog",
            "aiogram_dialog.api",
            "aiogram_dialog.api.entities",
            "aiogram_dialog.api.entities.events",
            "aiogram_dialog.api.exceptions",
            "aiogram_dialog.api.protocols",
            "aiogram_dialog.widgets",
            "aiogram_dialog.widgets.kbd",
            "aiogram_dialog.widgets.text",
        ]
        for mod in _dialog_mods:
            _saved[mod] = sys.modules.get(mod)
            sys.modules[mod] = MagicMock()
        _mocked.extend(_dialog_mods)

    for _opt_mod in ("fluent_compiler", "fluent_compiler.bundle", "fluentogram", "cachetools"):
        if _opt_mod not in sys.modules or isinstance(sys.modules[_opt_mod], MagicMock):
            _saved[_opt_mod] = sys.modules.get(_opt_mod)
            sys.modules[_opt_mod] = MagicMock()
            _mocked.append(_opt_mod)


def pytest_unconfigure(config):
    """Restore mocked modules."""
    for mod in _mocked:
        orig = _saved.get(mod)
        if orig is None:
            sys.modules.pop(mod, None)
        else:
            sys.modules[mod] = orig  # type: ignore[assignment]
    _mocked.clear()
    _saved.clear()

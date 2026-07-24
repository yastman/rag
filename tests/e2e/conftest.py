# tests/e2e/conftest.py
"""E2E test configuration.

Integration conftest installs aiogram MagicMocks at pytest_configure whenever
the package is not already in sys.modules — even when aiogram is installed.
Those stubs are present before collection, so e2e modules that bind
CallbackData / StatesGroup / Message at import time (FeedbackCB, DemoSG,
DemoCB, …) would otherwise capture polluted MagicMocks.

Restore real packages in pytest_sessionstart (after every conftest configure,
before collection). Lean venvs without aiogram keep the absence so
importorskip still skips.
"""

from __future__ import annotations

import contextlib
import sys
from unittest.mock import MagicMock

import pytest


# Import-time bindings that must not keep MagicMock CallbackData/StatesGroup.
_TB_RELOAD_PREFIXES = (
    "telegram_bot.callback_data",
    "telegram_bot.feedback",
    "telegram_bot.dialogs",
    "telegram_bot.handlers",
    "telegram_bot.keyboards",
    "telegram_bot.pipelines",
    "telegram_bot.services.forum_bridge",
    "telegram_bot.middlewares",
)


def _is_aiogram_name(name: str) -> bool:
    return (
        name == "aiogram"
        or name == "aiogram_dialog"
        or name.startswith(("aiogram.", "aiogram_dialog."))
    )


def _purge_mocked_aiogram() -> None:
    for name, mod in list(sys.modules.items()):
        if _is_aiogram_name(name) and isinstance(mod, MagicMock):
            del sys.modules[name]


def _purge_contaminated_telegram_bot() -> None:
    for name in list(sys.modules):
        for prefix in _TB_RELOAD_PREFIXES:
            if name == prefix or name.startswith(prefix + "."):
                del sys.modules[name]
                break


def _restore_real_aiogram_stack() -> None:
    """Drop MagicMock aiogram stubs when the real package is importable."""
    mocked = any(
        isinstance(mod, MagicMock) for name, mod in sys.modules.items() if _is_aiogram_name(name)
    )
    real = "aiogram" in sys.modules and not isinstance(sys.modules["aiogram"], MagicMock)
    if real and not mocked:
        return

    _purge_mocked_aiogram()
    try:
        import aiogram
        import aiogram.filters.callback_data
        import aiogram.fsm.state
        import aiogram.types
        import aiogram.utils.keyboard  # noqa: F401
    except ImportError:
        # Lean venv without aiogram — leave absence for importorskip paths.
        return

    with contextlib.suppress(ImportError):
        import aiogram_dialog  # noqa: F401

    _purge_contaminated_telegram_bot()


def pytest_sessionstart(session) -> None:
    """After all conftest configures, before collection imports e2e modules."""
    _restore_real_aiogram_stack()


@pytest.fixture(autouse=True)
def _ensure_real_aiogram_for_e2e() -> None:
    """Re-assert real aiogram before each e2e test (FeedbackCB / DemoSG / Message)."""
    _restore_real_aiogram_stack()

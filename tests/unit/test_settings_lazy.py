"""Tests for lazy settings initialization."""

import os
import sys
from unittest.mock import patch

import pytest


def test_import_settings_module_without_api_keys(monkeypatch: pytest.MonkeyPatch):
    """Importing settings module should not require API keys."""
    # Clear any cached settings using monkeypatch (auto-restored after test)
    for mod in list(sys.modules.keys()):
        if mod.startswith("src.config"):
            monkeypatch.delitem(sys.modules, mod, raising=False)

    # Import without API keys should not raise
    with patch.dict(
        os.environ,
        {
            "API_PROVIDER": "claude",
            "ANTHROPIC_API_KEY": "",
            "OPENAI_API_KEY": "",
            "GROQ_API_KEY": "",
        },
        clear=False,
    ):
        # This should NOT raise ValueError
        from src.config import settings as settings_module

        # get_settings() should be available
        assert hasattr(settings_module, "get_settings")


def test_get_settings_validates_on_call(monkeypatch: pytest.MonkeyPatch):
    """get_settings() should validate API keys when called."""
    # Clear any cached settings using monkeypatch (auto-restored after test)
    for mod in list(sys.modules.keys()):
        if mod.startswith("src.config"):
            monkeypatch.delitem(sys.modules, mod, raising=False)

    with patch.dict(
        os.environ,
        {
            "API_PROVIDER": "claude",
            "ANTHROPIC_API_KEY": "",
        },
        clear=False,
    ):
        from src.config.settings import get_settings

        with pytest.raises(ValueError, match="ANTHROPIC_API_KEY"):
            get_settings()

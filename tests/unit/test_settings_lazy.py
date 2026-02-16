"""Tests for lazy settings initialization."""

import os
import sys
from unittest.mock import patch


def test_import_settings_module_without_api_keys():
    """Importing settings module should not require API keys."""
    # Clear any cached settings
    for mod in list(sys.modules.keys()):
        if mod.startswith("src.config"):
            del sys.modules[mod]

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


def test_get_settings_validates_on_call():
    """get_settings() should validate API keys when called."""
    for mod in list(sys.modules.keys()):
        if mod.startswith("src.config"):
            del sys.modules[mod]

    with patch.dict(
        os.environ,
        {
            "API_PROVIDER": "claude",
            "ANTHROPIC_API_KEY": "",
        },
        clear=False,
    ):
        import pytest

        from src.config.settings import get_settings

        with pytest.raises(ValueError, match="ANTHROPIC_API_KEY"):
            get_settings()

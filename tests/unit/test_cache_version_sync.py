"""Test cache version synchronization across validation scripts.

Issue #224: Fallback cache version in validate_traces.py must match
actual CACHE_VERSION from telegram_bot.integrations.cache to prevent
version drift when imports fail.
"""

import pytest


def test_flush_fallback_uses_current_cache_version():
    """Fallback cache version must match actual CACHE_VERSION."""
    # Mock import failure to trigger fallback
    import builtins

    from scripts.validate_traces import _get_cache_version
    from telegram_bot.integrations.cache import CACHE_VERSION

    original_import = builtins.__import__

    def mock_import_with_failure(name, *args, **kwargs):
        if name == "telegram_bot.integrations.cache":
            raise ImportError("Simulated import failure")
        return original_import(name, *args, **kwargs)

    with pytest.MonkeyPatch.context() as m:
        m.setattr(builtins, "__import__", mock_import_with_failure)

        # When import fails, fallback should return current version
        fallback_version = _get_cache_version()

    # Fallback must match actual CACHE_VERSION (currently v4, NOT v3)
    assert fallback_version == CACHE_VERSION, (
        f"Fallback returns {fallback_version} but CACHE_VERSION is {CACHE_VERSION}. "
        f"Update fallback in scripts/validate_traces.py:247"
    )

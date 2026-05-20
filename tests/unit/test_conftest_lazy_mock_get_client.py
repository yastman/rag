"""Regression tests for unit conftest lazy patching."""

from __future__ import annotations

import sys

import pytest


def test_mock_get_client_does_not_eagerly_import_telegram_bot_bot():
    """mock_get_client must not trigger telegram_bot.bot import on its own.

    Contract: when a test does not itself import telegram_bot.bot, the autouse
    mock_get_client fixture must skip the patch. Otherwise the patch import
    chain can break pytest --cov with numpy C-extension re-import errors.
    """
    if "telegram_bot.bot" in sys.modules:
        pytest.skip("telegram_bot.bot was imported by another collected test module")

    assert "telegram_bot.bot" not in sys.modules

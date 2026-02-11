"""Tests for /call command."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from telegram_bot.config import BotConfig


@pytest.fixture
def bot_config():
    """Create test config with LiveKit fields."""
    return BotConfig(
        telegram_token="test:token",
        admin_ids=[111],
        livekit_url="ws://localhost:7880",
        livekit_api_key="devkey",
        livekit_api_secret="secret",
        sip_trunk_id="ST_test123",
    )


@pytest.fixture
def message():
    msg = MagicMock()
    msg.from_user = MagicMock()
    msg.from_user.id = 111  # admin
    msg.chat = MagicMock()
    msg.chat.id = 999
    msg.answer = AsyncMock()
    return msg


def _make_bot(bot_config: BotConfig) -> MagicMock:
    """Create a minimal PropertyBot mock with config and _is_admin."""
    from telegram_bot.bot import PropertyBot

    bot = MagicMock(spec=PropertyBot)
    bot.config = bot_config
    bot._is_admin = PropertyBot._is_admin.__get__(bot, PropertyBot)
    bot.cmd_call = PropertyBot.cmd_call.__get__(bot, PropertyBot)
    return bot


def test_call_requires_admin(bot_config, message):
    """Non-admin users should be rejected."""
    bot = _make_bot(bot_config)
    message.from_user.id = 999  # not admin
    asyncio.run(bot.cmd_call(message))
    message.answer.assert_called_once()
    assert "администратор" in message.answer.call_args[0][0].lower()


def test_call_requires_phone(bot_config, message):
    """Command without phone should show usage."""
    bot = _make_bot(bot_config)
    message.text = "/call"
    asyncio.run(bot.cmd_call(message))
    message.answer.assert_called_once()
    assert "380" in message.answer.call_args[0][0]


def test_call_requires_livekit_config(bot_config, message):
    """Missing LiveKit config should show error."""
    bot_config.livekit_url = ""
    bot_config.sip_trunk_id = ""
    bot = _make_bot(bot_config)
    message.text = "/call +380501234567"
    asyncio.run(bot.cmd_call(message))
    message.answer.assert_called_once()
    assert "Voice service" in message.answer.call_args[0][0]

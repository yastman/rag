"""Entry-point behavior with real SDK errors and explicit local collaborators."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from aiogram.exceptions import TelegramNetworkError
from aiogram.methods import GetMe

from src.runtime.integrations.polling_lock import PollingLockBusy
from telegram_bot import main as main_module


@pytest.fixture
async def runtime(monkeypatch):
    loop = asyncio.get_running_loop()
    previous_handler = loop.get_exception_handler()
    config = SimpleNamespace(telegram_token="test-token", llm_api_key="test-key")
    bot = SimpleNamespace(start=AsyncMock(), stop=AsyncMock())
    constructor = MagicMock(return_value=bot)
    setup_logging = MagicMock()
    monkeypatch.setattr(main_module, "BotConfig", lambda: config)
    monkeypatch.setattr(main_module, "PropertyBot", constructor)
    monkeypatch.setattr(main_module, "setup_logging", setup_logging)
    monkeypatch.setattr(main_module, "_MAX_START_ATTEMPTS", 3)
    monkeypatch.setattr(main_module, "_START_WAIT_MIN", 0)
    monkeypatch.setattr(main_module, "_START_WAIT_MAX", 0)
    try:
        yield SimpleNamespace(
            config=config, bot=bot, constructor=constructor, logging=setup_logging
        )
    finally:
        loop.set_exception_handler(previous_handler)


async def test_main_success_flow(runtime):
    await main_module.main()
    runtime.logging.assert_called_once()
    runtime.constructor.assert_called_once_with(runtime.config)
    runtime.bot.start.assert_awaited_once()
    runtime.bot.stop.assert_awaited_once()


async def test_main_no_telegram_token_exits_early(runtime, caplog):
    runtime.config.telegram_token = ""
    await main_module.main()
    runtime.constructor.assert_not_called()
    assert "TELEGRAM_BOT_TOKEN not set" in caplog.text


async def test_main_retries_on_temporary_startup_error(runtime):
    error = TelegramNetworkError(method=GetMe(), message="temporary network failure")
    runtime.bot.start.side_effect = [error, None]
    await main_module.main()
    assert runtime.bot.start.await_count == 2
    runtime.bot.stop.assert_awaited_once()


async def test_main_stops_after_retry_budget(runtime):
    error = TelegramNetworkError(method=GetMe(), message="persistent network failure")
    runtime.bot.start.side_effect = error
    with pytest.raises(TelegramNetworkError) as raised:
        await main_module.main()
    assert raised.value is error
    assert runtime.bot.start.await_count == 3
    runtime.bot.stop.assert_awaited_once()


async def test_main_propagates_non_retryable_startup_error(runtime):
    error = RuntimeError("boom")
    runtime.bot.start.side_effect = error
    with pytest.raises(RuntimeError) as raised:
        await main_module.main()
    assert raised.value is error
    runtime.bot.start.assert_awaited_once()
    runtime.bot.stop.assert_awaited_once()


async def test_main_handles_polling_lock_busy_without_traceback(runtime, caplog):
    error = PollingLockBusy("another instance owns polling")
    runtime.bot.start.side_effect = error
    with pytest.raises(SystemExit) as raised:
        await main_module.main()
    assert raised.value.code == 2
    runtime.bot.start.assert_awaited_once()
    runtime.bot.stop.assert_awaited_once()
    record = next(record for record in caplog.records if "Polling lock is busy" in record.message)
    assert str(error) in record.message
    assert record.exc_info is None

"""Unit tests for telegram_bot/main.py.

Tests use sys.modules mocking to avoid slow imports (aiogram, services).
Note: Due to module caching complexities, only basic flow tests are included.
For integration testing of main(), use the E2E test suite.
"""

import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class TestMainFunction:
    """Test main() function logic."""

    @pytest.fixture(autouse=True)
    def cleanup_modules(self):
        """Clear module cache before and after each test.

        Clears all telegram_bot and src.observability modules to ensure
        fresh imports and prevent state pollution between tests.
        """
        prefixes = (
            "telegram_bot",
            "src.observability",
        )

        def _clear():
            for key in list(sys.modules.keys()):
                if key.startswith(prefixes):
                    sys.modules.pop(key, None)

        _clear()
        yield
        _clear()
    async def test_main_success_flow(self):
        """Test successful bot startup and shutdown."""
        mock_property_bot_instance = AsyncMock()
        mock_property_bot = MagicMock(return_value=mock_property_bot_instance)
        mock_bot_config = MagicMock()
        mock_setup_logging = MagicMock()

        mock_bot_mod = MagicMock()
        mock_bot_mod.PropertyBot = mock_property_bot

        mock_config_mod = MagicMock()
        mock_config_mod.BotConfig = mock_bot_config

        mock_logging_config_mod = MagicMock()
        mock_logging_config_mod.setup_logging = mock_setup_logging

        mock_config_instance = MagicMock()
        mock_config_instance.telegram_token = "test-token"
        mock_config_instance.llm_api_key = "test-api-key"
        mock_bot_config.return_value = mock_config_instance

        with patch.dict(
            sys.modules,
            {
                "telegram_bot.bot": mock_bot_mod,
                "telegram_bot.config": mock_config_mod,
                "telegram_bot.logging_config": mock_logging_config_mod,
            },
        ):
            from telegram_bot import main as main_module

            await main_module.main()

            mock_setup_logging.assert_called_once()
            mock_property_bot_instance.start.assert_awaited_once()
            mock_property_bot_instance.stop.assert_awaited_once()
            mock_property_bot.assert_called_once_with(mock_config_instance)
    async def test_main_no_telegram_token_exits_early(self):
        """Test main exits early when no telegram token."""
        mock_property_bot = MagicMock()
        mock_bot_config = MagicMock()
        mock_setup_logging = MagicMock()

        mock_bot_mod = MagicMock()
        mock_bot_mod.PropertyBot = mock_property_bot

        mock_config_mod = MagicMock()
        mock_config_mod.BotConfig = mock_bot_config

        mock_logging_config_mod = MagicMock()
        mock_logging_config_mod.setup_logging = mock_setup_logging

        mock_config_instance = MagicMock()
        mock_config_instance.telegram_token = ""  # Empty token
        mock_config_instance.llm_api_key = "test-api-key"
        mock_bot_config.return_value = mock_config_instance

        with patch.dict(
            sys.modules,
            {
                "telegram_bot.bot": mock_bot_mod,
                "telegram_bot.config": mock_config_mod,
                "telegram_bot.logging_config": mock_logging_config_mod,
            },
        ):
            from telegram_bot import main as main_module

            await main_module.main()

            # Bot should not be created when token is missing
            mock_property_bot.assert_not_called()
    async def test_main_retries_on_temporary_startup_error(self):
        """Temporary network errors should trigger retry with sleep."""
        mock_property_bot_instance = AsyncMock()
        mock_property_bot_instance.start = AsyncMock(side_effect=[OSError("dns failure"), None])
        mock_property_bot = MagicMock(return_value=mock_property_bot_instance)
        mock_bot_config = MagicMock()
        mock_setup_logging = MagicMock()

        mock_bot_mod = MagicMock()
        mock_bot_mod.PropertyBot = mock_property_bot

        mock_config_mod = MagicMock()
        mock_config_mod.BotConfig = mock_bot_config

        mock_logging_config_mod = MagicMock()
        mock_logging_config_mod.setup_logging = mock_setup_logging

        mock_config_instance = MagicMock()
        mock_config_instance.telegram_token = "test-token"
        mock_config_instance.llm_api_key = "test-api-key"
        mock_bot_config.return_value = mock_config_instance

        with patch.dict(
            sys.modules,
            {
                "telegram_bot.bot": mock_bot_mod,
                "telegram_bot.config": mock_config_mod,
                "telegram_bot.logging_config": mock_logging_config_mod,
            },
        ):
            from telegram_bot import main as main_module

            with patch.object(main_module.asyncio, "sleep", new=AsyncMock()) as mock_sleep:
                await main_module.main()

            assert mock_property_bot_instance.start.await_count == 2
            mock_sleep.assert_awaited_once()
            mock_property_bot_instance.stop.assert_awaited_once()
    async def test_main_propagates_non_retryable_startup_error(self):
        """Unexpected startup errors should not be retried indefinitely."""
        mock_property_bot_instance = AsyncMock()
        mock_property_bot_instance.start = AsyncMock(side_effect=RuntimeError("boom"))
        mock_property_bot = MagicMock(return_value=mock_property_bot_instance)
        mock_bot_config = MagicMock()
        mock_setup_logging = MagicMock()

        mock_bot_mod = MagicMock()
        mock_bot_mod.PropertyBot = mock_property_bot

        mock_config_mod = MagicMock()
        mock_config_mod.BotConfig = mock_bot_config

        mock_logging_config_mod = MagicMock()
        mock_logging_config_mod.setup_logging = mock_setup_logging

        mock_config_instance = MagicMock()
        mock_config_instance.telegram_token = "test-token"
        mock_config_instance.llm_api_key = "test-api-key"
        mock_bot_config.return_value = mock_config_instance

        with patch.dict(
            sys.modules,
            {
                "telegram_bot.bot": mock_bot_mod,
                "telegram_bot.config": mock_config_mod,
                "telegram_bot.logging_config": mock_logging_config_mod,
            },
        ):
            from telegram_bot import main as main_module

            with pytest.raises(RuntimeError, match="boom"):
                await main_module.main()

            mock_property_bot_instance.start.assert_awaited_once()
            mock_property_bot_instance.stop.assert_awaited_once()

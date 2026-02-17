"""Unit tests for telegram_bot/middlewares/."""

import pytest


# Skip entire module if aiogram not installed
pytest.importorskip("aiogram", reason="aiogram not installed")

from unittest.mock import AsyncMock, MagicMock

from aiogram import Dispatcher
from aiogram.types import Message, User

from telegram_bot.middlewares.error_handler import (
    ErrorHandlerMiddleware,
    setup_error_middleware,
)
from telegram_bot.middlewares.throttling import (
    ThrottlingMiddleware,
    setup_throttling_middleware,
)


class TestErrorHandlerMiddleware:
    """Test ErrorHandlerMiddleware."""

    def test_middleware_creation(self):
        """Test that middleware can be created."""
        middleware = ErrorHandlerMiddleware()
        assert middleware is not None

    async def test_middleware_passes_through_on_success(self):
        """Test that middleware passes through when handler succeeds."""
        middleware = ErrorHandlerMiddleware()

        handler = AsyncMock(return_value="success")
        event = MagicMock(spec=Message)
        data = {}

        result = await middleware(handler, event, data)

        assert result == "success"
        handler.assert_called_once_with(event, data)

    async def test_middleware_handles_exception(self):
        """Test that middleware handles exceptions and sends error message."""
        middleware = ErrorHandlerMiddleware()

        handler = AsyncMock(side_effect=Exception("Test error"))
        event = MagicMock(spec=Message)
        event.answer = AsyncMock()
        data = {}

        with pytest.raises(Exception, match="Test error"):
            await middleware(handler, event, data)

        # Should have sent error message
        event.answer.assert_called_once()
        call_args = event.answer.call_args[0][0]
        assert "ошибка" in call_args.lower()

    async def test_middleware_logs_error(self, caplog):
        """Test that middleware logs errors."""
        middleware = ErrorHandlerMiddleware()

        handler = AsyncMock(side_effect=ValueError("Value error"))
        event = MagicMock(spec=Message)
        event.answer = AsyncMock()
        data = {}

        with caplog.at_level("ERROR", logger="telegram_bot.middlewares.error_handler"):
            with pytest.raises(ValueError):
                await middleware(handler, event, data)

        assert any("Error in handler" in record.message for record in caplog.records)


class TestSetupErrorMiddleware:
    """Test setup_error_middleware function."""

    def test_setup_registers_middleware(self):
        """Test that setup function registers middleware."""
        dp = MagicMock(spec=Dispatcher)
        dp.message = MagicMock()
        dp.message.outer_middleware = MagicMock()

        setup_error_middleware(dp)

        dp.message.outer_middleware.register.assert_called_once()


class TestThrottlingMiddleware:
    """Test ThrottlingMiddleware."""

    def test_middleware_creation_defaults(self):
        """Test middleware creation with defaults."""
        middleware = ThrottlingMiddleware()

        assert middleware.rate_limit == 1.5
        assert middleware.admin_ids == set()

    def test_middleware_creation_custom(self):
        """Test middleware creation with custom values."""
        middleware = ThrottlingMiddleware(rate_limit=2.0, admin_ids=[123, 456])

        assert middleware.rate_limit == 2.0
        assert middleware.admin_ids == {123, 456}

    async def test_middleware_allows_first_request(self):
        """Test that first request is allowed."""
        middleware = ThrottlingMiddleware(rate_limit=1.5)

        handler = AsyncMock(return_value="success")

        user = MagicMock(spec=User)
        user.id = 12345

        event = MagicMock(spec=Message)
        data = {"event_from_user": user}

        result = await middleware(handler, event, data)

        assert result == "success"
        handler.assert_called_once()

    async def test_middleware_throttles_rapid_requests(self):
        """Test that rapid requests are throttled."""
        middleware = ThrottlingMiddleware(rate_limit=1.5)

        handler = AsyncMock(return_value="success")

        user = MagicMock(spec=User)
        user.id = 12345

        event = MagicMock(spec=Message)
        event.answer = AsyncMock()
        data = {"event_from_user": user}

        # First request
        result1 = await middleware(handler, event, data)
        assert result1 == "success"

        # Second rapid request - should be throttled
        result2 = await middleware(handler, event, data)
        assert result2 is None

        # Should have sent throttle message
        event.answer.assert_called_once()

    async def test_middleware_exempts_admins(self):
        """Test that admins are exempt from throttling."""
        middleware = ThrottlingMiddleware(rate_limit=1.5, admin_ids=[12345])

        handler = AsyncMock(return_value="success")

        user = MagicMock(spec=User)
        user.id = 12345  # Admin

        event = MagicMock(spec=Message)
        data = {"event_from_user": user}

        # First request
        result1 = await middleware(handler, event, data)
        assert result1 == "success"

        # Second rapid request - admin should not be throttled
        result2 = await middleware(handler, event, data)
        assert result2 == "success"

    async def test_middleware_handles_no_user(self):
        """Test that middleware handles events without user."""
        middleware = ThrottlingMiddleware()

        handler = AsyncMock(return_value="success")

        event = MagicMock(spec=Message)
        data = {}  # No user

        result = await middleware(handler, event, data)

        assert result == "success"
        handler.assert_called_once()


class TestSetupThrottlingMiddleware:
    """Test setup_throttling_middleware function."""

    def test_setup_registers_middleware(self):
        """Test that setup function registers middleware."""
        dp = MagicMock(spec=Dispatcher)
        dp.message = MagicMock()
        dp.message.middleware = MagicMock()
        dp.callback_query = MagicMock()
        dp.callback_query.middleware = MagicMock()

        setup_throttling_middleware(dp, rate_limit=2.0, admin_ids=[123])

        dp.message.middleware.register.assert_called_once()
        dp.callback_query.middleware.register.assert_called_once()

"""Unit tests for telegram_bot/middlewares/."""

import pytest


# Skip entire module if aiogram not installed
pytest.importorskip("aiogram", reason="aiogram not installed")

from unittest.mock import AsyncMock, MagicMock, patch

from aiogram import Dispatcher
from aiogram.types import CallbackQuery, Message, User

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

        assert middleware.default_rate == 1.0
        assert middleware.admin_ids == set()

    def test_middleware_creation_custom(self):
        """Test middleware creation with custom values."""
        middleware = ThrottlingMiddleware(default_rate=2.0, admin_ids=[123, 456])

        assert middleware.default_rate == 2.0
        assert middleware.admin_ids == {123, 456}

    async def test_middleware_allows_first_request(self):
        """Test that first request is allowed."""
        middleware = ThrottlingMiddleware(default_rate=1.0)

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
        middleware = ThrottlingMiddleware(default_rate=1.0)

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
        middleware = ThrottlingMiddleware(default_rate=1.0, admin_ids=[12345])

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

    async def test_handler_with_rate_limit_flag_uses_custom_rate(self):
        """Handler with rate_limit flag throttles at its declared rate, not default."""
        middleware = ThrottlingMiddleware(default_rate=1.0)

        handler = AsyncMock(return_value="success")

        user = MagicMock(spec=User)
        user.id = 12345

        event = MagicMock(spec=Message)
        event.answer = AsyncMock()
        data = {"event_from_user": user}

        with patch(
            "telegram_bot.middlewares.throttling.get_flag",
            return_value={"rate": 0.3, "key": "catalog_more"},
        ):
            result1 = await middleware(handler, event, data)
            assert result1 == "success"

            # Second rapid request — should be throttled
            result2 = await middleware(handler, event, data)
            assert result2 is None

    async def test_handler_without_flag_uses_default_message_rate(self):
        """Handler without flag falls back to default_rate (1.0) for Message."""
        middleware = ThrottlingMiddleware(default_rate=1.0)

        handler = AsyncMock(return_value="success")

        user = MagicMock(spec=User)
        user.id = 12345

        event = MagicMock(spec=Message)
        event.answer = AsyncMock()
        data = {"event_from_user": user}

        with patch(
            "telegram_bot.middlewares.throttling.get_flag",
            return_value=None,
        ):
            result1 = await middleware(handler, event, data)
            assert result1 == "success"

            result2 = await middleware(handler, event, data)
            assert result2 is None

    async def test_handler_without_flag_uses_callback_default(self):
        """Handler without flag falls back to 0.3 for CallbackQuery."""
        middleware = ThrottlingMiddleware(default_rate=1.0)

        handler = AsyncMock(return_value="success")

        user = MagicMock(spec=User)
        user.id = 12345

        event = MagicMock(spec=CallbackQuery)
        event.answer = AsyncMock()
        data = {"event_from_user": user}

        with patch(
            "telegram_bot.middlewares.throttling.get_flag",
            return_value=None,
        ):
            result1 = await middleware(handler, event, data)
            assert result1 == "success"

            result2 = await middleware(handler, event, data)
            assert result2 is None
            event.answer.assert_called_once()

    async def test_different_keys_do_not_block_each_other(self):
        """Requests with different keys are independently throttled."""
        middleware = ThrottlingMiddleware(default_rate=1.0)

        handler = AsyncMock(return_value="success")

        user = MagicMock(spec=User)
        user.id = 12345

        event = MagicMock(spec=Message)
        event.answer = AsyncMock()
        data = {"event_from_user": user}

        # First request with key "catalog_more"
        with patch(
            "telegram_bot.middlewares.throttling.get_flag",
            return_value={"rate": 0.3, "key": "catalog_more"},
        ):
            result1 = await middleware(handler, event, data)
            assert result1 == "success"

        # Second request with key "catalog_filters" — should NOT be blocked
        with patch(
            "telegram_bot.middlewares.throttling.get_flag",
            return_value={"rate": 0.3, "key": "catalog_filters"},
        ):
            result2 = await middleware(handler, event, data)
            assert result2 == "success", "Different keys should not block each other"

    async def test_same_key_twice_faster_than_rate_is_throttled(self):
        """Same key hit twice within rate window is throttled."""
        middleware = ThrottlingMiddleware(default_rate=1.0)

        handler = AsyncMock(return_value="success")

        user = MagicMock(spec=User)
        user.id = 12345

        event = MagicMock(spec=Message)
        event.answer = AsyncMock()
        data = {"event_from_user": user}

        with patch(
            "telegram_bot.middlewares.throttling.get_flag",
            return_value={"rate": 0.3, "key": "voice"},
        ):
            result1 = await middleware(handler, event, data)
            assert result1 == "success"

            result2 = await middleware(handler, event, data)
            assert result2 is None

    async def test_admin_bypass_with_rate_limit_flag(self):
        """Admin bypasses throttling even when handler has rate_limit flag."""
        middleware = ThrottlingMiddleware(default_rate=1.0, admin_ids=[12345])

        handler = AsyncMock(return_value="success")

        user = MagicMock(spec=User)
        user.id = 12345

        event = MagicMock(spec=Message)
        data = {"event_from_user": user}

        with patch(
            "telegram_bot.middlewares.throttling.get_flag",
            return_value={"rate": 0.3, "key": "catalog_more"},
        ):
            result1 = await middleware(handler, event, data)
            assert result1 == "success"

            result2 = await middleware(handler, event, data)
            assert result2 == "success"

    async def test_lazy_cache_creation(self):
        """Caches are created lazily per unique rate value."""
        middleware = ThrottlingMiddleware(default_rate=1.0)
        assert len(middleware._caches) == 0

        handler = AsyncMock(return_value="success")
        user = MagicMock(spec=User)
        user.id = 12345
        event = MagicMock(spec=Message)
        data = {"event_from_user": user}

        # Use rate=0.3
        with patch(
            "telegram_bot.middlewares.throttling.get_flag",
            return_value={"rate": 0.3, "key": "a"},
        ):
            await middleware(handler, event, data)
        assert 0.3 in middleware._caches
        assert len(middleware._caches) == 1

        # Use rate=0.6
        user2 = MagicMock(spec=User)
        user2.id = 99999
        data2 = {"event_from_user": user2}
        with patch(
            "telegram_bot.middlewares.throttling.get_flag",
            return_value={"rate": 0.6, "key": "b"},
        ):
            await middleware(handler, event, data2)
        assert 0.6 in middleware._caches
        assert len(middleware._caches) == 2


class TestSetupThrottlingMiddleware:
    """Test setup_throttling_middleware function."""

    def test_setup_registers_middleware(self):
        """Test that setup function registers middleware."""
        dp = MagicMock(spec=Dispatcher)
        dp.message = MagicMock()
        dp.message.middleware = MagicMock()
        dp.callback_query = MagicMock()
        dp.callback_query.middleware = MagicMock()

        setup_throttling_middleware(dp, default_rate=2.0, admin_ids=[123])

        dp.message.middleware.register.assert_called_once()
        # 2 registrations: ThrottlingMiddleware + CallbackAnswerMiddleware
        assert dp.callback_query.middleware.register.call_count == 2

"""Unit tests for telegram_bot middlewares."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class TestErrorHandlerMiddleware:
    """Tests for error handler middleware."""

    @pytest.fixture
    def middleware(self):
        """Create ErrorHandlerMiddleware instance."""
        from telegram_bot.middlewares.error_handler import ErrorHandlerMiddleware

        return ErrorHandlerMiddleware()

    async def test_successful_handler_passes_through(self, middleware):
        """Test that successful handler results pass through unchanged."""
        handler = AsyncMock(return_value="success_result")
        event = MagicMock()
        data = {"key": "value"}

        result = await middleware(handler, event, data)

        assert result == "success_result"
        handler.assert_called_once_with(event, data)

    async def test_error_handler_logs_exception(self, middleware):
        """Test that errors are logged with exception info."""
        handler = AsyncMock(side_effect=ValueError("Test error"))
        event = MagicMock(spec=[])  # Not a Message
        data = {}

        with patch("telegram_bot.middlewares.error_handler.logger") as mock_logger:
            with pytest.raises(ValueError, match="Test error"):
                await middleware(handler, event, data)

            mock_logger.error.assert_called_once()
            call_args = mock_logger.error.call_args
            assert "Test error" in str(call_args)
            assert call_args.kwargs.get("exc_info") is True

    async def test_error_sends_message_to_user(self, middleware):
        """Test that error sends user-friendly message for Message events."""
        from aiogram.types import Message

        handler = AsyncMock(side_effect=RuntimeError("Internal error"))
        event = MagicMock(spec=Message)
        event.answer = AsyncMock()
        data = {}

        with patch("telegram_bot.middlewares.error_handler.logger"):
            with pytest.raises(RuntimeError):
                await middleware(handler, event, data)

        event.answer.assert_called_once()
        call_args = event.answer.call_args[0][0]
        assert "ошибка" in call_args.lower() or "❌" in call_args

    async def test_error_does_not_send_message_for_non_message_event(self, middleware):
        """Test that error does not try to send message for non-Message events."""
        handler = AsyncMock(side_effect=RuntimeError("Internal error"))
        event = MagicMock(spec=[])  # Not a Message
        data = {}

        with patch("telegram_bot.middlewares.error_handler.logger"):
            with pytest.raises(RuntimeError):
                await middleware(handler, event, data)

        # No answer method should be called
        assert not hasattr(event, "answer") or not event.answer.called

    async def test_error_is_re_raised(self, middleware):
        """Test that the original error is re-raised after handling."""
        handler = AsyncMock(side_effect=KeyError("missing_key"))
        event = MagicMock(spec=[])
        data = {}

        with patch("telegram_bot.middlewares.error_handler.logger"):
            with pytest.raises(KeyError, match="missing_key"):
                await middleware(handler, event, data)


class TestSetupErrorMiddleware:
    """Tests for setup_error_middleware function."""

    def test_setup_registers_middleware(self):
        """Test that setup_error_middleware registers the middleware."""
        from telegram_bot.middlewares.error_handler import setup_error_middleware

        mock_dp = MagicMock()

        with patch("telegram_bot.middlewares.error_handler.logger"):
            setup_error_middleware(mock_dp)

        mock_dp.message.outer_middleware.register.assert_called_once()


class TestThrottlingMiddleware:
    """Tests for throttling middleware."""

    @pytest.fixture
    def middleware(self):
        """Create ThrottlingMiddleware instance."""
        from telegram_bot.middlewares.throttling import ThrottlingMiddleware

        return ThrottlingMiddleware(default_rate=1.0, admin_ids=[123, 456])

    async def test_first_request_passes_through(self, middleware):
        """Test that first request from a user passes through."""
        handler = AsyncMock(return_value="result")
        event = MagicMock()
        user = MagicMock()
        user.id = 789  # Not an admin
        data = {"event_from_user": user}

        result = await middleware(handler, event, data)

        assert result == "result"
        handler.assert_called_once_with(event, data)

    async def test_second_request_is_throttled(self, middleware):
        """Test that rapid second request is throttled."""
        from aiogram.types import Message

        handler = AsyncMock(return_value="result")
        event = MagicMock(spec=Message)
        event.answer = AsyncMock()
        user = MagicMock()
        user.id = 789
        data = {"event_from_user": user}

        # First request - should pass
        result1 = await middleware(handler, event, data)
        assert result1 == "result"

        # Second request immediately - should be throttled
        with patch("telegram_bot.middlewares.throttling.logger"):
            result2 = await middleware(handler, event, data)

        assert result2 is None
        event.answer.assert_called_once()
        assert (
            "подождите" in event.answer.call_args[0][0].lower()
            or "⏱" in event.answer.call_args[0][0]
        )

    async def test_admin_is_not_throttled(self, middleware):
        """Test that admin users are exempt from throttling."""
        handler = AsyncMock(return_value="result")
        event = MagicMock()
        user = MagicMock()
        user.id = 123  # Admin ID
        data = {"event_from_user": user}

        # First request
        result1 = await middleware(handler, event, data)
        assert result1 == "result"

        # Second request immediately - should still pass (admin)
        result2 = await middleware(handler, event, data)
        assert result2 == "result"

        assert handler.call_count == 2

    async def test_no_user_passes_through(self, middleware):
        """Test that events without user info pass through."""
        handler = AsyncMock(return_value="result")
        event = MagicMock()
        data = {}  # No event_from_user

        result = await middleware(handler, event, data)

        assert result == "result"
        handler.assert_called_once()

    async def test_callback_query_throttle_message(self, middleware):
        """Test that throttled callback queries show alert."""
        from aiogram.types import CallbackQuery

        handler = AsyncMock(return_value="result")
        event = MagicMock(spec=CallbackQuery)
        event.answer = AsyncMock()
        user = MagicMock()
        user.id = 789
        data = {"event_from_user": user}

        # First request
        await middleware(handler, event, data)

        # Second request - throttled
        with patch("telegram_bot.middlewares.throttling.logger"):
            result = await middleware(handler, event, data)

        assert result is None
        event.answer.assert_called_once()
        call_kwargs = event.answer.call_args.kwargs
        assert call_kwargs.get("show_alert") is True

    def test_initialization_with_defaults(self):
        """Test middleware initialization with default values."""
        from telegram_bot.middlewares.throttling import ThrottlingMiddleware

        with patch("telegram_bot.middlewares.throttling.logger"):
            middleware = ThrottlingMiddleware()

        assert middleware.default_rate == 1.0
        assert middleware.admin_ids == set()

    def test_initialization_with_custom_values(self):
        """Test middleware initialization with custom values."""
        from telegram_bot.middlewares.throttling import ThrottlingMiddleware

        with patch("telegram_bot.middlewares.throttling.logger"):
            middleware = ThrottlingMiddleware(default_rate=3.0, admin_ids=[100, 200])

        assert middleware.default_rate == 3.0
        assert middleware.admin_ids == {100, 200}

    async def test_handler_with_rate_limit_flag(self):
        """Handler with rate_limit flag uses its rate, not default."""
        from telegram_bot.middlewares.throttling import ThrottlingMiddleware

        middleware = ThrottlingMiddleware(default_rate=1.0)
        handler = AsyncMock(return_value="result")
        event = MagicMock()
        event.answer = AsyncMock()
        user = MagicMock()
        user.id = 789
        data = {"event_from_user": user}

        with patch(
            "telegram_bot.middlewares.throttling.get_flag",
            return_value={"rate": 0.3, "key": "catalog_more"},
        ):
            result1 = await middleware(handler, event, data)
            assert result1 == "result"

            with patch("telegram_bot.middlewares.throttling.logger"):
                result2 = await middleware(handler, event, data)
            assert result2 is None

    async def test_different_keys_independent(self):
        """Different keys do not block each other for the same user."""
        from telegram_bot.middlewares.throttling import ThrottlingMiddleware

        middleware = ThrottlingMiddleware(default_rate=1.0)
        handler = AsyncMock(return_value="result")
        event = MagicMock()
        user = MagicMock()
        user.id = 789
        data = {"event_from_user": user}

        with patch(
            "telegram_bot.middlewares.throttling.get_flag",
            return_value={"rate": 0.3, "key": "catalog_more"},
        ):
            await middleware(handler, event, data)

        with patch(
            "telegram_bot.middlewares.throttling.get_flag",
            return_value={"rate": 0.3, "key": "catalog_filters"},
        ):
            result = await middleware(handler, event, data)
            assert result == "result", "Different keys must not block each other"


class TestSetupThrottlingMiddleware:
    """Tests for setup_throttling_middleware function."""

    def test_setup_registers_middlewares(self):
        """Test that setup registers middleware for messages and callbacks."""
        from telegram_bot.middlewares.throttling import setup_throttling_middleware

        mock_dp = MagicMock()

        with patch("telegram_bot.middlewares.throttling.logger"):
            setup_throttling_middleware(mock_dp, default_rate=2.0, admin_ids=[111])

        mock_dp.message.middleware.register.assert_called_once()
        # 2 registrations: ThrottlingMiddleware + CallbackAnswerMiddleware
        assert mock_dp.callback_query.middleware.register.call_count == 2

    def test_setup_uses_defaults(self):
        """Test that setup works with default parameters."""
        from telegram_bot.middlewares.throttling import setup_throttling_middleware

        mock_dp = MagicMock()

        with patch("telegram_bot.middlewares.throttling.logger"):
            setup_throttling_middleware(mock_dp)

        mock_dp.message.middleware.register.assert_called_once()
        # 2 registrations: ThrottlingMiddleware + CallbackAnswerMiddleware
        assert mock_dp.callback_query.middleware.register.call_count == 2

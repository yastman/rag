"""Unit tests for simplified I18nMiddleware (H5 refactor)."""

import pytest


pytest.importorskip("aiogram", reason="aiogram not installed")

from unittest.mock import AsyncMock, MagicMock, patch

from aiogram import Dispatcher
from aiogram.types import Message, User

from telegram_bot.middlewares.i18n import I18nMiddleware, setup_i18n_middleware


class TestI18nMiddlewareInit:
    """Test I18nMiddleware.__init__ signature is simplified."""

    def test_only_hub_required(self):
        hub = MagicMock()
        mw = I18nMiddleware(hub=hub)
        assert mw._hub is hub
        assert mw._user_service is None
        assert mw._default_locale == "ru"

    def test_with_user_service(self):
        hub = MagicMock()
        user_service = MagicMock()
        mw = I18nMiddleware(hub=hub, user_service=user_service)
        assert mw._user_service is user_service

    def test_no_service_params(self):
        """Middleware must NOT accept old service params (lead_scoring_store etc.)."""
        import inspect

        sig = inspect.signature(I18nMiddleware.__init__)
        params = set(sig.parameters.keys())
        forbidden = {
            "lead_scoring_store",
            "hot_lead_notifier",
            "kommo_client",
            "pg_pool",
            "bot_config",
            "property_bot",
            "ai_advisor_service",
        }
        assert not (forbidden & params), f"Unexpected params still present: {forbidden & params}"


class TestI18nMiddlewareCall:
    """Test I18nMiddleware.__call__ injects only i18n + locale."""

    def _make_hub(self, locale: str = "ru") -> MagicMock:
        hub = MagicMock()
        translator = MagicMock()
        hub.get_translator_by_locale.return_value = translator
        return hub

    async def test_injects_i18n_and_locale(self):
        hub = self._make_hub()
        mw = I18nMiddleware(hub=hub, default_locale="ru")
        handler = AsyncMock(return_value="ok")
        event = MagicMock(spec=Message)
        data: dict = {}

        result = await mw(handler, event, data)

        assert result == "ok"
        assert "i18n" in data
        assert data["locale"] == "ru"
        hub.get_translator_by_locale.assert_called_once_with("ru")

    async def test_does_not_inject_services(self):
        """After refactor, services must NOT be injected by middleware."""
        hub = self._make_hub()
        mw = I18nMiddleware(hub=hub)
        handler = AsyncMock(return_value=None)
        event = MagicMock(spec=Message)
        data: dict = {}

        await mw(handler, event, data)

        service_keys = {
            "user_service",
            "lead_scoring_store",
            "hot_lead_notifier",
            "kommo_client",
            "pg_pool",
            "bot_config",
            "property_bot",
            "ai_advisor_service",
            "apartments_service",
            "favorites_service",
            "search_event_store",
        }
        injected = service_keys & data.keys()
        assert not injected, f"Middleware should not inject services, got: {injected}"

    async def test_uses_user_service_for_locale(self):
        hub = self._make_hub()
        user_service = MagicMock()
        user_service.get_or_create = AsyncMock(return_value=MagicMock(locale="uk"))
        mw = I18nMiddleware(hub=hub, user_service=user_service)

        user = MagicMock(spec=User)
        user.id = 42
        user.language_code = "uk"
        user.first_name = "Test"

        handler = AsyncMock(return_value=None)
        event = MagicMock(spec=Message)
        data: dict = {"event_from_user": user}

        await mw(handler, event, data)

        assert data["locale"] == "uk"
        user_service.get_or_create.assert_called_once_with(
            telegram_id=42,
            first_name="Test",
            language_code="uk",
        )

    async def test_fallback_to_language_code(self):
        hub = self._make_hub()
        user_service = MagicMock()
        user_service.get_or_create = AsyncMock(return_value=None)
        mw = I18nMiddleware(hub=hub, user_service=user_service, default_locale="ru")

        user = MagicMock(spec=User)
        user.id = 99
        user.language_code = "en"
        user.first_name = "Test"

        handler = AsyncMock(return_value=None)
        event = MagicMock(spec=Message)
        data: dict = {"event_from_user": user}

        with patch(
            "telegram_bot.services.user_service.detect_locale",
            return_value="en",
        ) as mock_detect:
            await mw(handler, event, data)
            mock_detect.assert_called_once_with("en")

        assert data["locale"] == "en"

    async def test_user_service_exception_fallback(self):
        hub = self._make_hub()
        user_service = MagicMock()
        user_service.get_or_create = AsyncMock(side_effect=RuntimeError("db down"))
        mw = I18nMiddleware(hub=hub, user_service=user_service, default_locale="ru")

        user = MagicMock(spec=User)
        user.id = 7
        user.language_code = None
        user.first_name = "Test"

        handler = AsyncMock(return_value=None)
        event = MagicMock(spec=Message)
        data: dict = {"event_from_user": user}

        # Should not raise; fall back to default locale
        await mw(handler, event, data)
        assert data["locale"] == "ru"

    async def test_existing_user_locale_beats_telegram_language_code(self):
        hub = self._make_hub()
        user_service = MagicMock()
        user_service.get_or_create = AsyncMock(return_value=MagicMock(locale="ru"))
        mw = I18nMiddleware(hub=hub, user_service=user_service, default_locale="ru")

        user = MagicMock(spec=User)
        user.id = 123
        user.language_code = "en"
        user.first_name = "Test"

        handler = AsyncMock(return_value=None)
        event = MagicMock(spec=Message)
        data: dict = {"event_from_user": user}

        await mw(handler, event, data)

        assert data["locale"] == "ru"

    async def test_no_user_uses_default_locale(self):
        hub = self._make_hub()
        mw = I18nMiddleware(hub=hub, default_locale="en")
        handler = AsyncMock(return_value=None)
        event = MagicMock(spec=Message)
        data: dict = {}

        await mw(handler, event, data)

        assert data["locale"] == "en"


class TestSetupI18nMiddleware:
    """Test that setup_i18n_middleware accepts only 3 params."""

    def test_setup_signature(self):
        import inspect

        sig = inspect.signature(setup_i18n_middleware)
        params = list(sig.parameters.keys())
        assert params == ["dp", "hub", "user_service"], (
            f"Expected [dp, hub, user_service], got {params}"
        )

    def test_registers_on_message_and_callback(self):
        dp = MagicMock(spec=Dispatcher)
        dp.message = MagicMock()
        dp.message.outer_middleware = MagicMock()
        dp.callback_query = MagicMock()
        dp.callback_query.outer_middleware = MagicMock()

        hub = MagicMock()
        setup_i18n_middleware(dp, hub)

        dp.message.outer_middleware.assert_called_once()
        dp.callback_query.outer_middleware.assert_called_once()

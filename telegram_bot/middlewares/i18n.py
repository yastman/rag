"""i18n middleware using fluentogram (Fluent .ftl files)."""

from __future__ import annotations

import logging
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING, Any

from aiogram import BaseMiddleware, Dispatcher
from fluent_compiler.bundle import FluentBundle
from fluentogram import FluentTranslator, TranslatorHub


if TYPE_CHECKING:
    from aiogram.types import TelegramObject

    from telegram_bot.services.user_service import UserService

logger = logging.getLogger(__name__)


def create_translator_hub(
    *,
    locales_dir: Path | None = None,
) -> TranslatorHub:
    """Create TranslatorHub with all supported locales.

    Args:
        locales_dir: Path to locales directory. Defaults to telegram_bot/locales/.
    """
    if locales_dir is None:
        locales_dir = Path(__file__).resolve().parent.parent / "locales"

    return TranslatorHub(
        locales_map={
            "en": ("en",),
            "ru": ("ru", "en"),
            "uk": ("uk", "ru", "en"),
        },
        translators=[
            FluentTranslator(
                locale="en",
                translator=FluentBundle.from_files(
                    "en-US",
                    filenames=[str(p) for p in (locales_dir / "en").glob("*.ftl")],
                ),
            ),
            FluentTranslator(
                locale="ru",
                translator=FluentBundle.from_files(
                    "ru",
                    filenames=[str(p) for p in (locales_dir / "ru").glob("*.ftl")],
                ),
            ),
            FluentTranslator(
                locale="uk",
                translator=FluentBundle.from_files(
                    "uk",
                    filenames=[str(p) for p in (locales_dir / "uk").glob("*.ftl")],
                ),
            ),
        ],
    )


class I18nMiddleware(BaseMiddleware):
    """Inject translator (i18n) into handler data based on user locale."""

    def __init__(
        self,
        hub: TranslatorHub,
        user_service: UserService | None = None,
        lead_scoring_store: Any | None = None,
        hot_lead_notifier: Any | None = None,
        kommo_client: Any | None = None,
        pg_pool: Any | None = None,
        bot_config: Any | None = None,
        default_locale: str = "ru",
    ) -> None:
        super().__init__()
        self._hub = hub
        self._user_service = user_service
        self._lead_scoring_store = lead_scoring_store
        self._hot_lead_notifier = hot_lead_notifier
        self._kommo_client = kommo_client
        self._pg_pool = pg_pool
        self._bot_config = bot_config
        self._default_locale = default_locale

    async def __call__(
        self,
        handler: Callable,
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        user = data.get("event_from_user")
        locale = self._default_locale

        if user is not None:
            # Try loading from DB/cache via UserService
            if self._user_service is not None:
                try:
                    locale = await self._user_service.get_locale(telegram_id=user.id)
                except Exception:
                    logger.debug("Failed to get locale for user %s", user.id, exc_info=True)

            # Fallback: detect from Telegram language_code
            if locale == self._default_locale and user.language_code:
                from telegram_bot.services.user_service import detect_locale

                locale = detect_locale(user.language_code)

        data["i18n"] = self._hub.get_translator_by_locale(locale)
        data["locale"] = locale
        data["user_service"] = self._user_service
        data["lead_scoring_store"] = self._lead_scoring_store
        data["hot_lead_notifier"] = self._hot_lead_notifier
        data["kommo_client"] = self._kommo_client
        data["pg_pool"] = self._pg_pool
        data["bot_config"] = self._bot_config
        return await handler(event, data)


def setup_i18n_middleware(
    dp: Dispatcher,
    hub: TranslatorHub,
    user_service: UserService | None = None,
    lead_scoring_store: Any | None = None,
    hot_lead_notifier: Any | None = None,
    kommo_client: Any | None = None,
    pg_pool: Any | None = None,
    bot_config: Any | None = None,
) -> None:
    """Register i18n middleware on all routers."""
    middleware = I18nMiddleware(
        hub=hub,
        user_service=user_service,
        lead_scoring_store=lead_scoring_store,
        hot_lead_notifier=hot_lead_notifier,
        kommo_client=kommo_client,
        pg_pool=pg_pool,
        bot_config=bot_config,
    )
    dp.message.outer_middleware(middleware)
    dp.callback_query.outer_middleware(middleware)

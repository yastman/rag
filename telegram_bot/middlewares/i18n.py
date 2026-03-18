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
        default_locale: str = "ru",
    ) -> None:
        super().__init__()
        self._hub = hub
        self._user_service = user_service
        self._default_locale = default_locale

    async def __call__(
        self,
        handler: Callable,
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        user = data.get("event_from_user")
        locale = self._default_locale
        locale_loaded_from_storage = False

        if user is not None:
            # Resolve locale from the persisted user record when available.
            # This keeps message and callback flows on the same language path.
            if self._user_service is not None:
                try:
                    stored_user = await self._user_service.get_or_create(
                        telegram_id=user.id,
                        first_name=getattr(user, "first_name", None),
                        language_code=getattr(user, "language_code", None),
                    )
                    if stored_user is not None and stored_user.locale:
                        locale = stored_user.locale
                        locale_loaded_from_storage = True
                except Exception:
                    logger.debug("Failed to get locale for user %s", user.id, exc_info=True)

            # Fallback: detect from Telegram language_code
            if (
                not locale_loaded_from_storage
                and locale == self._default_locale
                and user.language_code
            ):
                from telegram_bot.services.user_service import detect_locale

                locale = detect_locale(user.language_code)

        data["i18n"] = self._hub.get_translator_by_locale(locale)
        data["locale"] = locale
        return await handler(event, data)


def setup_i18n_middleware(
    dp: Dispatcher,
    hub: TranslatorHub,
    user_service: UserService | None = None,
) -> None:
    """Register i18n middleware on all routers."""
    middleware = I18nMiddleware(
        hub=hub,
        user_service=user_service,
    )
    dp.message.outer_middleware(middleware)
    dp.callback_query.outer_middleware(middleware)

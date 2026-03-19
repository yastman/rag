"""Catalog-specific reply keyboard and text action parsing."""

from __future__ import annotations

import logging
from typing import Any

from aiogram.types import KeyboardButton, ReplyKeyboardMarkup


logger = logging.getLogger(__name__)


CATALOG_ACTION_TO_FALLBACK_TEXT: dict[str, str] = {
    "catalog_filters": "🔍 Фильтры",
    "catalog_bookmarks": "📌 Избранное",
    "catalog_viewing": "📅 Запись на осмотр",
    "catalog_manager": "👤 Написать менеджеру",
    "catalog_home": "🏠 Главное меню",
}

_ACTION_TO_FTL_KEY: dict[str, str] = {
    "catalog_filters": "catalog-filters",
    "catalog_bookmarks": "catalog-bookmarks",
    "catalog_viewing": "kb-viewing",
    "catalog_manager": "catalog-manager",
    "catalog_home": "main-menu",
}

_SHOW_MORE_FTL_KEYS = ("results-show-more",)


def _collect_labels(i18n_hub: Any, action_id: str) -> set[str]:
    labels = {CATALOG_ACTION_TO_FALLBACK_TEXT[action_id]}
    ftl_key = _ACTION_TO_FTL_KEY[action_id]
    for locale in ("ru", "uk", "en"):
        try:
            translator = i18n_hub.get_translator_by_locale(locale)
        except Exception:
            logger.debug("Failed to load translator for locale=%s", locale, exc_info=True)
            continue
        if translator is None:
            continue
        try:
            label = translator.get(ftl_key)
        except Exception:
            logger.debug(
                "Failed to resolve catalog label for locale=%s key=%s",
                locale,
                ftl_key,
                exc_info=True,
            )
            continue
        if isinstance(label, str) and label:
            labels.add(label)
    return labels


def _collect_show_more_prefixes(i18n_hub: Any = None, i18n: Any = None) -> set[str]:
    prefixes = {"🔄 Показать ещё", "🔄 Показать еще", "🔄 Show more", "🔄 Показати ще"}
    if i18n is not None:
        for key in _SHOW_MORE_FTL_KEYS:
            try:
                label = i18n.get(key)
            except Exception:
                continue
            if isinstance(label, str) and label:
                prefixes.add(label)
    if i18n_hub is not None:
        for locale in ("ru", "uk", "en"):
            try:
                translator = i18n_hub.get_translator_by_locale(locale)
            except Exception:
                logger.debug("Failed to load translator for locale=%s", locale, exc_info=True)
                continue
            if translator is None:
                continue
            for key in _SHOW_MORE_FTL_KEYS:
                try:
                    label = translator.get(key)
                except Exception:
                    logger.debug(
                        "Failed to resolve show-more label for locale=%s key=%s",
                        locale,
                        key,
                        exc_info=True,
                    )
                    continue
                if isinstance(label, str) and label:
                    prefixes.add(label)
    return prefixes


def build_catalog_keyboard(
    *,
    shown: int,
    total: int,
    i18n: Any = None,
) -> ReplyKeyboardMarkup:
    if i18n is not None:
        show_more = i18n.get("results-show-more")
        filters = i18n.get("catalog-filters")
        bookmarks = i18n.get("catalog-bookmarks")
        viewing = i18n.get("kb-viewing")
        manager = i18n.get("catalog-manager")
        home = i18n.get("main-menu")
    else:
        show_more = "🔄 Показать ещё"
        filters = CATALOG_ACTION_TO_FALLBACK_TEXT["catalog_filters"]
        bookmarks = CATALOG_ACTION_TO_FALLBACK_TEXT["catalog_bookmarks"]
        viewing = CATALOG_ACTION_TO_FALLBACK_TEXT["catalog_viewing"]
        manager = CATALOG_ACTION_TO_FALLBACK_TEXT["catalog_manager"]
        home = CATALOG_ACTION_TO_FALLBACK_TEXT["catalog_home"]

    rows: list[list[KeyboardButton]] = []
    if shown < total:
        rows.append([KeyboardButton(text=show_more)])
    rows.append([KeyboardButton(text=filters), KeyboardButton(text=bookmarks)])
    rows.append([KeyboardButton(text=viewing), KeyboardButton(text=manager)])
    rows.append([KeyboardButton(text=home)])
    return ReplyKeyboardMarkup(
        keyboard=rows,
        resize_keyboard=True,
        is_persistent=True,
    )


def parse_catalog_button(
    text: str,
    *,
    i18n_hub: Any = None,
    i18n: Any = None,
) -> str | None:
    if not text:
        return None

    for prefix in _collect_show_more_prefixes(i18n_hub=i18n_hub, i18n=i18n):
        if text.startswith(prefix):
            return "catalog_more"

    for action_id in (
        "catalog_filters",
        "catalog_bookmarks",
        "catalog_viewing",
        "catalog_manager",
        "catalog_home",
    ):
        labels = {CATALOG_ACTION_TO_FALLBACK_TEXT[action_id]}
        if i18n is not None:
            try:
                label = i18n.get(_ACTION_TO_FTL_KEY[action_id])
            except Exception:
                label = None
            if isinstance(label, str) and label:
                labels.add(label)
        if i18n_hub is not None:
            labels.update(_collect_labels(i18n_hub, action_id))
        if text in labels:
            return action_id

    return None

"""Compatibility tests for stale legacy results callbacks."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from telegram_bot.bot import PropertyBot
from telegram_bot.lifecycle.services import Services
from tests.unit._bot_config_factory import make_full_bot_config as _make_config


def _create_bot() -> PropertyBot:
    config = _make_config()
    services = Services(
        graph_config=MagicMock(),
        cache=MagicMock(),
        hybrid=MagicMock(),
        embeddings=MagicMock(),
        sparse=MagicMock(),
        qdrant=MagicMock(),
        qdrant_apartments=MagicMock(),
        apartments_service=MagicMock(),
        reranker=None,
        llm=MagicMock(),
        apartment_pipeline=MagicMock(),
        redis_monitor=MagicMock(),
        i18n_hub=None,
    )
    return PropertyBot(config, _services=services)


def _make_callback() -> MagicMock:
    cb = MagicMock()
    cb.data = "results:more"
    cb.from_user = MagicMock(id=12345)
    cb.answer = AsyncMock()
    cb.message = MagicMock()
    cb.message.answer = AsyncMock()
    cb.message.edit_reply_markup = AsyncMock()
    return cb


def _make_state(data: dict) -> MagicMock:
    state = MagicMock()
    state.get_data = AsyncMock(return_value=data)
    state.update_data = AsyncMock()
    return state


@pytest.mark.asyncio
async def test_results_more_stale_compat_does_not_call_scroll_with_filters() -> None:
    bot = _create_bot()
    bot._apartments_service = MagicMock()
    bot._apartments_service.scroll_with_filters = AsyncMock()
    state = _make_state(
        {
            "apartment_results": [{"id": "apt-1"}],
            "apartment_offset": 0,
            "apartment_total": 20,
            "apartment_next_offset": 55000.0,
            "apartment_filters": {"rooms": 2},
            "apartment_scroll_seen_ids": ["apt-1"],
        }
    )
    callback = _make_callback()

    await bot.handle_results_callback(callback, state)

    bot._apartments_service.scroll_with_filters.assert_not_awaited()
    state.update_data.assert_not_awaited()
    callback.message.answer.assert_awaited_once_with(
        "Это устаревшая кнопка. Используйте актуальное меню ниже."
    )

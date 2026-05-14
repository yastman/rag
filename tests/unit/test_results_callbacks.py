"""Unit tests for stale legacy results callbacks (#654)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


pytest.importorskip("aiogram", reason="aiogram not installed")

from telegram_bot.bot import PropertyBot
from telegram_bot.config import BotConfig


def _make_config() -> BotConfig:
    return BotConfig(
        _env_file=None,
        telegram_token="test-token",
        voyage_api_key="voyage-key",
        llm_api_key="llm-key",
        llm_base_url="https://api.example.com/v1",
        llm_model="gpt-4o-mini",
        qdrant_url="http://localhost:6333",
        qdrant_api_key="qdrant-key",
        qdrant_collection="test_collection",
        redis_url="redis://localhost:6379",
        realestate_database_url="postgresql://postgres:postgres@127.0.0.1:1/realestate",
        rerank_provider="none",
    )


def _create_bot() -> PropertyBot:
    config = _make_config()
    with (
        patch("telegram_bot.bot.Bot"),
        patch("telegram_bot.integrations.cache.CacheLayerManager"),
        patch("telegram_bot.integrations.embeddings.BGEM3HybridEmbeddings"),
        patch("telegram_bot.integrations.embeddings.BGEM3SparseEmbeddings"),
        patch("telegram_bot.services.qdrant.QdrantService"),
        patch("telegram_bot.graph.config.GraphConfig.create_llm"),
        patch("telegram_bot.graph.config.GraphConfig.create_supervisor_llm"),
    ):
        return PropertyBot(config)


def _make_callback(data: str = "results:more", user_id: int = 12345) -> MagicMock:
    cb = MagicMock()
    cb.data = data
    cb.from_user = MagicMock(id=user_id)
    cb.answer = AsyncMock()
    cb.message = MagicMock()
    cb.message.answer = AsyncMock()
    cb.message.edit_reply_markup = AsyncMock()
    return cb


def _make_state(data: dict | None = None) -> MagicMock:
    state = MagicMock()
    state.get_data = AsyncMock(return_value=data or {})
    state.update_data = AsyncMock()
    return state


def _make_results(n: int = 8) -> list[dict]:
    return [{"id": f"prop-{i}", "payload": {"complex_name": f"Complex {i}"}} for i in range(n)]


@pytest.mark.asyncio
async def test_results_more_is_stale_compat_only() -> None:
    bot = _create_bot()
    bot._send_property_card = AsyncMock()
    state = _make_state({"apartment_results": _make_results(8), "apartment_offset": 0})
    callback = _make_callback("results:more")

    await bot.handle_results_callback(callback, state)

    callback.message.answer.assert_awaited_once_with(
        "Это устаревшая кнопка. Используйте актуальное меню ниже."
    )
    bot._send_property_card.assert_not_awaited()
    state.update_data.assert_not_awaited()
    callback.answer.assert_awaited_once_with()


@pytest.mark.asyncio
async def test_results_refine_is_stale_compat_only() -> None:
    bot = _create_bot()
    state = _make_state({"apartment_results": _make_results(3)})
    callback = _make_callback("results:refine")

    await bot.handle_results_callback(callback, state)

    callback.message.answer.assert_awaited_once_with(
        "Это устаревшая кнопка. Используйте актуальное меню ниже."
    )
    state.update_data.assert_not_awaited()
    callback.answer.assert_awaited_once_with()


@pytest.mark.asyncio
async def test_results_viewing_is_stale_compat_only__results_callbacks() -> None:
    bot = _create_bot()
    state = _make_state({"apartment_results": _make_results(3)})
    callback = _make_callback("results:viewing")
    dialog_manager = AsyncMock()

    await bot.handle_results_callback(callback, state, dialog_manager=dialog_manager)

    dialog_manager.start.assert_not_awaited()
    callback.message.answer.assert_awaited_once_with(
        "Это устаревшая кнопка. Используйте актуальное меню ниже."
    )
    callback.answer.assert_awaited_once_with()


# ---------------------------------------------------------------------------
# Direct module-level handler tests (#1264)
# ---------------------------------------------------------------------------

from telegram_bot.handlers.results_callbacks import (
    create_results_callback_router,
    handle_card_callback,
    handle_results_callback,
)


def _make_direct_cb(data: str = "results:more", user_id: int = 12345) -> MagicMock:
    cb = MagicMock()
    cb.data = data
    cb.from_user = MagicMock(id=user_id)
    cb.answer = AsyncMock()
    cb.message = MagicMock()
    cb.message.answer = AsyncMock()
    cb.message.edit_reply_markup = AsyncMock()
    cb.message.delete = AsyncMock()
    cb.message.chat = MagicMock(id=999)
    cb.bot = AsyncMock()
    return cb


def _make_direct_state(data: dict | None = None) -> MagicMock:
    state = MagicMock()
    state.get_data = AsyncMock(return_value=data or {})
    state.update_data = AsyncMock()
    return state


# handle_results_callback
async def test_direct_results_callback_stale() -> None:
    cb = _make_direct_cb("results:more")
    state = _make_direct_state()
    await handle_results_callback(cb, state)
    cb.message.edit_reply_markup.assert_awaited_once_with(reply_markup=None)
    cb.message.answer.assert_awaited_once()
    cb.answer.assert_awaited_once()


async def test_direct_results_callback_no_message() -> None:
    cb = _make_direct_cb("results:more")
    cb.message = None
    state = _make_direct_state()
    await handle_results_callback(cb, state)
    cb.answer.assert_awaited_once()


# handle_card_callback
async def test_direct_card_callback_invalid_data() -> None:
    cb = _make_direct_cb("card:viewing")
    state = _make_direct_state()
    await handle_card_callback(cb, state)
    cb.answer.assert_awaited_once()


async def test_direct_card_callback_no_from_user() -> None:
    cb = _make_direct_cb("card:viewing:prop-42")
    cb.from_user = None
    state = _make_direct_state()
    await handle_card_callback(cb, state)
    cb.answer.assert_awaited_once()


async def test_direct_card_callback_viewing_with_dialog_manager() -> None:
    cb = _make_direct_cb("card:viewing:prop-42")
    state = _make_direct_state(
        {
            "apartment_results": [
                {
                    "id": "prop-42",
                    "payload": {
                        "complex_name": "X",
                        "property_type": "Apt",
                        "area_m2": 50,
                        "price_eur": 100000,
                    },
                }
            ]
        }
    )
    dialog_manager = AsyncMock()
    with patch(
        "telegram_bot.handlers.phone_collector.start_phone_collection", new_callable=AsyncMock
    ) as mock_phone:
        await handle_card_callback(cb, state, dialog_manager=dialog_manager)
        dialog_manager.start.assert_awaited_once()
        mock_phone.assert_not_awaited()


async def test_direct_card_callback_viewing_without_dialog_manager() -> None:
    cb = _make_direct_cb("card:viewing:prop-42")
    state = _make_direct_state(
        {
            "apartment_results": [
                {
                    "id": "prop-42",
                    "payload": {
                        "complex_name": "X",
                        "property_type": "Apt",
                        "area_m2": 50,
                        "price_eur": 100000,
                    },
                }
            ]
        }
    )
    with patch(
        "telegram_bot.handlers.phone_collector.start_phone_collection", new_callable=AsyncMock
    ) as mock_phone:
        await handle_card_callback(cb, state)
        mock_phone.assert_awaited_once()
        assert mock_phone.call_args.kwargs["service_key"] == "viewing"


async def test_direct_card_callback_ask_with_dialog_manager() -> None:
    cb = _make_direct_cb("card:ask:prop-42")
    state = _make_direct_state()
    dialog_manager = AsyncMock()
    with patch(
        "telegram_bot.handlers.phone_collector.start_phone_collection", new_callable=AsyncMock
    ) as mock_phone:
        await handle_card_callback(cb, state, dialog_manager=dialog_manager)
        dialog_manager.start.assert_awaited_once()
        mock_phone.assert_not_awaited()


async def test_direct_card_callback_ask_without_dialog_manager() -> None:
    cb = _make_direct_cb("card:ask:prop-42")
    state = _make_direct_state()
    with patch(
        "telegram_bot.handlers.phone_collector.start_phone_collection", new_callable=AsyncMock
    ) as mock_phone:
        await handle_card_callback(cb, state)
        mock_phone.assert_awaited_once()
        assert mock_phone.call_args.kwargs["service_key"] == "question"


async def test_direct_card_callback_matched_from_favorites() -> None:
    cb = _make_direct_cb("card:viewing:prop-42")
    state = _make_direct_state()
    favorites_service = MagicMock()
    mock_fav = MagicMock()
    mock_fav.property_id = "prop-42"
    mock_fav.property_data = {
        "complex_name": "Fav",
        "property_type": "Studio",
        "area_m2": 30,
        "price_eur": 50000,
    }
    favorites_service.list = AsyncMock(return_value=[mock_fav])
    with patch(
        "telegram_bot.handlers.phone_collector.start_phone_collection", new_callable=AsyncMock
    ) as mock_phone:
        await handle_card_callback(cb, state, favorites_service=favorites_service)
        mock_phone.assert_awaited_once()
        assert mock_phone.call_args.kwargs["viewing_objects"][0]["complex_name"] == "Fav"


async def test_direct_card_callback_control_message_delete() -> None:
    cb = _make_direct_cb("card:viewing:prop-42")
    cb.message.chat.id = 999
    state = _make_direct_state(
        {
            "catalog_runtime": {
                "results": [
                    {
                        "id": "prop-42",
                        "payload": {
                            "complex_name": "X",
                            "property_type": "Apt",
                            "area_m2": 50,
                            "price_eur": 100000,
                        },
                    }
                ],
                "control_message_id": 555,
            }
        }
    )
    dialog_manager = AsyncMock()
    await handle_card_callback(cb, state, dialog_manager=dialog_manager)
    cb.bot.delete_message.assert_awaited_once_with(999, 555)


async def test_direct_card_callback_unknown_action() -> None:
    cb = _make_direct_cb("card:unknown:prop-42")
    state = _make_direct_state()
    await handle_card_callback(cb, state)
    cb.answer.assert_awaited_once()


# create_results_callback_router
def test_create_results_callback_router() -> None:
    router = create_results_callback_router()
    assert router.name == "results_callbacks"

"""Unit tests for handle_favorite_callback metadata fix (#655)."""

from __future__ import annotations

import pytest


pytest.importorskip("aiogram", reason="aiogram not installed")

from unittest.mock import AsyncMock, MagicMock, patch

from telegram_bot.bot import PropertyBot
from telegram_bot.config import BotConfig


# ---------------------------------------------------------------------------
# Helpers (same pattern as test_results_callbacks.py)
# ---------------------------------------------------------------------------


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


def _make_callback(data: str = "fav:add:prop-42", user_id: int = 12345) -> MagicMock:
    cb = MagicMock()
    cb.data = data
    cb.from_user = MagicMock(id=user_id)
    cb.answer = AsyncMock()
    cb.message = MagicMock()
    cb.message.message_id = 100
    cb.message.answer = AsyncMock()
    cb.message.delete = AsyncMock()
    return cb


def _make_state(data: dict | None = None) -> MagicMock:
    state = MagicMock()
    state.get_data = AsyncMock(return_value=data or {})
    state.update_data = AsyncMock()
    state.clear = AsyncMock()
    return state


def _sample_result(property_id: str = "prop-42") -> dict:
    return {
        "id": property_id,
        "score": 0.95,
        "payload": {
            "complex_name": "Ocean Vista",
            "city": "Dubai",
            "property_type": "Studio",
            "floor": 5,
            "area_m2": 55,
            "view_tags": ["Sea", "Pool"],
            "view_primary": "Sea",
            "price_eur": 250000,
        },
    }


# ---------------------------------------------------------------------------
# Tests: fav:add with metadata
# ---------------------------------------------------------------------------


async def test_fav_add_saves_metadata() -> None:
    """State has matching result → property_data is built from payload."""
    bot = _create_bot()
    bot._favorites_service = MagicMock()
    bot._favorites_service.add = AsyncMock(return_value={"id": 1, "property_id": "prop-42"})

    result = _sample_result("prop-42")
    state = _make_state({"apartment_results": [result]})
    callback = _make_callback("fav:add:prop-42")

    await bot.handle_favorite_callback(callback, state)

    bot._favorites_service.add.assert_awaited_once()
    call_kwargs = bot._favorites_service.add.call_args.kwargs
    pd = call_kwargs["property_data"]
    assert pd["complex_name"] == "Ocean Vista"
    assert pd["price_eur"] == 250000
    assert pd["location"] == "Dubai"
    assert pd["area_m2"] == 55
    assert pd["floor"] == 5
    callback.answer.assert_awaited_once_with("Добавлено в закладки")


async def test_fav_add_no_state_fallback() -> None:
    """No apartment_results in state → property_data={}."""
    bot = _create_bot()
    bot._favorites_service = MagicMock()
    bot._favorites_service.add = AsyncMock(return_value={"id": 1, "property_id": "prop-42"})

    state = _make_state({})
    callback = _make_callback("fav:add:prop-42")

    await bot.handle_favorite_callback(callback, state)

    call_kwargs = bot._favorites_service.add.call_args.kwargs
    assert call_kwargs["property_data"] == {}


async def test_fav_add_uses_catalog_runtime_results() -> None:
    """Dialog-owned catalog flow should still provide property metadata for favorites."""
    bot = _create_bot()
    bot._favorites_service = MagicMock()
    bot._favorites_service.add = AsyncMock(return_value={"id": 1, "property_id": "prop-42"})

    state = _make_state({"catalog_runtime": {"results": [_sample_result("prop-42")]}})
    callback = _make_callback("fav:add:prop-42")

    await bot.handle_favorite_callback(callback, state)

    call_kwargs = bot._favorites_service.add.call_args.kwargs
    assert call_kwargs["property_data"]["complex_name"] == "Ocean Vista"


async def test_fav_add_none_state_fallback() -> None:
    """apartment_results=None in state → property_data={} (no crash)."""
    bot = _create_bot()
    bot._favorites_service = MagicMock()
    bot._favorites_service.add = AsyncMock(return_value={"id": 1, "property_id": "prop-42"})

    state = _make_state({"apartment_results": None})
    callback = _make_callback("fav:add:prop-42")

    await bot.handle_favorite_callback(callback, state)

    call_kwargs = bot._favorites_service.add.call_args.kwargs
    assert call_kwargs["property_data"] == {}


async def test_fav_add_property_not_found() -> None:
    """Results in state but no matching id → property_data={}."""
    bot = _create_bot()
    bot._favorites_service = MagicMock()
    bot._favorites_service.add = AsyncMock(return_value={"id": 1, "property_id": "prop-99"})

    state = _make_state({"apartment_results": [_sample_result("prop-10")]})
    callback = _make_callback("fav:add:prop-99")

    await bot.handle_favorite_callback(callback, state)

    call_kwargs = bot._favorites_service.add.call_args.kwargs
    assert call_kwargs["property_data"] == {}


async def test_fav_add_duplicate() -> None:
    """favorites_service.add returns None → 'Уже в закладках'."""
    bot = _create_bot()
    bot._favorites_service = MagicMock()
    bot._favorites_service.add = AsyncMock(return_value=None)

    state = _make_state({"apartment_results": [_sample_result("prop-42")]})
    callback = _make_callback("fav:add:prop-42")

    await bot.handle_favorite_callback(callback, state)

    callback.answer.assert_awaited_once_with("Уже в закладках")


# ---------------------------------------------------------------------------
# Tests: fav:remove
# ---------------------------------------------------------------------------


async def test_fav_remove_deletes_and_removes_message() -> None:
    """fav:remove from bookmarks (no apartment_results in state) → delete message."""
    bot = _create_bot()
    bot._favorites_service = MagicMock()
    bot._favorites_service.remove = AsyncMock()

    state = _make_state()  # empty = bookmarks context
    callback = _make_callback("fav:remove:prop-42")

    await bot.handle_favorite_callback(callback, state)

    bot._favorites_service.remove.assert_awaited_once_with(telegram_id=12345, property_id="prop-42")
    callback.message.delete.assert_awaited_once()
    callback.answer.assert_awaited_once_with("Удалено из закладок")


# ---------------------------------------------------------------------------
# Tests: Task 4 — toggle fav via edit_reply_markup (#705)
# ---------------------------------------------------------------------------


async def test_fav_add_toggles_reply_markup() -> None:
    """fav:add → edit_reply_markup с is_favorited=True."""
    bot = _create_bot()
    bot._favorites_service = MagicMock()
    bot._favorites_service.add = AsyncMock(return_value={"id": 1})

    state = _make_state({"apartment_results": [_sample_result("prop-42")]})
    callback = _make_callback("fav:add:prop-42")
    callback.message.edit_reply_markup = AsyncMock()

    await bot.handle_favorite_callback(callback, state)

    callback.message.edit_reply_markup.assert_awaited_once()
    kb = callback.message.edit_reply_markup.call_args.kwargs["reply_markup"]
    callbacks = [btn.callback_data for row in kb.inline_keyboard for btn in row]
    assert "fav:remove:prop-42" in callbacks
    assert "fav:add:prop-42" not in callbacks


async def test_fav_remove_toggles_reply_markup_in_search_results() -> None:
    """fav:remove from search results → edit_reply_markup, NOT delete message."""
    bot = _create_bot()
    bot._favorites_service = MagicMock()
    bot._favorites_service.remove = AsyncMock()

    state = _make_state({"apartment_results": [_sample_result("prop-42")]})
    callback = _make_callback("fav:remove:prop-42")
    callback.message.edit_reply_markup = AsyncMock()

    await bot.handle_favorite_callback(callback, state)

    bot._favorites_service.remove.assert_awaited_once()
    callback.message.edit_reply_markup.assert_awaited_once()
    callback.message.delete.assert_not_awaited()

    kb = callback.message.edit_reply_markup.call_args.kwargs["reply_markup"]
    callbacks = [btn.callback_data for row in kb.inline_keyboard for btn in row]
    assert "fav:add:prop-42" in callbacks


async def test_fav_remove_toggles_reply_markup_for_catalog_runtime_results() -> None:
    """Dialog-owned catalog results should be treated as search results, not bookmarks."""
    bot = _create_bot()
    bot._favorites_service = MagicMock()
    bot._favorites_service.remove = AsyncMock()

    state = _make_state({"catalog_runtime": {"results": [_sample_result("prop-42")]}})
    callback = _make_callback("fav:remove:prop-42")
    callback.message.edit_reply_markup = AsyncMock()

    await bot.handle_favorite_callback(callback, state)

    callback.message.edit_reply_markup.assert_awaited_once()
    callback.message.delete.assert_not_awaited()


async def test_fav_remove_deletes_when_message_is_from_bookmarks() -> None:
    """When callback message belongs to bookmarks, remove should delete card."""
    bot = _create_bot()
    bot._favorites_service = MagicMock()
    bot._favorites_service.remove = AsyncMock()

    state = _make_state(
        {
            "apartment_results": [_sample_result("prop-42")],
            "bookmark_message_ids": [100],
        }
    )
    callback = _make_callback("fav:remove:prop-42")
    callback.message.edit_reply_markup = AsyncMock()

    await bot.handle_favorite_callback(callback, state)

    callback.message.delete.assert_awaited_once()
    callback.message.edit_reply_markup.assert_not_awaited()


async def test_fav_toggle_handles_message_not_modified() -> None:
    """Double-tap race: MessageNotModified should not crash."""
    from aiogram.exceptions import TelegramBadRequest

    bot = _create_bot()
    bot._favorites_service = MagicMock()
    bot._favorites_service.add = AsyncMock(return_value={"id": 1})

    state = _make_state({"apartment_results": [_sample_result("prop-42")]})
    callback = _make_callback("fav:add:prop-42")
    callback.message.edit_reply_markup = AsyncMock(
        side_effect=TelegramBadRequest(method=MagicMock(), message="message is not modified")
    )

    await bot.handle_favorite_callback(callback, state)
    callback.answer.assert_awaited()


# ---------------------------------------------------------------------------
# Direct module-level handler tests (#1264)
# ---------------------------------------------------------------------------

from telegram_bot.handlers.favorites_callbacks import (
    create_favorites_router,
    handle_fav_add,
    handle_fav_remove,
    handle_fav_viewing,
    handle_fav_viewing_all,
    handle_favorite_callback,
)


def _make_direct_callback(data: str = "fav:add:prop-42", user_id: int = 12345) -> MagicMock:
    cb = MagicMock()
    cb.data = data
    cb.from_user = MagicMock(id=user_id)
    cb.answer = AsyncMock()
    cb.message = MagicMock()
    cb.message.message_id = 100
    cb.message.answer = AsyncMock()
    cb.message.delete = AsyncMock()
    cb.message.edit_reply_markup = AsyncMock()
    return cb


def _make_direct_state(data: dict | None = None) -> MagicMock:
    state = MagicMock()
    state.get_data = AsyncMock(return_value=data or {})
    state.update_data = AsyncMock()
    state.clear = AsyncMock()
    return state


def _make_direct_fav_cb(action: str = "add", apartment_id: str = "prop-42") -> MagicMock:
    cb = MagicMock()
    cb.action = action
    cb.apartment_id = apartment_id
    return cb


# handle_fav_add
async def test_direct_fav_add_no_user() -> None:
    cb = _make_direct_callback()
    cb.from_user = None
    state = _make_direct_state()
    await handle_fav_add(cb, state)
    cb.answer.assert_awaited_once()


async def test_direct_fav_add_missing_property_id() -> None:
    cb = _make_direct_callback()
    state = _make_direct_state()
    callback_data = _make_direct_fav_cb(action="add", apartment_id="")
    await handle_fav_add(cb, state, callback_data=callback_data)
    cb.answer.assert_awaited_once()


async def test_direct_fav_add_no_favorites_service() -> None:
    cb = _make_direct_callback()
    state = _make_direct_state()
    callback_data = _make_direct_fav_cb(action="add", apartment_id="prop-42")
    await handle_fav_add(cb, state, callback_data=callback_data, favorites_service=None)
    cb.answer.assert_awaited_once_with("Закладки недоступны")


async def test_direct_fav_add_success_with_metadata() -> None:
    cb = _make_direct_callback("fav:add:prop-42")
    state = _make_direct_state({"apartment_results": [_sample_result("prop-42")]})
    callback_data = _make_direct_fav_cb(action="add", apartment_id="prop-42")
    favorites_service = MagicMock()
    favorites_service.add = AsyncMock(return_value={"id": 1})
    await handle_fav_add(
        cb, state, callback_data=callback_data, favorites_service=favorites_service
    )
    favorites_service.add.assert_awaited_once()
    call_kwargs = favorites_service.add.call_args.kwargs
    assert call_kwargs["property_data"]["complex_name"] == "Ocean Vista"
    cb.answer.assert_awaited_once_with("Добавлено в закладки")


async def test_direct_fav_add_duplicate() -> None:
    cb = _make_direct_callback("fav:add:prop-42")
    state = _make_direct_state({"apartment_results": [_sample_result("prop-42")]})
    callback_data = _make_direct_fav_cb(action="add", apartment_id="prop-42")
    favorites_service = MagicMock()
    favorites_service.add = AsyncMock(return_value=None)
    await handle_fav_add(
        cb, state, callback_data=callback_data, favorites_service=favorites_service
    )
    cb.answer.assert_awaited_once_with("Уже в закладках")


async def test_direct_fav_add_catalog_runtime_results() -> None:
    cb = _make_direct_callback("fav:add:prop-42")
    state = _make_direct_state({"catalog_runtime": {"results": [_sample_result("prop-42")]}})
    callback_data = _make_direct_fav_cb(action="add", apartment_id="prop-42")
    favorites_service = MagicMock()
    favorites_service.add = AsyncMock(return_value={"id": 1})
    await handle_fav_add(
        cb, state, callback_data=callback_data, favorites_service=favorites_service
    )
    call_kwargs = favorites_service.add.call_args.kwargs
    assert call_kwargs["property_data"]["complex_name"] == "Ocean Vista"


# handle_fav_remove
async def test_direct_fav_remove_no_user() -> None:
    cb = _make_direct_callback("fav:remove:prop-42")
    cb.from_user = None
    state = _make_direct_state()
    await handle_fav_remove(cb, state)
    cb.answer.assert_awaited_once()


async def test_direct_fav_remove_missing_property_id() -> None:
    cb = _make_direct_callback("fav:remove:prop-42")
    state = _make_direct_state()
    callback_data = _make_direct_fav_cb(action="remove", apartment_id="")
    await handle_fav_remove(cb, state, callback_data=callback_data)
    cb.answer.assert_awaited_once()


async def test_direct_fav_remove_no_favorites_service() -> None:
    cb = _make_direct_callback("fav:remove:prop-42")
    state = _make_direct_state()
    callback_data = _make_direct_fav_cb(action="remove", apartment_id="prop-42")
    await handle_fav_remove(cb, state, callback_data=callback_data, favorites_service=None)
    cb.answer.assert_awaited_once_with("Закладки недоступны")


async def test_direct_fav_remove_in_search_results() -> None:
    cb = _make_direct_callback("fav:remove:prop-42")
    state = _make_direct_state({"apartment_results": [_sample_result("prop-42")]})
    callback_data = _make_direct_fav_cb(action="remove", apartment_id="prop-42")
    favorites_service = MagicMock()
    favorites_service.remove = AsyncMock()
    await handle_fav_remove(
        cb, state, callback_data=callback_data, favorites_service=favorites_service
    )
    favorites_service.remove.assert_awaited_once()
    cb.message.edit_reply_markup.assert_awaited_once()
    cb.answer.assert_awaited_once_with("Удалено из закладок")


async def test_direct_fav_remove_bookmark_message() -> None:
    cb = _make_direct_callback("fav:remove:prop-42")
    cb.message.message_id = 200
    state = _make_direct_state({"bookmark_message_ids": [200]})
    callback_data = _make_direct_fav_cb(action="remove", apartment_id="prop-42")
    favorites_service = MagicMock()
    favorites_service.remove = AsyncMock()
    await handle_fav_remove(
        cb, state, callback_data=callback_data, favorites_service=favorites_service
    )
    cb.message.delete.assert_awaited_once()
    cb.answer.assert_awaited_once_with("Удалено из закладок")


# handle_fav_viewing
async def test_direct_fav_viewing_no_user() -> None:
    cb = _make_direct_callback("fav:viewing:prop-42")
    cb.from_user = None
    state = _make_direct_state()
    callback_data = _make_direct_fav_cb(action="viewing", apartment_id="prop-42")
    await handle_fav_viewing(cb, state, callback_data=callback_data)
    cb.answer.assert_awaited_once()


async def test_direct_fav_viewing_missing_property_id() -> None:
    cb = _make_direct_callback("fav:viewing:prop-42")
    state = _make_direct_state()
    callback_data = _make_direct_fav_cb(action="viewing", apartment_id="")
    await handle_fav_viewing(cb, state, callback_data=callback_data)
    cb.answer.assert_awaited_once()


async def test_direct_fav_viewing_no_favorites_service() -> None:
    cb = _make_direct_callback("fav:viewing:prop-42")
    state = _make_direct_state()
    callback_data = _make_direct_fav_cb(action="viewing", apartment_id="prop-42")
    with patch(
        "telegram_bot.handlers.phone_collector.start_phone_collection", new_callable=AsyncMock
    ) as mock_phone:
        await handle_fav_viewing(cb, state, callback_data=callback_data, favorites_service=None)
        mock_phone.assert_awaited_once()
        assert mock_phone.call_args.kwargs["viewing_objects"] == []


async def test_direct_fav_viewing_success() -> None:
    cb = _make_direct_callback("fav:viewing:prop-42")
    state = _make_direct_state()
    callback_data = _make_direct_fav_cb(action="viewing", apartment_id="prop-42")
    favorites_service = MagicMock()
    mock_fav = MagicMock()
    mock_fav.property_id = "prop-42"
    mock_fav.property_data = {
        "complex_name": "Test Property",
        "property_type": "Apartment",
        "area_m2": 50,
        "price_eur": 100000,
    }
    favorites_service.list = AsyncMock(return_value=[mock_fav])
    with patch(
        "telegram_bot.handlers.phone_collector.start_phone_collection", new_callable=AsyncMock
    ) as mock_phone:
        await handle_fav_viewing(
            cb, state, callback_data=callback_data, favorites_service=favorites_service
        )
        mock_phone.assert_awaited_once()
        assert len(mock_phone.call_args.kwargs["viewing_objects"]) == 1
        assert mock_phone.call_args.kwargs["service_key"] == "viewing"


# handle_fav_viewing_all
async def test_direct_fav_viewing_all_no_user() -> None:
    cb = _make_direct_callback("fav:viewing_all")
    cb.from_user = None
    state = _make_direct_state()
    await handle_fav_viewing_all(cb, state)
    cb.answer.assert_awaited_once()


async def test_direct_fav_viewing_all_no_favorites_service() -> None:
    cb = _make_direct_callback("fav:viewing_all")
    state = _make_direct_state()
    with patch(
        "telegram_bot.handlers.phone_collector.start_phone_collection", new_callable=AsyncMock
    ) as mock_phone:
        await handle_fav_viewing_all(cb, state, favorites_service=None)
        mock_phone.assert_awaited_once()
        assert mock_phone.call_args.kwargs["viewing_objects"] == []


async def test_direct_fav_viewing_all_success() -> None:
    cb = _make_direct_callback("fav:viewing_all")
    state = _make_direct_state()
    favorites_service = MagicMock()
    mock_fav = MagicMock()
    mock_fav.property_id = "prop-1"
    mock_fav.property_data = {
        "complex_name": "Test Property",
        "property_type": "Apartment",
        "area_m2": 50,
        "price_eur": 100000,
    }
    favorites_service.list = AsyncMock(return_value=[mock_fav])
    with patch(
        "telegram_bot.handlers.phone_collector.start_phone_collection", new_callable=AsyncMock
    ) as mock_phone:
        await handle_fav_viewing_all(cb, state, favorites_service=favorites_service)
        mock_phone.assert_awaited_once()
        assert len(mock_phone.call_args.kwargs["viewing_objects"]) == 1
        assert mock_phone.call_args.kwargs["service_key"] == "viewing"


# handle_favorite_callback
async def test_direct_handle_favorite_callback_malformed_data() -> None:
    cb = _make_direct_callback("fav")
    state = _make_direct_state()
    await handle_favorite_callback(cb, state)
    cb.answer.assert_awaited_once()


async def test_direct_handle_favorite_callback_unknown_action() -> None:
    cb = _make_direct_callback("fav:unknown:prop-42")
    state = _make_direct_state()
    await handle_favorite_callback(cb, state)
    cb.answer.assert_awaited_once()


async def test_direct_handle_favorite_callback_add() -> None:
    cb = _make_direct_callback("fav:add:prop-42")
    state = _make_direct_state({"apartment_results": [_sample_result("prop-42")]})
    favorites_service = MagicMock()
    favorites_service.add = AsyncMock(return_value={"id": 1})
    await handle_favorite_callback(cb, state, favorites_service=favorites_service)
    favorites_service.add.assert_awaited_once()


async def test_direct_handle_favorite_callback_remove() -> None:
    cb = _make_direct_callback("fav:remove:prop-42")
    state = _make_direct_state({"apartment_results": [_sample_result("prop-42")]})
    favorites_service = MagicMock()
    favorites_service.remove = AsyncMock()
    await handle_favorite_callback(cb, state, favorites_service=favorites_service)
    favorites_service.remove.assert_awaited_once()


async def test_direct_handle_favorite_callback_viewing() -> None:
    cb = _make_direct_callback("fav:viewing:prop-42")
    state = _make_direct_state()
    favorites_service = MagicMock()
    mock_fav = MagicMock()
    mock_fav.property_id = "prop-42"
    mock_fav.property_data = {
        "complex_name": "Test",
        "property_type": "Apt",
        "area_m2": 50,
        "price_eur": 100000,
    }
    favorites_service.list = AsyncMock(return_value=[mock_fav])
    with patch(
        "telegram_bot.handlers.phone_collector.start_phone_collection", new_callable=AsyncMock
    ) as mock_phone:
        await handle_favorite_callback(cb, state, favorites_service=favorites_service)
        mock_phone.assert_awaited_once()


async def test_direct_handle_favorite_callback_viewing_all() -> None:
    cb = _make_direct_callback("fav:viewing_all")
    state = _make_direct_state()
    favorites_service = MagicMock()
    favorites_service.list = AsyncMock(return_value=[])
    with patch(
        "telegram_bot.handlers.phone_collector.start_phone_collection", new_callable=AsyncMock
    ) as mock_phone:
        await handle_favorite_callback(cb, state, favorites_service=favorites_service)
        mock_phone.assert_awaited_once()


# create_favorites_router
def test_create_favorites_router() -> None:
    router = create_favorites_router()
    assert router.name == "favorites"

"""Unit tests for handle_results_callback (#654)."""

from __future__ import annotations

import pytest


pytest.importorskip("aiogram", reason="aiogram not installed")

from unittest.mock import AsyncMock, MagicMock, patch

from telegram_bot.bot import PropertyBot
from telegram_bot.config import BotConfig


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_PAGE_SIZE = 5  # must match _APARTMENT_PAGE_SIZE in bot.py


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
    cb.message.answer_photo = AsyncMock()
    cb.message.answer_media_group = AsyncMock()
    cb.message.delete = AsyncMock()
    return cb


def _make_state(data: dict | None = None) -> MagicMock:
    state = MagicMock()
    state.get_data = AsyncMock(return_value=data or {})
    state.update_data = AsyncMock()
    state.clear = AsyncMock()
    return state


def _make_results(n: int = 8) -> list[dict]:
    return [
        {
            "id": f"prop-{i}",
            "score": 0.9 - i * 0.01,
            "payload": {
                "complex_name": f"Complex {i}",
                "city": "Dubai",
                "property_type": "Apartment",
                "floor": i + 1,
                "area_m2": 60 + i * 5,
                "view_tags": ["Sea"],
                "view_primary": "Sea",
                "price_eur": 200000 + i * 10000,
            },
        }
        for i in range(n)
    ]


# ---------------------------------------------------------------------------
# Tests: results:more
# ---------------------------------------------------------------------------


async def test_results_more_shows_next_page() -> None:
    """8 results, offset=0 → sends 3 cards + 1 footer, updates offset to PAGE_SIZE."""
    bot = _create_bot()
    bot._send_property_card = AsyncMock()
    results = _make_results(8)
    state = _make_state({"apartment_results": results, "apartment_offset": 0})
    callback = _make_callback("results:more")

    await bot.handle_results_callback(callback, state)

    # 3 remaining cards via helper + 1 footer message via answer
    assert bot._send_property_card.await_count == 3
    assert callback.message.answer.await_count == 1
    state.update_data.assert_awaited_once_with(apartment_offset=_PAGE_SIZE)
    callback.answer.assert_awaited_once_with()


async def test_results_more_no_results_in_state() -> None:
    """No apartment_results in state → answer with error message."""
    bot = _create_bot()
    bot._send_property_card = AsyncMock()
    state = _make_state({})
    callback = _make_callback("results:more")

    await bot.handle_results_callback(callback, state)

    callback.answer.assert_awaited_once_with("Нет сохранённых результатов")
    callback.message.answer.assert_not_called()
    bot._send_property_card.assert_not_awaited()


async def test_results_more_exhausted() -> None:
    """offset == len(results) → answer 'all shown'."""
    bot = _create_bot()
    bot._send_property_card = AsyncMock()
    results = _make_results(5)
    state = _make_state({"apartment_results": results, "apartment_offset": 5})
    callback = _make_callback("results:more")

    await bot.handle_results_callback(callback, state)

    callback.answer.assert_awaited_once_with("Все результаты уже показаны")
    callback.message.answer.assert_not_called()
    bot._send_property_card.assert_not_awaited()


async def test_results_more_fetches_next_scroll_page_for_funnel_state() -> None:
    """When funnel stored only first page, results:more loads next page from scroll API."""
    bot = _create_bot()
    bot._send_property_card = AsyncMock()
    all_results = _make_results(8)
    first_page = all_results[:_PAGE_SIZE]
    next_page = all_results[_PAGE_SIZE:]
    bot._apartments_service = MagicMock()
    bot._apartments_service.scroll_with_filters = AsyncMock(return_value=(next_page, 8, None))

    state = _make_state(
        {
            "apartment_results": first_page,
            "apartment_offset": 0,
            "apartment_total": 8,
            "apartment_next_offset": "offset-2",
            "apartment_filters": {"city": "Бургас"},
        }
    )
    callback = _make_callback("results:more")

    await bot.handle_results_callback(callback, state)

    bot._apartments_service.scroll_with_filters.assert_awaited_once_with(
        filters={"city": "Бургас"},
        limit=_PAGE_SIZE,
        offset="offset-2",
    )
    assert bot._send_property_card.await_count == 3
    assert callback.message.answer.await_count == 1
    assert state.update_data.await_count == 2
    first_call = state.update_data.await_args_list[0].kwargs
    assert first_call["apartment_total"] == 8
    assert first_call["apartment_next_offset"] is None
    assert len(first_call["apartment_results"]) == 8
    second_call = state.update_data.await_args_list[1].kwargs
    assert second_call == {"apartment_offset": _PAGE_SIZE}
    callback.answer.assert_awaited_once_with()


async def test_results_more_backfills_from_start_when_next_offset_missing() -> None:
    """If next_offset is None but total_count says more, fetch wider prefix and avoid duplicates."""
    bot = _create_bot()
    bot._send_property_card = AsyncMock()
    all_results = _make_results(8)
    first_page = all_results[:_PAGE_SIZE]
    bot._apartments_service = MagicMock()
    bot._apartments_service.scroll_with_filters = AsyncMock(return_value=(all_results, 8, None))

    state = _make_state(
        {
            "apartment_results": first_page,
            "apartment_offset": 0,
            "apartment_total": 8,
            "apartment_next_offset": None,
            "apartment_filters": {"city": "Бургас"},
        }
    )
    callback = _make_callback("results:more")

    await bot.handle_results_callback(callback, state)

    bot._apartments_service.scroll_with_filters.assert_awaited_once_with(
        filters={"city": "Бургас"},
        limit=_PAGE_SIZE * 2,
        offset=None,
    )
    sent_ids = [call.args[1]["id"] for call in bot._send_property_card.await_args_list]
    assert sent_ids == ["prop-5", "prop-6", "prop-7"]
    first_call = state.update_data.await_args_list[0].kwargs
    assert len(first_call["apartment_results"]) == 8


# ---------------------------------------------------------------------------
# Tests: results:refine
# ---------------------------------------------------------------------------


async def test_results_refine_clears_state() -> None:
    """results:refine → clears results from state, sends prompt, answers callback."""
    bot = _create_bot()
    state = _make_state({"apartment_results": _make_results(3)})
    callback = _make_callback("results:refine")

    await bot.handle_results_callback(callback, state)

    state.update_data.assert_awaited_once_with(apartment_results=None, apartment_offset=0)
    callback.message.answer.assert_awaited_once()
    callback.answer.assert_awaited_once_with()


# ---------------------------------------------------------------------------
# Tests: results:viewing
# ---------------------------------------------------------------------------


async def test_results_viewing_delegates() -> None:
    """results:viewing → starts ViewingSG.date dialog via dialog_manager."""
    bot = _create_bot()
    state = _make_state({"apartment_results": _make_results(3)})
    callback = _make_callback("results:viewing")
    dialog_manager = AsyncMock()

    await bot.handle_results_callback(callback, state, dialog_manager=dialog_manager)

    dialog_manager.start.assert_awaited_once()
    from telegram_bot.dialogs.states import ViewingSG

    call_args = dialog_manager.start.call_args
    assert call_args.args[0] == ViewingSG.date
    start_data = call_args.kwargs.get("data", {})
    assert "selected_objects" in start_data


async def test_results_viewing_fallback_phone_collector() -> None:
    """results:viewing without dialog_manager → falls back to start_phone_collection."""
    bot = _create_bot()
    state = _make_state()
    callback = _make_callback("results:viewing")

    with patch(
        "telegram_bot.handlers.phone_collector.start_phone_collection",
        new=AsyncMock(),
    ) as mock_collect:
        await bot.handle_results_callback(callback, state)

    mock_collect.assert_awaited_once()


# ---------------------------------------------------------------------------
# Tests: unknown action
# ---------------------------------------------------------------------------


async def test_results_unknown_action() -> None:
    """Unknown results: action → just answer callback."""
    bot = _create_bot()
    state = _make_state()
    callback = _make_callback("results:unknown_xyz")

    await bot.handle_results_callback(callback, state)

    callback.answer.assert_awaited_once()
    callback.message.answer.assert_not_called()

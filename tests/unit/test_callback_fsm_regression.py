"""Callback/FSM transition regression suite (#664).

Tests cross-callback flows, malformed-state resilience, and footer contract.
Prevents regressions similar to PR #661/#663.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest


pytest.importorskip("aiogram", reason="aiogram not installed")

from unittest.mock import AsyncMock, MagicMock, patch

from telegram_bot.bot import PropertyBot
from telegram_bot.config import BotConfig


# ---------------------------------------------------------------------------
# Helpers (same pattern as existing callback tests)
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


def _make_callback(data: str, user_id: int = 12345) -> MagicMock:
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


def _make_results(n: int) -> list[dict]:
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


def _make_favorite(property_id: str, **data: object) -> SimpleNamespace:
    """Create a fake Favorite object for tests."""
    return SimpleNamespace(
        property_id=property_id,
        property_data={
            "complex_name": data.get("complex_name", "Test Complex"),
            "property_type": data.get("property_type", "Apartment"),
            "area_m2": data.get("area_m2", 60),
            "price_eur": data.get("price_eur", 200000),
        },
    )


def _fav_bot(favorites: list | None = None) -> PropertyBot:
    """Create bot with favorites_service mock pre-wired."""
    bot = _create_bot()
    bot._favorites_service = MagicMock()
    bot._favorites_service.add = AsyncMock(return_value={"id": 1, "property_id": "prop-0"})
    bot._favorites_service.remove = AsyncMock()
    bot._favorites_service.list = AsyncMock(return_value=favorites or [])
    return bot


# ---------------------------------------------------------------------------
# 1. Callback-flow: stale legacy results callbacks
# ---------------------------------------------------------------------------


class TestLegacyResultsCompat:
    """Legacy results buttons should only show stale compatibility guidance."""

    async def test_results_more_is_stale_when_results_exist(self) -> None:
        bot = _create_bot()
        bot._send_property_card = AsyncMock()
        state = _make_state({"apartment_results": _make_results(12), "apartment_offset": 0})
        cb = _make_callback("results:more")

        await bot.handle_results_callback(cb, state)

        cb.message.answer.assert_awaited_once_with(
            "Это устаревшая кнопка. Используйте актуальное меню ниже."
        )
        state.update_data.assert_not_awaited()
        bot._send_property_card.assert_not_awaited()

    async def test_results_more_is_stale_at_end_of_legacy_state(self) -> None:
        bot = _create_bot()
        bot._send_property_card = AsyncMock()
        state = _make_state({"apartment_results": _make_results(12), "apartment_offset": 10})
        cb = _make_callback("results:more")

        await bot.handle_results_callback(cb, state)

        cb.message.answer.assert_awaited_once_with(
            "Это устаревшая кнопка. Используйте актуальное меню ниже."
        )
        bot._send_property_card.assert_not_awaited()

    async def test_results_more_is_stale_without_results(self) -> None:
        bot = _create_bot()
        state = _make_state({"apartment_results": None, "apartment_offset": 0})
        cb = _make_callback("results:more")

        await bot.handle_results_callback(cb, state)

        cb.message.answer.assert_awaited_once_with(
            "Это устаревшая кнопка. Используйте актуальное меню ниже."
        )


# ---------------------------------------------------------------------------
# 2. Callback-flow: refine -> stale fav:add (stale-button scenario)
# ---------------------------------------------------------------------------


class TestRefineStaleButton:
    """Reproduce stale-button scenario: refine clears state, old fav:add follows."""

    async def test_refine_then_stale_fav_add_no_crash(self) -> None:
        """After refine (apartment_results=None), stale fav:add -> no crash."""
        bot = _fav_bot()
        # State after refine: apartment_results=None, apartment_offset=0
        state = _make_state({"apartment_results": None, "apartment_offset": 0})
        cb = _make_callback("fav:add:prop-0")

        # Should not raise
        await bot.handle_favorite_callback(cb, state)

        call_kwargs = bot._favorites_service.add.call_args.kwargs
        assert call_kwargs["property_data"] == {}
        cb.answer.assert_awaited_once_with(
            "\u0414\u043e\u0431\u0430\u0432\u043b\u0435\u043d\u043e \u0432 \u0437\u0430\u043a\u043b\u0430\u0434\u043a\u0438"
        )

    async def test_refine_clears_then_more_fails_gracefully(self) -> None:
        """After refine, stale more button still gets compat guidance, not old pagination."""
        bot = _create_bot()
        state = _make_state({"apartment_results": None, "apartment_offset": 0})
        cb = _make_callback("results:more")

        await bot.handle_results_callback(cb, state)

        cb.message.answer.assert_awaited_once_with(
            "Это устаревшая кнопка. Используйте актуальное меню ниже."
        )


# ---------------------------------------------------------------------------
# 3. Callback-flow: viewing -> phone collector contract
# ---------------------------------------------------------------------------


class TestViewingDialog:
    """Legacy results:viewing should be compat-only; favorites still open ViewingSG."""

    async def test_results_viewing_starts_dialog(self) -> None:
        """results:viewing should no longer enter ViewingSG."""
        bot = _create_bot()
        state = _make_state()
        cb = _make_callback("results:viewing")
        dialog_manager = AsyncMock()

        await bot.handle_results_callback(cb, state, dialog_manager=dialog_manager)

        dialog_manager.start.assert_not_awaited()
        cb.message.answer.assert_awaited_once_with(
            "Это устаревшая кнопка. Используйте актуальное меню ниже."
        )

    async def test_results_viewing_fallback_no_dialog_manager(self) -> None:
        """results:viewing without dialog_manager should not reach phone_collector anymore."""
        bot = _create_bot()
        state = _make_state()
        cb = _make_callback("results:viewing")

        with patch(
            "telegram_bot.handlers.phone_collector.start_phone_collection",
            new=AsyncMock(),
        ) as mock_collect:
            await bot.handle_results_callback(cb, state)

        mock_collect.assert_not_awaited()
        cb.message.answer.assert_awaited_once_with(
            "Это устаревшая кнопка. Используйте актуальное меню ниже."
        )

    async def test_fav_viewing_starts_dialog(self) -> None:
        """fav:viewing:prop-42 -> dialog_manager.start(ViewingSG.date, data={selected_objects})."""
        fav = _make_favorite("prop-42", complex_name="Ocean View", area_m2=75, price_eur=300000)
        bot = _fav_bot(favorites=[fav])
        state = _make_state()
        cb = _make_callback("fav:viewing:prop-42")
        dialog_manager = AsyncMock()

        await bot.handle_favorite_callback(cb, state, dialog_manager=dialog_manager)

        dialog_manager.start.assert_awaited_once()
        from telegram_bot.dialogs.states import ViewingSG

        assert dialog_manager.start.call_args.args[0] == ViewingSG.date
        start_data = dialog_manager.start.call_args.kwargs.get("data", {})
        viewing_objects = start_data.get("selected_objects", [])
        assert len(viewing_objects) == 1
        assert viewing_objects[0]["id"] == "prop-42"
        assert viewing_objects[0]["complex_name"] == "Ocean View"
        assert viewing_objects[0]["area_m2"] == 75
        assert viewing_objects[0]["price_eur"] == 300000

    async def test_fav_viewing_all_starts_dialog(self) -> None:
        """fav:viewing_all -> dialog_manager.start(ViewingSG.date, data={selected_objects})."""
        favs = [
            _make_favorite("prop-1", complex_name="Complex A", area_m2=60, price_eur=200000),
            _make_favorite("prop-2", complex_name="Complex B", area_m2=80, price_eur=350000),
        ]
        bot = _fav_bot(favorites=favs)
        state = _make_state()
        cb = _make_callback("fav:viewing_all")
        dialog_manager = AsyncMock()

        await bot.handle_favorite_callback(cb, state, dialog_manager=dialog_manager)

        dialog_manager.start.assert_awaited_once()
        from telegram_bot.dialogs.states import ViewingSG

        assert dialog_manager.start.call_args.args[0] == ViewingSG.date
        start_data = dialog_manager.start.call_args.kwargs.get("data", {})
        viewing_objects = start_data.get("selected_objects", [])
        assert len(viewing_objects) == 2
        assert viewing_objects[0]["id"] == "prop-1"
        assert viewing_objects[1]["id"] == "prop-2"


# ---------------------------------------------------------------------------
# 4. Malformed-state matrix: fav:add resilience
# ---------------------------------------------------------------------------


class TestMalformedStateFavAdd:
    """Malformed apartment_results must not crash, should yield empty metadata."""

    @pytest.mark.parametrize(
        "bad_results",
        [None, {"not": "a list"}, 42, "string", True],
        ids=["none", "dict", "int", "string", "bool"],
    )
    async def test_non_list_apartment_results(self, bad_results: object) -> None:
        """Non-list apartment_results -> no crash, property_data={}."""
        bot = _fav_bot()
        state = _make_state({"apartment_results": bad_results})
        cb = _make_callback("fav:add:prop-0")

        await bot.handle_favorite_callback(cb, state)

        call_kwargs = bot._favorites_service.add.call_args.kwargs
        assert call_kwargs["property_data"] == {}

    async def test_mixed_list_entries_finds_valid(self) -> None:
        """List with [None, 42, valid_dict, 'str'] -> finds valid dict match."""
        bot = _fav_bot()
        valid = {
            "id": "prop-0",
            "payload": {
                "complex_name": "Tower A",
                "city": "Dubai",
                "property_type": "Studio",
                "floor": 3,
                "area_m2": 40,
                "view_tags": ["Garden"],
                "price_eur": 150000,
            },
        }
        mixed: list = [None, 42, valid, "bad-entry"]
        state = _make_state({"apartment_results": mixed})
        cb = _make_callback("fav:add:prop-0")

        await bot.handle_favorite_callback(cb, state)

        call_kwargs = bot._favorites_service.add.call_args.kwargs
        assert call_kwargs["property_data"]["complex_name"] == "Tower A"
        assert call_kwargs["property_data"]["price_eur"] == 150000

    async def test_payload_missing(self) -> None:
        """Result dict without 'payload' key -> no crash, empty metadata."""
        bot = _fav_bot()
        result_no_payload = {"id": "prop-0", "score": 0.9}
        state = _make_state({"apartment_results": [result_no_payload]})
        cb = _make_callback("fav:add:prop-0")

        await bot.handle_favorite_callback(cb, state)

        call_kwargs = bot._favorites_service.add.call_args.kwargs
        assert call_kwargs["property_data"] == {}

    @pytest.mark.parametrize(
        "bad_payload",
        [None, 42, "string", []],
        ids=["none", "int", "string", "list"],
    )
    async def test_payload_non_dict(self, bad_payload: object) -> None:
        """Non-dict payload -> no crash, empty metadata."""
        bot = _fav_bot()
        result = {"id": "prop-0", "score": 0.9, "payload": bad_payload}
        state = _make_state({"apartment_results": [result]})
        cb = _make_callback("fav:add:prop-0")

        await bot.handle_favorite_callback(cb, state)

        call_kwargs = bot._favorites_service.add.call_args.kwargs
        assert call_kwargs["property_data"] == {}


# ---------------------------------------------------------------------------
# 5. Legacy results footer contract removed
# ---------------------------------------------------------------------------


class TestFooterContract:
    """Legacy footer flows should now only point users to the fresh catalog controls."""

    @pytest.mark.parametrize("total,offset", [(12, 0), (12, 5), (10, 0), (6, 0), (7, 0)])
    async def test_results_more_always_returns_stale_guidance(
        self,
        total: int,
        offset: int,
    ) -> None:
        bot = _create_bot()
        bot._send_property_card = AsyncMock()
        results = _make_results(total)
        state = _make_state({"apartment_results": results, "apartment_offset": offset})
        cb = _make_callback("results:more")

        await bot.handle_results_callback(cb, state)

        cb.message.answer.assert_awaited_once_with(
            "Это устаревшая кнопка. Используйте актуальное меню ниже."
        )
        bot._send_property_card.assert_not_awaited()

    async def test_results_more_does_not_emit_partial_page_cards(self) -> None:
        bot = _create_bot()
        bot._send_property_card = AsyncMock()
        state = _make_state({"apartment_results": _make_results(7), "apartment_offset": 0})
        cb = _make_callback("results:more")

        await bot.handle_results_callback(cb, state)

        assert bot._send_property_card.await_args_list == []

    async def test_single_result_legacy_button_uses_stale_guidance(self) -> None:
        bot = _create_bot()
        bot._send_property_card = AsyncMock()
        state = _make_state({"apartment_results": _make_results(1), "apartment_offset": 0})
        cb = _make_callback("results:more")

        await bot.handle_results_callback(cb, state)

        cb.message.answer.assert_awaited_once_with(
            "Это устаревшая кнопка. Используйте актуальное меню ниже."
        )

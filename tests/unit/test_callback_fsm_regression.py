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
# 1. Callback-flow: multi-page pagination (results:more)
# ---------------------------------------------------------------------------


class TestMultiPagePagination:
    """Verify pagination across multiple results:more clicks."""

    async def test_page2_of_12_shows_5_cards_and_has_more(self) -> None:
        """12 results, offset=0 -> page2: 5 cards + footer, has_more=True."""
        bot = _create_bot()
        results = _make_results(12)
        state = _make_state({"apartment_results": results, "apartment_offset": 0})
        cb = _make_callback("results:more")

        await bot.handle_results_callback(cb, state)

        assert cb.message.answer_photo.await_count == 5
        assert cb.message.answer.await_count == 1
        state.update_data.assert_awaited_once_with(apartment_offset=_PAGE_SIZE)
        footer_call = cb.message.answer.call_args
        assert "показаны 6–10" in footer_call.args[0]

    async def test_page3_of_12_shows_2_cards_no_more(self) -> None:
        """12 results, offset=5 -> page3: 2 cards + footer, has_more=False."""
        bot = _create_bot()
        results = _make_results(12)
        state = _make_state({"apartment_results": results, "apartment_offset": 5})
        cb = _make_callback("results:more")

        await bot.handle_results_callback(cb, state)

        assert cb.message.answer_photo.await_count == 2
        assert cb.message.answer.await_count == 1
        state.update_data.assert_awaited_once_with(apartment_offset=10)
        footer_call = cb.message.answer.call_args
        assert "показаны 11–12" in footer_call.args[0]

    async def test_page4_of_12_exhausted(self) -> None:
        """12 results, offset=10 -> new_offset=15 >= 12 -> 'all shown'."""
        bot = _create_bot()
        results = _make_results(12)
        state = _make_state({"apartment_results": results, "apartment_offset": 10})
        cb = _make_callback("results:more")

        await bot.handle_results_callback(cb, state)

        cb.answer.assert_awaited_once_with(
            "\u0412\u0441\u0435 \u0440\u0435\u0437\u0443\u043b\u044c\u0442\u0430\u0442\u044b \u0443\u0436\u0435 \u043f\u043e\u043a\u0430\u0437\u0430\u043d\u044b"
        )
        cb.message.answer.assert_not_called()
        cb.message.answer_photo.assert_not_called()

    async def test_exact_boundary_10_results(self) -> None:
        """10 results, offset=0 -> page2: 5 cards, has_more=False."""
        bot = _create_bot()
        results = _make_results(10)
        state = _make_state({"apartment_results": results, "apartment_offset": 0})
        cb = _make_callback("results:more")

        await bot.handle_results_callback(cb, state)

        assert cb.message.answer_photo.await_count == 5
        assert cb.message.answer.await_count == 1
        footer_call = cb.message.answer.call_args
        assert "показаны 6–10" in footer_call.args[0]


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
        """After refine, results:more -> 'no results' (not crash)."""
        bot = _create_bot()
        state = _make_state({"apartment_results": None, "apartment_offset": 0})
        cb = _make_callback("results:more")

        await bot.handle_results_callback(cb, state)

        cb.answer.assert_awaited_once_with(
            "\u041d\u0435\u0442 \u0441\u043e\u0445\u0440\u0430\u043d\u0451\u043d\u043d\u044b\u0445 \u0440\u0435\u0437\u0443\u043b\u044c\u0442\u0430\u0442\u043e\u0432"
        )


# ---------------------------------------------------------------------------
# 3. Callback-flow: viewing -> phone collector contract
# ---------------------------------------------------------------------------


class TestViewingPhoneCollector:
    """Contract: viewing delegates to phone_collector with correct kwargs."""

    async def test_results_viewing_passes_source_results(self) -> None:
        """results:viewing -> start_phone_collection(service_key='viewing', viewing_objects=None)."""
        bot = _create_bot()
        state = _make_state()  # empty state -> no apartment_results
        cb = _make_callback("results:viewing")

        with patch(
            "telegram_bot.handlers.phone_collector.start_phone_collection",
            new=AsyncMock(),
        ) as mock_collect:
            await bot.handle_results_callback(cb, state)

        mock_collect.assert_awaited_once_with(
            cb, state, service_key="viewing", viewing_objects=None
        )

    async def test_fav_viewing_passes_property_id(self) -> None:
        """fav:viewing:prop-42 -> service_key='viewing', viewing_objects with matched favorite."""
        fav = _make_favorite("prop-42", complex_name="Ocean View", area_m2=75, price_eur=300000)
        bot = _fav_bot(favorites=[fav])
        state = _make_state()
        cb = _make_callback("fav:viewing:prop-42")

        with patch(
            "telegram_bot.handlers.phone_collector.start_phone_collection",
            new=AsyncMock(),
        ) as mock_collect:
            await bot.handle_favorite_callback(cb, state)

        mock_collect.assert_awaited_once_with(
            cb,
            state,
            service_key="viewing",
            viewing_objects=[
                {
                    "id": "prop-42",
                    "complex_name": "Ocean View",
                    "property_type": "Apartment",
                    "area_m2": 75,
                    "price_eur": 300000,
                }
            ],
        )

    async def test_fav_viewing_all_passes_correct_kwargs(self) -> None:
        """fav:viewing_all -> service_key='viewing', viewing_objects with all favorites."""
        favs = [
            _make_favorite("prop-1", complex_name="Complex A", area_m2=60, price_eur=200000),
            _make_favorite("prop-2", complex_name="Complex B", area_m2=80, price_eur=350000),
        ]
        bot = _fav_bot(favorites=favs)
        state = _make_state()
        cb = _make_callback("fav:viewing_all")

        with patch(
            "telegram_bot.handlers.phone_collector.start_phone_collection",
            new=AsyncMock(),
        ) as mock_collect:
            await bot.handle_favorite_callback(cb, state)

        mock_collect.assert_awaited_once_with(
            cb,
            state,
            service_key="viewing",
            viewing_objects=[
                {
                    "id": "prop-1",
                    "complex_name": "Complex A",
                    "property_type": "Apartment",
                    "area_m2": 60,
                    "price_eur": 200000,
                },
                {
                    "id": "prop-2",
                    "complex_name": "Complex B",
                    "property_type": "Apartment",
                    "area_m2": 80,
                    "price_eur": 350000,
                },
            ],
        )


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
# 5. Footer contract: shown/total/has_more consistency
# ---------------------------------------------------------------------------


class TestFooterContract:
    """Verify correct shown/total/has_more combinations per page."""

    @pytest.mark.parametrize(
        "total,offset,exp_cards,exp_range,exp_has_more",
        [
            (12, 0, 5, "показаны 6–10", True),
            (12, 5, 2, "показаны 11–12", False),
            (10, 0, 5, "показаны 6–10", False),
            (6, 0, 1, "показаны 6–6", False),
            (7, 0, 2, "показаны 6–7", False),
        ],
        ids=[
            "mid-page-has-more",
            "last-partial-page",
            "exact-boundary",
            "single-card-last",
            "two-cards-last",
        ],
    )
    async def test_footer_text_and_card_count(
        self,
        total: int,
        offset: int,
        exp_cards: int,
        exp_range: str,
        exp_has_more: bool,
    ) -> None:
        bot = _create_bot()
        results = _make_results(total)
        state = _make_state({"apartment_results": results, "apartment_offset": offset})
        cb = _make_callback("results:more")

        await bot.handle_results_callback(cb, state)

        assert cb.message.answer_photo.await_count == exp_cards
        assert cb.message.answer.await_count == 1
        footer_call = cb.message.answer.call_args
        assert exp_range in footer_call.args[0]
        footer_markup = footer_call.kwargs["reply_markup"]
        callbacks = [btn.callback_data for row in footer_markup.inline_keyboard for btn in row]
        if exp_has_more:
            assert "results:more" in callbacks
        else:
            assert "results:more" not in callbacks

    async def test_no_duplicate_cards_edge_page(self) -> None:
        """Each card sent exactly once on partial last page."""
        bot = _create_bot()
        results = _make_results(7)
        state = _make_state({"apartment_results": results, "apartment_offset": 0})
        cb = _make_callback("results:more")

        await bot.handle_results_callback(cb, state)

        card_calls = cb.message.answer_photo.call_args_list
        card_texts = [c.kwargs["caption"] for c in card_calls]
        assert len(card_texts) == 2
        assert "Complex 5" in card_texts[0]
        assert "Complex 6" in card_texts[1]

    async def test_single_result_no_more_page(self) -> None:
        """1 total result, offset=0 -> 'all shown' (page 1 was initial display)."""
        bot = _create_bot()
        results = _make_results(1)
        state = _make_state({"apartment_results": results, "apartment_offset": 0})
        cb = _make_callback("results:more")

        await bot.handle_results_callback(cb, state)

        cb.answer.assert_awaited_once_with(
            "\u0412\u0441\u0435 \u0440\u0435\u0437\u0443\u043b\u044c\u0442\u0430\u0442\u044b "
            "\u0443\u0436\u0435 \u043f\u043e\u043a\u0430\u0437\u0430\u043d\u044b"
        )
        cb.message.answer.assert_not_called()
        cb.message.answer_photo.assert_not_called()

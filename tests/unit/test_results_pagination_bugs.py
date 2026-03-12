"""Regression tests for handle_results_callback pagination bugs (#948).

Bugs fixed:
1. offset=scroll_offset → start_from=scroll_offset
2. 3-tuple unpack → 4-tuple (captures page_ids)
3. exclude_ids not passed from state
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


pytest.importorskip("aiogram", reason="aiogram not installed")

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


def _make_callback(user_id: int = 12345) -> MagicMock:
    cb = MagicMock()
    cb.data = "results:more"
    cb.from_user = MagicMock(id=user_id)
    cb.answer = AsyncMock()
    cb.message = MagicMock()
    cb.message.answer = AsyncMock()
    cb.message.answer_photo = AsyncMock()
    cb.message.answer_media_group = AsyncMock()
    return cb


def _make_state(data: dict) -> MagicMock:
    state = MagicMock()
    state.get_data = AsyncMock(return_value=data)
    state.update_data = AsyncMock()
    return state


_APT = {"id": "apt-1", "payload": {"price_eur": 55000, "complex_name": "Test"}}


# ---------------------------------------------------------------------------
# Bug #1: start_from parameter name
# ---------------------------------------------------------------------------


class TestScrollStartFromParameter:
    async def test_scroll_with_filters_called_with_start_from_not_offset(self):
        """scroll_with_filters must use start_from=, not offset= (#948 bug 1)."""
        bot = _create_bot()
        mock_svc = MagicMock()
        scroll_return = ([_APT] * 5, 20, 65000.0, ["apt-1", "apt-2"])
        mock_svc.scroll_with_filters = AsyncMock(return_value=scroll_return)
        bot._apartments_service = mock_svc

        # State: current page full → triggers lazy fetch
        first_page = [_APT] * _PAGE_SIZE
        state_data = {
            "apartment_results": first_page,
            "apartment_offset": 0,
            "apartment_total": 20,
            "apartment_next_offset": 55000.0,
            "apartment_filters": {"city": "Солнечный берег"},
            "apartment_scroll_seen_ids": [],
        }
        state = _make_state(state_data)
        cb = _make_callback()

        from telegram_bot.callback_data import ResultsCB

        cb_data = ResultsCB(action="more")

        with patch.object(bot, "_send_property_card", new=AsyncMock()):
            await bot.handle_results_callback(cb, state, callback_data=cb_data)

        mock_svc.scroll_with_filters.assert_awaited_once()
        call_kwargs = mock_svc.scroll_with_filters.call_args.kwargs
        # Bug #1: must use start_from=, not offset=
        assert "start_from" in call_kwargs, (
            "scroll_with_filters must be called with start_from= parameter, not offset="
        )
        assert "offset" not in call_kwargs, "scroll_with_filters must NOT use offset= parameter"
        assert call_kwargs["start_from"] == 55000.0


# ---------------------------------------------------------------------------
# Bug #2: 4-tuple unpack (page_ids captured)
# ---------------------------------------------------------------------------


class TestScrollFourTupleUnpack:
    async def test_page_ids_saved_to_state_after_scroll(self):
        """page_ids from 4-tuple must be saved to state as apartment_scroll_seen_ids (#948 bug 2)."""
        bot = _create_bot()
        mock_svc = MagicMock()
        new_page_ids = ["apt-10", "apt-11", "apt-12"]
        scroll_return = ([_APT] * 3, 20, 70000.0, new_page_ids)
        mock_svc.scroll_with_filters = AsyncMock(return_value=scroll_return)
        bot._apartments_service = mock_svc

        first_page = [_APT] * _PAGE_SIZE
        state_data = {
            "apartment_results": first_page,
            "apartment_offset": 0,
            "apartment_total": 20,
            "apartment_next_offset": 55000.0,
            "apartment_filters": {},
            "apartment_scroll_seen_ids": [],
        }
        state = _make_state(state_data)
        cb = _make_callback()

        from telegram_bot.callback_data import ResultsCB

        cb_data = ResultsCB(action="more")

        with patch.object(bot, "_send_property_card", new=AsyncMock()):
            await bot.handle_results_callback(cb, state, callback_data=cb_data)

        state.update_data.assert_awaited()
        # Find the call that stores apartment data
        update_calls = state.update_data.call_args_list
        stored_ids = None
        for call in update_calls:
            kw = call.kwargs
            if "apartment_scroll_seen_ids" in kw:
                stored_ids = kw["apartment_scroll_seen_ids"]
                break
        assert stored_ids == new_page_ids, (
            f"page_ids {new_page_ids!r} must be stored as apartment_scroll_seen_ids, got {stored_ids!r}"
        )


# ---------------------------------------------------------------------------
# Bug #3: exclude_ids passed from state
# ---------------------------------------------------------------------------


class TestScrollExcludeIds:
    async def test_exclude_ids_passed_from_state(self):
        """exclude_ids must be passed from state's apartment_scroll_seen_ids (#948 bug 3)."""
        bot = _create_bot()
        mock_svc = MagicMock()
        scroll_return = ([_APT] * 5, 20, 70000.0, ["apt-new"])
        mock_svc.scroll_with_filters = AsyncMock(return_value=scroll_return)
        bot._apartments_service = mock_svc

        seen_ids = ["apt-5", "apt-6", "apt-7"]
        first_page = [_APT] * _PAGE_SIZE
        state_data = {
            "apartment_results": first_page,
            "apartment_offset": 0,
            "apartment_total": 20,
            "apartment_next_offset": 55000.0,
            "apartment_filters": {"rooms": 2},
            "apartment_scroll_seen_ids": seen_ids,
        }
        state = _make_state(state_data)
        cb = _make_callback()

        from telegram_bot.callback_data import ResultsCB

        cb_data = ResultsCB(action="more")

        with patch.object(bot, "_send_property_card", new=AsyncMock()):
            await bot.handle_results_callback(cb, state, callback_data=cb_data)

        mock_svc.scroll_with_filters.assert_awaited_once()
        call_kwargs = mock_svc.scroll_with_filters.call_args.kwargs
        # Bug #3: exclude_ids must be passed
        assert "exclude_ids" in call_kwargs, (
            "scroll_with_filters must be called with exclude_ids= parameter"
        )
        assert call_kwargs["exclude_ids"] == seen_ids, (
            f"exclude_ids must equal apartment_scroll_seen_ids={seen_ids!r}"
        )

    async def test_exclude_ids_is_none_when_seen_ids_empty(self):
        """When no seen_ids in state, exclude_ids must be None (not empty list)."""
        bot = _create_bot()
        mock_svc = MagicMock()
        scroll_return = ([_APT] * 5, 20, 70000.0, ["apt-new"])
        mock_svc.scroll_with_filters = AsyncMock(return_value=scroll_return)
        bot._apartments_service = mock_svc

        first_page = [_APT] * _PAGE_SIZE
        state_data = {
            "apartment_results": first_page,
            "apartment_offset": 0,
            "apartment_total": 20,
            "apartment_next_offset": 55000.0,
            "apartment_filters": {},
            "apartment_scroll_seen_ids": [],
        }
        state = _make_state(state_data)
        cb = _make_callback()

        from telegram_bot.callback_data import ResultsCB

        cb_data = ResultsCB(action="more")

        with patch.object(bot, "_send_property_card", new=AsyncMock()):
            await bot.handle_results_callback(cb, state, callback_data=cb_data)

        call_kwargs = mock_svc.scroll_with_filters.call_args.kwargs
        # Empty list → None (falsy guard)
        assert call_kwargs.get("exclude_ids") is None

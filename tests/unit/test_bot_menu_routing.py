"""Tests for handle_menu_button routing, handle_service_callback,
handle_cta_callback, and _handle_apartment_fast_path.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


pytest.importorskip("aiogram", reason="aiogram not installed")

from telegram_bot.config import BotConfig


def _make_config(**overrides) -> BotConfig:
    defaults = dict(
        telegram_token="test-token",
        llm_api_key="llm-key",
        llm_base_url="https://api.example.com/v1",
        llm_model="gpt-4o-mini",
        qdrant_url="http://localhost:6333",
        redis_url="redis://localhost:6379",
        rerank_provider="none",
    )
    defaults.update(overrides)
    return BotConfig(_env_file=None, **defaults)


def _create_bot(config: BotConfig | None = None):
    if config is None:
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
        from telegram_bot.bot import PropertyBot

        return PropertyBot(config)


def _make_message(text="test"):
    message = MagicMock()
    message.text = text
    message.from_user = MagicMock(id=12345)
    message.chat = MagicMock(id=12345)
    message.bot = MagicMock(send_chat_action=AsyncMock())
    message.answer = AsyncMock()
    return message


def _make_callback(data="svc:back"):
    callback = MagicMock()
    callback.data = data
    callback.from_user = MagicMock(id=12345)
    callback.answer = AsyncMock()
    callback.message = MagicMock(
        edit_text=AsyncMock(),
        delete=AsyncMock(),
        answer=AsyncMock(),
        chat=MagicMock(id=456),
    )
    return callback


def _make_state(current_state=None, data=None):
    state = MagicMock()
    state.get_data = AsyncMock(return_value=data or {})
    state.update_data = AsyncMock()
    state.set_state = AsyncMock()
    state.clear = AsyncMock()
    state.get_state = AsyncMock(return_value=current_state)
    return state


***REMOVED*** ---------------------------------------------------------------------------
***REMOVED*** TestHandleMenuButton
***REMOVED*** ---------------------------------------------------------------------------


class TestHandleMenuButton:
    """Test handle_menu_button dispatch routing."""

    @pytest.mark.asyncio()
    async def test_search_dispatches_to_handle_search(self):
        bot = _create_bot()
        message = _make_message("search")
        state = _make_state()
        bot._handle_search = AsyncMock()

        with patch(
            "telegram_bot.bot.parse_menu_button", return_value="search"
        ):
            await bot.handle_menu_button(message, state)

        bot._handle_search.assert_awaited_once()

    @pytest.mark.asyncio()
    async def test_services_dispatches_to_handle_services(self):
        bot = _create_bot()
        message = _make_message("services")
        state = _make_state()
        bot._handle_services = AsyncMock()

        with patch(
            "telegram_bot.bot.parse_menu_button", return_value="services"
        ):
            await bot.handle_menu_button(message, state)

        bot._handle_services.assert_awaited_once()

    @pytest.mark.asyncio()
    async def test_viewing_dispatches_to_handle_viewing(self):
        bot = _create_bot()
        message = _make_message("viewing")
        state = _make_state()
        bot._handle_viewing = AsyncMock()

        with patch(
            "telegram_bot.bot.parse_menu_button", return_value="viewing"
        ):
            await bot.handle_menu_button(message, state)

        bot._handle_viewing.assert_awaited_once()

    @pytest.mark.asyncio()
    async def test_bookmarks_dispatches_to_handle_bookmarks(self):
        bot = _create_bot()
        message = _make_message("bookmarks")
        state = _make_state()
        bot._handle_bookmarks = AsyncMock()

        with patch(
            "telegram_bot.bot.parse_menu_button", return_value="bookmarks"
        ):
            await bot.handle_menu_button(message, state)

        bot._handle_bookmarks.assert_awaited_once()

    @pytest.mark.asyncio()
    async def test_ask_dispatches_to_handle_ask(self):
        bot = _create_bot()
        message = _make_message("ask")
        state = _make_state()
        bot._handle_ask = AsyncMock()

        with patch(
            "telegram_bot.bot.parse_menu_button", return_value="ask"
        ):
            await bot.handle_menu_button(message, state)

        bot._handle_ask.assert_awaited_once()

    @pytest.mark.asyncio()
    async def test_manager_dispatches_to_handle_manager(self):
        bot = _create_bot()
        message = _make_message("manager")
        state = _make_state()
        bot._handle_manager = AsyncMock()

        with patch(
            "telegram_bot.bot.parse_menu_button", return_value="manager"
        ):
            await bot.handle_menu_button(message, state)

        bot._handle_manager.assert_awaited_once()

    @pytest.mark.asyncio()
    async def test_none_action_returns_early(self):
        bot = _create_bot()
        message = _make_message("unknown")
        state = _make_state()
        bot._handle_search = AsyncMock()
        bot._handle_services = AsyncMock()
        bot._handle_viewing = AsyncMock()
        bot._handle_bookmarks = AsyncMock()
        bot._handle_ask = AsyncMock()
        bot._handle_manager = AsyncMock()

        with patch(
            "telegram_bot.bot.parse_menu_button", return_value=None
        ):
            await bot.handle_menu_button(message, state)

        bot._handle_search.assert_not_awaited()
        bot._handle_services.assert_not_awaited()
        bot._handle_viewing.assert_not_awaited()
        bot._handle_bookmarks.assert_not_awaited()
        bot._handle_ask.assert_not_awaited()
        bot._handle_manager.assert_not_awaited()

    @pytest.mark.asyncio()
    async def test_clears_phone_collector_state(self):
        bot = _create_bot()
        message = _make_message("search")
        state = _make_state(current_state="PhoneCollectorStates:waiting_phone")
        bot._handle_search = AsyncMock()

        with patch(
            "telegram_bot.bot.parse_menu_button", return_value="search"
        ):
            await bot.handle_menu_button(message, state)

        state.clear.assert_awaited_once()

    @pytest.mark.asyncio()
    async def test_does_not_clear_non_phone_collection_state(self):
        bot = _create_bot()
        message = _make_message("search")
        state = _make_state(current_state="SomeOtherState:step")
        bot._handle_search = AsyncMock()

        with patch(
            "telegram_bot.bot.parse_menu_button", return_value="search"
        ):
            await bot.handle_menu_button(message, state)

        state.clear.assert_not_awaited()


***REMOVED*** ---------------------------------------------------------------------------
***REMOVED*** TestHandleServiceCallback
***REMOVED*** ---------------------------------------------------------------------------


class TestHandleServiceCallback:
    """Test handle_service_callback actions."""

    @pytest.mark.asyncio()
    async def test_action_back_deletes_message(self):
        bot = _create_bot()
        callback = _make_callback("svc:back")

        with patch(
            "telegram_bot.keyboards.services_keyboard.parse_service_callback",
            return_value=("back", None),
        ):
            await bot.handle_service_callback(callback)

        callback.message.delete.assert_awaited_once()
        callback.answer.assert_awaited_once()

    @pytest.mark.asyncio()
    async def test_action_menu_edits_message(self):
        bot = _create_bot()
        callback = _make_callback("svc:menu")

        with (
            patch(
                "telegram_bot.keyboards.services_keyboard.parse_service_callback",
                return_value=("menu", None),
            ),
            patch(
                "telegram_bot.keyboards.services_keyboard.build_services_menu",
                return_value=MagicMock(),
            ),
        ):
            await bot.handle_service_callback(callback)

        callback.message.edit_text.assert_awaited_once()
        callback.answer.assert_awaited_once()

    @pytest.mark.asyncio()
    async def test_action_service_with_valid_param(self):
        bot = _create_bot()
        callback = _make_callback("svc:service:insurance")

        with (
            patch(
                "telegram_bot.keyboards.services_keyboard.parse_service_callback",
                return_value=("service", "insurance"),
            ),
            patch(
                "telegram_bot.services.content_loader.get_service_card",
                return_value={"card_text": "Insurance details"},
            ),
            patch(
                "telegram_bot.keyboards.services_keyboard.build_service_card_buttons",
                return_value=MagicMock(),
            ),
        ):
            await bot.handle_service_callback(callback)

        callback.message.edit_text.assert_awaited_once()
        callback.answer.assert_awaited_once()

    @pytest.mark.asyncio()
    async def test_unparseable_data_answers_callback(self):
        bot = _create_bot()
        callback = _make_callback("garbage")

        with patch(
            "telegram_bot.keyboards.services_keyboard.parse_service_callback",
            return_value=None,
        ):
            await bot.handle_service_callback(callback)

        callback.answer.assert_awaited_once()
        callback.message.edit_text.assert_not_awaited()
        callback.message.delete.assert_not_awaited()

    @pytest.mark.asyncio()
    async def test_unknown_action_answers_callback(self):
        bot = _create_bot()
        callback = _make_callback("svc:unknown")

        with patch(
            "telegram_bot.keyboards.services_keyboard.parse_service_callback",
            return_value=("unknown_action", None),
        ):
            await bot.handle_service_callback(callback)

        callback.answer.assert_awaited_once()
        callback.message.edit_text.assert_not_awaited()
        callback.message.delete.assert_not_awaited()


***REMOVED*** ---------------------------------------------------------------------------
***REMOVED*** TestHandleCtaCallback
***REMOVED*** ---------------------------------------------------------------------------


class TestHandleCtaCallback:
    """Test handle_cta_callback actions."""

    @pytest.mark.asyncio()
    async def test_get_offer_starts_phone_collection(self):
        bot = _create_bot()
        callback = _make_callback("cta:get_offer:insurance")
        state = _make_state()

        with (
            patch(
                "telegram_bot.keyboards.services_keyboard.parse_service_callback",
                return_value=("get_offer", "insurance"),
            ),
            patch(
                "telegram_bot.handlers.phone_collector.start_phone_collection",
                new_callable=AsyncMock,
            ) as mock_phone,
        ):
            await bot.handle_cta_callback(callback, state)

        mock_phone.assert_awaited_once()
        call_kwargs = mock_phone.call_args
        assert call_kwargs.kwargs.get("service_key") == "insurance"

    @pytest.mark.asyncio()
    async def test_manager_with_forum_bridge_starts_qualification(self):
        bot = _create_bot()
        bot._forum_bridge = MagicMock()
        callback = _make_callback("cta:manager")
        state = _make_state()

        with (
            patch(
                "telegram_bot.keyboards.services_keyboard.parse_service_callback",
                return_value=("manager", None),
            ),
            patch(
                "telegram_bot.bot.start_qualification",
                new_callable=AsyncMock,
            ) as mock_qual,
        ):
            await bot.handle_cta_callback(callback, state)

        mock_qual.assert_awaited_once()

    @pytest.mark.asyncio()
    async def test_manager_without_forum_bridge_starts_phone_collection(self):
        bot = _create_bot()
        bot._forum_bridge = None
        callback = _make_callback("cta:manager")
        state = _make_state()

        with (
            patch(
                "telegram_bot.keyboards.services_keyboard.parse_service_callback",
                return_value=("manager", None),
            ),
            patch(
                "telegram_bot.handlers.phone_collector.start_phone_collection",
                new_callable=AsyncMock,
            ) as mock_phone,
        ):
            await bot.handle_cta_callback(callback, state)

        mock_phone.assert_awaited_once()
        call_kwargs = mock_phone.call_args
        assert call_kwargs.kwargs.get("service_key") == "manager"

    @pytest.mark.asyncio()
    async def test_none_unparseable_answers_callback(self):
        bot = _create_bot()
        callback = _make_callback("garbage")
        state = _make_state()

        with patch(
            "telegram_bot.keyboards.services_keyboard.parse_service_callback",
            return_value=None,
        ):
            await bot.handle_cta_callback(callback, state)

        callback.answer.assert_awaited_once()


***REMOVED*** ---------------------------------------------------------------------------
***REMOVED*** TestHandleApartmentFastPath
***REMOVED*** ---------------------------------------------------------------------------


class TestHandleApartmentFastPath:
    """Test _handle_apartment_fast_path logic."""

    @pytest.mark.asyncio()
    async def test_low_confidence_returns_none(self):
        bot = _create_bot()
        message = _make_message("find apartment")

        extract_result = MagicMock()
        extract_result.meta.confidence = "LOW"
        bot._apartment_pipeline.extract = AsyncMock(return_value=extract_result)

        result = await bot._handle_apartment_fast_path(
            user_text="find apartment", message=message
        )

        assert result is None

    @pytest.mark.asyncio()
    async def test_escalation_triggered_returns_none(self):
        bot = _create_bot()
        message = _make_message("find apartment")
        message.from_user = MagicMock(id=12345)

        extract_result = MagicMock()
        extract_result.meta.confidence = "HIGH"
        extract_result.meta.semantic_remainder = "apartment near sea"
        extract_result.hard.to_filters_dict.return_value = {"city": "Limassol"}
        bot._apartment_pipeline.extract = AsyncMock(return_value=extract_result)

        bot._embeddings.aembed_hybrid_with_colbert = AsyncMock(
            return_value=([0.1, 0.2], {"indices": [1], "values": [0.5]}, [[0.1]])
        )
        bot._cache.store_embedding = AsyncMock()
        bot._cache.store_sparse_embedding = AsyncMock()
        bot._cache.redis = None

        search_results = [
            {"score": 0.9, "id": "1", "payload": {}},
            {"score": 0.1, "id": "2", "payload": {}},
        ]
        bot._apartments_service.search_with_filters = AsyncMock(
            return_value=(search_results, 2)
        )

        with patch(
            "telegram_bot.services.apartments_service.check_escalation",
            return_value=True,
        ):
            result = await bot._handle_apartment_fast_path(
                user_text="find apartment", message=message
            )

        assert result is None

    @pytest.mark.asyncio()
    async def test_successful_path_sends_response(self):
        bot = _create_bot()
        message = _make_message("find apartment")
        message.from_user = MagicMock(id=12345)

        extract_result = MagicMock()
        extract_result.meta.confidence = "HIGH"
        extract_result.meta.semantic_remainder = "apartment near sea"
        extract_result.hard.to_filters_dict.return_value = {"city": "Limassol"}
        bot._apartment_pipeline.extract = AsyncMock(return_value=extract_result)

        bot._embeddings.aembed_hybrid_with_colbert = AsyncMock(
            return_value=([0.1, 0.2], {"indices": [1], "values": [0.5]}, [[0.1]])
        )
        bot._cache.store_embedding = AsyncMock()
        bot._cache.store_sparse_embedding = AsyncMock()
        bot._cache.redis = None

        search_results = [
            {"score": 0.9, "id": "1", "payload": {}},
            {"score": 0.85, "id": "2", "payload": {}},
        ]
        bot._apartments_service.search_with_filters = AsyncMock(
            return_value=(search_results, 2)
        )

        bot._send_markdown_chunks = AsyncMock()

        with (
            patch(
                "telegram_bot.services.apartments_service.check_escalation",
                return_value=False,
            ),
            patch(
                "telegram_bot.services.apartment_formatter.format_apartment_text",
                return_value="Formatted apartments",
            ),
            patch(
                "telegram_bot.services.generate_response.generate_response",
                new_callable=AsyncMock,
                return_value={"response": "Here are your apartments", "response_sent": False},
            ),
        ):
            result = await bot._handle_apartment_fast_path(
                user_text="find apartment", message=message
            )

        assert result is not None
        assert result == "Here are your apartments"
        bot._send_markdown_chunks.assert_awaited_once()

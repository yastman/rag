"""Tests for handle_menu_button routing, handle_service_callback,
and handle_cta_callback.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

from telegram_bot.config import BotConfig
from tests.unit._bot_config_factory import make_bot_config as _make_config


def _create_bot(config: BotConfig | None = None):
    if config is None:
        config = _make_config()
    with (
        patch("telegram_bot.bot.Bot"),
        patch("src.runtime.integrations.cache.CacheLayerManager"),
        patch("src.runtime.integrations.embeddings.BGEM3HybridEmbeddings"),
        patch("src.runtime.integrations.embeddings.BGEM3SparseEmbeddings"),
        patch("src.runtime.services.qdrant.QdrantService"),
        patch("src.runtime.config.GraphConfig.create_llm"),
        patch("src.runtime.config.GraphConfig.create_supervisor_llm"),
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


# ---------------------------------------------------------------------------
# TestHandleMenuButton
# ---------------------------------------------------------------------------


class TestHandleMenuButton:
    """Test handle_menu_button dispatch routing."""

    async def test_search_dispatches_to_handle_search(self):
        bot = _create_bot()
        message = _make_message("search")
        state = _make_state()

        with (
            patch(
                "telegram_bot.keyboards.client_keyboard.parse_menu_button", return_value="search"
            ),
            patch(
                "telegram_bot.handlers.catalog._handle_search", new_callable=AsyncMock
            ) as mock_search,
        ):
            await bot.handle_menu_button(message, state)

        mock_search.assert_awaited_once_with(bot, message, None)

    async def test_services_dispatches_to_handle_services(self):
        bot = _create_bot()
        message = _make_message("services")
        state = _make_state()

        with (
            patch(
                "telegram_bot.keyboards.client_keyboard.parse_menu_button", return_value="services"
            ),
            patch(
                "telegram_bot.handlers.catalog._handle_services", new_callable=AsyncMock
            ) as mock_svc,
        ):
            await bot.handle_menu_button(message, state)

        mock_svc.assert_awaited_once_with(bot, message, i18n=None)

    async def test_viewing_dispatches_to_handle_viewing(self):
        bot = _create_bot()
        message = _make_message("viewing")
        state = _make_state()

        with (
            patch(
                "telegram_bot.keyboards.client_keyboard.parse_menu_button", return_value="viewing"
            ),
            patch(
                "telegram_bot.handlers.catalog._handle_viewing", new_callable=AsyncMock
            ) as mock_viewing,
        ):
            await bot.handle_menu_button(message, state)

        mock_viewing.assert_awaited_once_with(bot, message, state, None)

    async def test_bookmarks_dispatches_to_handle_bookmarks(self):
        bot = _create_bot()
        message = _make_message("bookmarks")
        state = _make_state()

        with (
            patch(
                "telegram_bot.keyboards.client_keyboard.parse_menu_button", return_value="bookmarks"
            ),
            patch(
                "telegram_bot.handlers.favorites._handle_bookmarks", new_callable=AsyncMock
            ) as mock_bm,
        ):
            await bot.handle_menu_button(message, state)

        mock_bm.assert_awaited_once_with(bot, message, state)

    async def test_ask_dispatches_to_handle_ask(self):
        bot = _create_bot()
        message = _make_message("ask")
        state = _make_state()

        with (
            patch("telegram_bot.keyboards.client_keyboard.parse_menu_button", return_value="ask"),
            patch("telegram_bot.handlers.catalog._handle_ask", new_callable=AsyncMock) as mock_ask,
        ):
            await bot.handle_menu_button(message, state, dialog_manager=None)

        # Ask must receive state/dialog_manager so it can exit any active
        # flow and hand the typed question to the Q&A route (#3204).
        mock_ask.assert_awaited_once_with(
            bot,
            message,
            i18n=None,
            state=state,
            dialog_manager=None,
        )

    async def test_manager_dispatches_to_handle_manager(self):
        bot = _create_bot()
        message = _make_message("manager")
        state = _make_state()

        with (
            patch(
                "telegram_bot.keyboards.client_keyboard.parse_menu_button", return_value="manager"
            ),
            patch(
                "telegram_bot.handlers.bot_handoff._handle_manager", new_callable=AsyncMock
            ) as mock_mgr,
        ):
            await bot.handle_menu_button(message, state)

        mock_mgr.assert_awaited_once_with(bot, message, i18n=None, state=state, dialog_manager=None)

    async def test_none_action_returns_early(self):
        bot = _create_bot()
        message = _make_message("unknown")
        state = _make_state()

        with patch("telegram_bot.keyboards.client_keyboard.parse_menu_button", return_value=None):
            await bot.handle_menu_button(message, state)

        # No handler should have been called

    async def test_clears_phone_collector_state(self):
        bot = _create_bot()
        message = _make_message("search")
        state = _make_state(current_state="PhoneCollectorStates:waiting_phone")

        with (
            patch(
                "telegram_bot.keyboards.client_keyboard.parse_menu_button", return_value="search"
            ),
            patch("telegram_bot.handlers.catalog._handle_search", new_callable=AsyncMock),
        ):
            await bot.handle_menu_button(message, state)

        state.clear.assert_awaited_once()

    async def test_does_not_clear_non_phone_collection_state(self):
        bot = _create_bot()
        message = _make_message("search")
        state = _make_state(current_state="SomeOtherState:step")

        with (
            patch(
                "telegram_bot.keyboards.client_keyboard.parse_menu_button", return_value="search"
            ),
            patch("telegram_bot.handlers.catalog._handle_search", new_callable=AsyncMock),
        ):
            await bot.handle_menu_button(message, state)

        state.clear.assert_not_awaited()


# ---------------------------------------------------------------------------
# TestHandleServiceCallback
# ---------------------------------------------------------------------------


class TestHandleServiceCallback:
    """Test handle_service_callback actions."""

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

    async def test_action_service_with_valid_param(self):
        bot = _create_bot()
        callback = _make_callback("svc:service:insurance")

        with (
            patch(
                "telegram_bot.keyboards.services_keyboard.parse_service_callback",
                return_value=("service", "insurance"),
            ),
            patch(
                "src.services.content_loader.get_service_card",
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


# ---------------------------------------------------------------------------
# TestHandleCtaCallback
# ---------------------------------------------------------------------------


class TestHandleCtaCallback:
    """Test handle_cta_callback actions."""

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

    async def test_manager_with_forum_bridge_starts_qualification(self):
        # Capability on (#3239): HANDOFF_ENABLED + bridge + Redis state.
        config = _make_config(handoff_enabled=True, managers_group_id=-100123)
        bot = _create_bot(config)
        bot._forum_bridge = MagicMock()
        bot._handoff_state = MagicMock()
        callback = _make_callback("cta:manager")
        state = _make_state()

        with (
            patch(
                "telegram_bot.keyboards.services_keyboard.parse_service_callback",
                return_value=("manager", None),
            ),
            patch(
                "telegram_bot.handlers.catalog.start_qualification",
                new_callable=AsyncMock,
            ) as mock_qual,
        ):
            await bot.handle_cta_callback(callback, state)

        mock_qual.assert_awaited_once()

    async def test_manager_with_bridge_but_capability_off_starts_phone_collection(self):
        """Bridge present but HANDOFF_ENABLED unset — no forum handoff (#3239)."""
        bot = _create_bot()
        bot._forum_bridge = MagicMock()
        bot._handoff_state = MagicMock()
        callback = _make_callback("cta:manager")
        state = _make_state()

        with (
            patch(
                "telegram_bot.keyboards.services_keyboard.parse_service_callback",
                return_value=("manager", None),
            ),
            patch(
                "telegram_bot.handlers.catalog.start_qualification",
                new_callable=AsyncMock,
            ) as mock_qual,
            patch(
                "telegram_bot.handlers.phone_collector.start_phone_collection",
                new_callable=AsyncMock,
            ) as mock_phone,
        ):
            await bot.handle_cta_callback(callback, state)

        mock_qual.assert_not_awaited()
        mock_phone.assert_awaited_once_with(callback, state, service_key="manager")

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

"""Unit tests for client menu integration in bot.py (#628).

Covers:
- Task A: handle_menu_button routing (routes ReplyKeyboard presses to _handle_* methods)
- Task B: cmd_start role routing (client vs manager, with/without dialog)
- Task C: handle_service_callback (svc: callbacks — show card, back, menu, unknown)
- Task D: handle_favorite_callback (fav: callbacks — add, remove, no service)
- Task E: handle_cta_callback (cta: callbacks — get_offer, manager)
- Task F: handle_menu_action_text (dispatches + restores message.text)
- Task G: _handle_bookmarks display (empty vs with items)
- Task H: edge cases (None text, no user, no message)
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


pytest.importorskip("aiogram", reason="aiogram not installed")

from telegram_bot.bot import PropertyBot
from telegram_bot.config import BotConfig


# ─── Shared fixtures ──────────────────────────────────────────────────────────


@pytest.fixture
def mock_config(monkeypatch):
    """Create mock bot config."""
    monkeypatch.delenv("CLIENT_DIRECT_PIPELINE_ENABLED", raising=False)
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


def _create_bot(mock_config: BotConfig) -> PropertyBot:
    """Create PropertyBot with all external deps mocked."""
    with (
        patch("telegram_bot.bot.Bot"),
        patch("telegram_bot.integrations.cache.CacheLayerManager"),
        patch("telegram_bot.integrations.embeddings.BGEM3HybridEmbeddings"),
        patch("telegram_bot.integrations.embeddings.BGEM3SparseEmbeddings"),
        patch("telegram_bot.services.qdrant.QdrantService"),
        patch("telegram_bot.graph.config.GraphConfig.create_llm"),
        patch("telegram_bot.graph.config.GraphConfig.create_supervisor_llm"),
    ):
        return PropertyBot(mock_config)


def _make_message(text: str = "test", user_id: int = 12345, chat_id: int = 12345) -> MagicMock:
    """Create a mock aiogram Message."""
    message = MagicMock()
    message.text = text
    message.from_user = MagicMock(id=user_id)
    message.chat = MagicMock(id=chat_id)
    message.bot = MagicMock()
    message.answer = AsyncMock()
    message.delete = AsyncMock()
    return message


def _make_callback(data: str = "", user_id: int = 12345) -> MagicMock:
    """Create a mock aiogram CallbackQuery."""
    callback = MagicMock()
    callback.data = data
    callback.from_user = MagicMock(id=user_id)
    callback.message = MagicMock()
    callback.message.delete = AsyncMock()
    callback.message.edit_text = AsyncMock()
    callback.message.answer = AsyncMock()
    callback.message.chat = MagicMock(id=12345)
    callback.message.bot = MagicMock()
    callback.answer = AsyncMock()
    return callback


# ─── Task A: handle_menu_button routing ──────────────────────────────────────


class TestHandleMenuButtonRouting:
    """handle_menu_button dispatches ReplyKeyboard presses to correct _handle_* methods."""

    async def test_handle_menu_button_routes_search(self, mock_config):
        """Button «🏠 Подбор апартаментов» routes to _handle_search."""
        from telegram_bot.keyboards.client_keyboard import ACTIONS_TO_TEXT

        bot = _create_bot(mock_config)
        bot._handle_search = AsyncMock()
        message = _make_message(text=ACTIONS_TO_TEXT["search"])

        await bot.handle_menu_button(message)

        bot._handle_search.assert_awaited_once_with(message)

    async def test_handle_menu_button_routes_services(self, mock_config):
        """Button «🔑 Услуги» routes to _handle_services."""
        from telegram_bot.keyboards.client_keyboard import ACTIONS_TO_TEXT

        bot = _create_bot(mock_config)
        bot._handle_services = AsyncMock()
        message = _make_message(text=ACTIONS_TO_TEXT["services"])

        await bot.handle_menu_button(message)

        bot._handle_services.assert_awaited_once_with(message)

    async def test_handle_menu_button_routes_viewing(self, mock_config):
        """Button «📅 Запись на осмотр» routes to _handle_viewing."""
        from telegram_bot.keyboards.client_keyboard import ACTIONS_TO_TEXT

        bot = _create_bot(mock_config)
        bot._handle_viewing = AsyncMock()
        message = _make_message(text=ACTIONS_TO_TEXT["viewing"])

        await bot.handle_menu_button(message)

        bot._handle_viewing.assert_awaited_once_with(message)

    async def test_handle_menu_button_routes_bookmarks(self, mock_config):
        """Button «📌 Мои закладки» routes to _handle_bookmarks."""
        from telegram_bot.keyboards.client_keyboard import ACTIONS_TO_TEXT

        bot = _create_bot(mock_config)
        bot._handle_bookmarks = AsyncMock()
        message = _make_message(text=ACTIONS_TO_TEXT["bookmarks"])

        await bot.handle_menu_button(message)

        bot._handle_bookmarks.assert_awaited_once_with(message)

    async def test_handle_menu_button_routes_promotions(self, mock_config):
        """Button «🎁 Акции» routes to _handle_promotions."""
        from telegram_bot.keyboards.client_keyboard import ACTIONS_TO_TEXT

        bot = _create_bot(mock_config)
        bot._handle_promotions = AsyncMock()
        message = _make_message(text=ACTIONS_TO_TEXT["promotions"])

        await bot.handle_menu_button(message)

        bot._handle_promotions.assert_awaited_once_with(message)

    async def test_handle_menu_button_routes_manager(self, mock_config):
        """Button «👤 Связь с менеджером» routes to _handle_manager."""
        from telegram_bot.keyboards.client_keyboard import ACTIONS_TO_TEXT

        bot = _create_bot(mock_config)
        bot._handle_manager = AsyncMock()
        message = _make_message(text=ACTIONS_TO_TEXT["manager"])

        await bot.handle_menu_button(message)

        bot._handle_manager.assert_awaited_once_with(message)

    async def test_handle_menu_button_unknown_text_noop(self, mock_config):
        """Unrecognized button text is silently ignored (returns None, no handler called)."""
        bot = _create_bot(mock_config)
        for attr in (
            "_handle_search",
            "_handle_services",
            "_handle_viewing",
            "_handle_bookmarks",
            "_handle_promotions",
            "_handle_manager",
        ):
            setattr(bot, attr, AsyncMock())
        message = _make_message(text="some random unrecognized text")

        result = await bot.handle_menu_button(message)

        assert result is None
        bot._handle_search.assert_not_awaited()
        bot._handle_services.assert_not_awaited()

    async def test_handle_menu_button_none_text(self, mock_config):
        """message.text is None must not crash — treated as unrecognized."""
        bot = _create_bot(mock_config)
        bot._handle_search = AsyncMock()
        message = _make_message()
        message.text = None

        await bot.handle_menu_button(message)

        bot._handle_search.assert_not_awaited()


# ─── Task B: cmd_start role routing ──────────────────────────────────────────


class TestCmdStartRoleRouting:
    """cmd_start routes to client welcome or manager menu based on resolved role."""

    async def test_cmd_start_client_sends_welcome_keyboard(self, mock_config):
        """Client role receives welcome text + persistent ReplyKeyboard."""
        mock_config.manager_ids = []  # no manager elevation
        bot = _create_bot(mock_config)
        message = _make_message(user_id=99999)

        await bot.cmd_start(message)

        message.answer.assert_awaited_once()
        call_args = message.answer.call_args
        # reply_markup keyword arg must be set (ReplyKeyboardMarkup)
        assert call_args.kwargs.get("reply_markup") is not None
        # welcome text contains "FortNoks" (from services.yaml)
        sent_text = call_args.args[0]
        assert "FortNoks" in sent_text

    async def test_cmd_start_manager_with_dialog(self, mock_config):
        """Manager + kommo_enabled + dialog_manager → starts ManagerMenuSG dialog."""
        mock_config.manager_ids = [12345]
        mock_config.kommo_enabled = True
        bot = _create_bot(mock_config)
        message = _make_message(user_id=12345)
        dialog_manager = AsyncMock()

        await bot.cmd_start(message, dialog_manager=dialog_manager)

        dialog_manager.start.assert_awaited_once()
        # Positional arg is the state (ManagerMenuSG.main)
        from telegram_bot.dialogs.states import ManagerMenuSG

        started_state = dialog_manager.start.call_args.args[0]
        assert started_state is ManagerMenuSG.main

    async def test_cmd_start_manager_without_dialog(self, mock_config):
        """Manager without dialog_manager (kommo disabled) falls back to text answer."""
        mock_config.manager_ids = [12345]
        mock_config.kommo_enabled = False
        bot = _create_bot(mock_config)
        message = _make_message(user_id=12345)

        await bot.cmd_start(message, dialog_manager=None)

        message.answer.assert_awaited_once()
        # No reply_markup for manager text fallback
        call_args = message.answer.call_args
        assert isinstance(call_args.args[0], str)


# ─── Task C: handle_service_callback ─────────────────────────────────────────


class TestHandleServiceCallback:
    """svc: inline button callbacks — show card, back, menu, unknown, no-message."""

    async def test_handle_service_callback_show_card(self, mock_config):
        """svc:installment edits message to show card text + CTA buttons."""
        bot = _create_bot(mock_config)
        callback = _make_callback(data="svc:installment")

        await bot.handle_service_callback(callback)

        # edit_text called once (card render), then answer() called
        callback.message.edit_text.assert_awaited_once()
        callback.answer.assert_awaited_once()

    async def test_handle_service_callback_back(self, mock_config):
        """svc:back deletes the message."""
        bot = _create_bot(mock_config)
        callback = _make_callback(data="svc:back")

        await bot.handle_service_callback(callback)

        callback.message.delete.assert_awaited_once()
        callback.answer.assert_awaited_once()
        callback.message.edit_text.assert_not_awaited()

    async def test_handle_service_callback_menu(self, mock_config):
        """svc:menu edits message back to the services list."""
        bot = _create_bot(mock_config)
        callback = _make_callback(data="svc:menu")

        await bot.handle_service_callback(callback)

        callback.message.edit_text.assert_awaited_once()
        callback.answer.assert_awaited_once()
        callback.message.delete.assert_not_awaited()

    async def test_handle_service_callback_unknown(self, mock_config):
        """Data that parse_service_callback cannot parse → just answer() with no edits."""
        bot = _create_bot(mock_config)
        # Neither "svc:" nor "cta:" prefix → parse_service_callback returns None
        callback = _make_callback(data="unknown:action")

        await bot.handle_service_callback(callback)

        callback.answer.assert_awaited_once()
        callback.message.edit_text.assert_not_awaited()
        callback.message.delete.assert_not_awaited()

    async def test_handle_service_callback_no_message(self, mock_config):
        """callback.message is None must not crash — just answers."""
        bot = _create_bot(mock_config)
        callback = _make_callback(data="svc:back")
        callback.message = None

        await bot.handle_service_callback(callback)

        callback.answer.assert_awaited_once()


# ─── Task D: handle_favorite_callback ────────────────────────────────────────


class TestHandleFavoriteCallback:
    """fav: inline button callbacks — add, remove, no service, no user."""

    async def test_handle_favorite_add(self, mock_config):
        """fav:add:prop1 → favorites_service.add called, answers '📌 Добавлено'."""
        bot = _create_bot(mock_config)
        bot._favorites_service = AsyncMock()
        bot._favorites_service.add = AsyncMock(return_value={"id": 1})
        callback = _make_callback(data="fav:add:prop1")

        await bot.handle_favorite_callback(callback)

        bot._favorites_service.add.assert_awaited_once_with(
            telegram_id=12345,
            property_id="prop1",
            property_data={},
        )
        callback.answer.assert_awaited_once()
        answered_text = callback.answer.call_args.args[0]
        assert "Добавлено" in answered_text

    async def test_handle_favorite_add_duplicate(self, mock_config):
        """Duplicate add (service returns None) → answers 'Уже в закладках'."""
        bot = _create_bot(mock_config)
        bot._favorites_service = AsyncMock()
        bot._favorites_service.add = AsyncMock(return_value=None)
        callback = _make_callback(data="fav:add:prop1")

        await bot.handle_favorite_callback(callback)

        callback.answer.assert_awaited_once()
        answered_text = callback.answer.call_args.args[0]
        assert "закладках" in answered_text

    async def test_handle_favorite_remove(self, mock_config):
        """fav:remove:prop1 → remove called, message deleted, answer sent."""
        bot = _create_bot(mock_config)
        bot._favorites_service = AsyncMock()
        bot._favorites_service.remove = AsyncMock(return_value=True)
        callback = _make_callback(data="fav:remove:prop1")

        await bot.handle_favorite_callback(callback)

        bot._favorites_service.remove.assert_awaited_once_with(
            telegram_id=12345,
            property_id="prop1",
        )
        callback.message.delete.assert_awaited_once()
        callback.answer.assert_awaited_once()

    async def test_handle_favorite_no_service(self, mock_config):
        """No _favorites_service attribute → answers 'Закладки недоступны'."""
        bot = _create_bot(mock_config)
        # _favorites_service not set (only initialized in start(), not __init__)
        assert not hasattr(bot, "_favorites_service")
        callback = _make_callback(data="fav:add:prop1")

        await bot.handle_favorite_callback(callback)

        callback.answer.assert_awaited_once()
        answered_text = callback.answer.call_args.args[0]
        assert "недоступны" in answered_text.lower()

    async def test_handle_favorite_callback_no_user(self, mock_config):
        """No callback.from_user → just answer() without crashing."""
        bot = _create_bot(mock_config)
        callback = _make_callback(data="fav:add:prop1")
        callback.from_user = None

        await bot.handle_favorite_callback(callback)

        callback.answer.assert_awaited_once()


# ─── Task E: handle_cta_callback ─────────────────────────────────────────────


class TestHandleCtaCallback:
    """cta: CTA button callbacks — get_offer starts FSM, manager handoff."""

    async def test_handle_cta_get_offer_starts_phone_collection(self, mock_config):
        """cta:get_offer:installment + state → start_phone_collection called."""
        bot = _create_bot(mock_config)
        callback = _make_callback(data="cta:get_offer:installment")
        state = AsyncMock()

        with patch(
            "telegram_bot.handlers.phone_collector.start_phone_collection",
            new_callable=AsyncMock,
        ) as mock_start:
            await bot.handle_cta_callback(callback, state=state)

        mock_start.assert_awaited_once()
        call_kwargs = mock_start.call_args.kwargs
        assert call_kwargs["source"] == "service"
        assert call_kwargs["source_detail"] == "installment"

    async def test_handle_cta_manager_dispatches_handoff(self, mock_config):
        """cta:manager → handle_menu_action called with 'Соедини с менеджером'."""
        bot = _create_bot(mock_config)
        bot.handle_menu_action = AsyncMock()
        callback = _make_callback(data="cta:manager")

        await bot.handle_cta_callback(callback)

        bot.handle_menu_action.assert_awaited_once_with(callback, "Соедини с менеджером")


# ─── Task F: handle_menu_action_text ─────────────────────────────────────────


class TestHandleMenuActionText:
    """handle_menu_action_text sets query text, dispatches, restores original."""

    async def test_handle_menu_action_text_dispatches(self, mock_config):
        """Calls handle_query with message (text temporarily set to query_text)."""
        bot = _create_bot(mock_config)
        bot.handle_query = AsyncMock()
        message = _make_message(text="🏠 Подбор апартаментов")

        await bot.handle_menu_action_text(message, "Подбор апартаментов")

        bot.handle_query.assert_awaited_once_with(message)

    async def test_handle_menu_action_text_restores_original(self, mock_config):
        """Original message.text is restored even when handle_query raises."""
        bot = _create_bot(mock_config)
        original_text = "original button text"
        message = _make_message(text=original_text)
        bot.handle_query = AsyncMock(side_effect=RuntimeError("pipeline error"))

        with pytest.raises(RuntimeError, match="pipeline error"):
            await bot.handle_menu_action_text(message, "Подбор апартаментов")

        assert message.text == original_text


# ─── Task G: _handle_bookmarks display ───────────────────────────────────────


class TestHandleBookmarks:
    """_handle_bookmarks shows empty state or cards + footer."""

    async def test_handle_bookmarks_empty(self, mock_config):
        """No favorites → single answer with empty-state message."""
        bot = _create_bot(mock_config)
        bot._favorites_service = AsyncMock()
        bot._favorites_service.list = AsyncMock(return_value=[])
        message = _make_message()

        await bot._handle_bookmarks(message)

        message.answer.assert_awaited_once()
        sent_text = message.answer.call_args.args[0]
        assert "закладок" in sent_text.lower()

    async def test_handle_bookmarks_with_items(self, mock_config):
        """Favorites list → card answers + footer answer (≥2 total answers)."""
        from telegram_bot.services.favorites_service import Favorite

        bot = _create_bot(mock_config)
        fav = Favorite(
            id=1,
            property_id="prop1",
            property_data={
                "complex_name": "Test Complex",
                "location": "Несебр",
                "property_type": "Апартамент",
                "floor": 3,
                "area_m2": 45.0,
                "view": "море",
                "price_eur": 80000,
            },
            created_at=None,
        )
        bot._favorites_service = AsyncMock()
        bot._favorites_service.list = AsyncMock(return_value=[fav])
        message = _make_message()

        await bot._handle_bookmarks(message)

        # At least 2 answer calls: card + footer
        assert message.answer.await_count >= 2
        # Footer text contains the item count
        footer_text = message.answer.await_args_list[-1].args[0]
        assert "1" in footer_text

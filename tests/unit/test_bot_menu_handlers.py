"""Unit tests for client menu handlers in telegram_bot/bot.py (#628).

Covers the bugs found during audit:
- StateFilter(None) guard on catch-all F.text handler
- phone_router included before catch-all (FSM routing)
- results:* callback routing
- handle_menu_action_text DRY helper
- All ReplyKeyboard button handlers and inline callback handlers
"""

import pytest


pytest.importorskip("aiogram", reason="aiogram not installed")

from unittest.mock import AsyncMock, MagicMock, patch

from telegram_bot.bot import PropertyBot
from telegram_bot.config import BotConfig


@pytest.fixture(autouse=True)
def _reset_phone_router():
    """Detach phone_router between tests so include_router() succeeds."""
    from telegram_bot.handlers.phone_collector import phone_router

    phone_router._parent_router = None
    yield
    phone_router._parent_router = None


@pytest.fixture
def mock_config(monkeypatch):
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


def _create_bot(cfg):
    with (
        patch("telegram_bot.bot.Bot"),
        patch("telegram_bot.integrations.cache.CacheLayerManager"),
        patch("telegram_bot.integrations.embeddings.BGEM3HybridEmbeddings"),
        patch("telegram_bot.integrations.embeddings.BGEM3SparseEmbeddings"),
        patch("telegram_bot.services.qdrant.QdrantService"),
        patch("telegram_bot.graph.config.GraphConfig.create_llm"),
        patch("telegram_bot.graph.config.GraphConfig.create_supervisor_llm"),
    ):
        return PropertyBot(cfg)


def _make_message(text="test", user_id=12345):
    msg = MagicMock()
    msg.text = text
    msg.from_user = MagicMock(id=user_id, first_name="Test")
    msg.chat = MagicMock(id=user_id)
    msg.bot = MagicMock()
    msg.bot.send_chat_action = AsyncMock()
    msg.answer = AsyncMock()
    msg.model_copy = MagicMock(return_value=msg)
    return msg


def _make_callback(data="", user_id=12345):
    cb = MagicMock()
    cb.data = data
    cb.from_user = MagicMock(id=user_id)
    cb.message = MagicMock()
    cb.message.answer = AsyncMock()
    cb.message.edit_text = AsyncMock()
    cb.message.delete = AsyncMock()
    cb.answer = AsyncMock()
    return cb


def _make_state():
    state = AsyncMock()
    state.set_state = AsyncMock()
    state.update_data = AsyncMock()
    state.get_data = AsyncMock(return_value={})
    state.clear = AsyncMock()
    return state


# ---------------------------------------------------------------------------
# Bug #1: StateFilter(None) on catch-all F.text handler
# Without this, handle_query intercepts text input during phone_collector FSM
# ---------------------------------------------------------------------------
class TestStateFilterGuard:
    def test_handle_query_has_two_filters_including_state(self, mock_config):
        """handle_query must have 2 filters (StateFilter + F.text) not just 1."""
        bot = _create_bot(mock_config)
        for h in bot.dp.message.handlers:
            if getattr(h.callback, "__name__", "") == "handle_query":
                assert len(h.filters) == 2, (
                    f"handle_query has {len(h.filters)} filter(s), expected 2 "
                    "(StateFilter(None) + F.text). Without StateFilter, "
                    "phone_collector FSM is broken."
                )
                return
        pytest.fail("handle_query not found in message handlers")

    def test_phone_router_in_sub_routers(self, mock_config):
        """phone_router must be included in dispatcher for FSM to work."""
        bot = _create_bot(mock_config)
        router_names = [r.name for r in bot.dp.sub_routers]
        assert "phone_collector" in router_names


# ---------------------------------------------------------------------------
# Bug #2: results:* callbacks not registered
# ---------------------------------------------------------------------------
class TestResultsCallback:
    async def test_results_more(self, mock_config):
        bot = _create_bot(mock_config)
        cb = _make_callback("results:more")
        await bot.handle_results_callback(cb, _make_state())
        cb.answer.assert_called_once_with("Загрузка...")

    async def test_results_refine(self, mock_config):
        bot = _create_bot(mock_config)
        cb = _make_callback("results:refine")
        await bot.handle_results_callback(cb, _make_state())
        cb.answer.assert_called_once_with("Изменение параметров...")

    async def test_results_viewing_starts_phone_collection(self, mock_config):
        bot = _create_bot(mock_config)
        cb = _make_callback("results:viewing")
        state = _make_state()
        with patch(
            "telegram_bot.handlers.phone_collector.start_phone_collection",
            new_callable=AsyncMock,
        ) as mock_phone:
            await bot.handle_results_callback(cb, state)
            mock_phone.assert_called_once_with(cb, state, source="results")

    async def test_results_unknown_action(self, mock_config):
        bot = _create_bot(mock_config)
        cb = _make_callback("results:something_else")
        await bot.handle_results_callback(cb, _make_state())
        cb.answer.assert_called_once_with()


# ---------------------------------------------------------------------------
# Bug #3: handle_menu_action_text DRY helper (was missing → code duplication)
# ---------------------------------------------------------------------------
class TestMenuActionText:
    async def test_patches_message_and_calls_handle_query(self, mock_config):
        bot = _create_bot(mock_config)
        msg = _make_message("original")
        patched = MagicMock()
        msg.model_copy = MagicMock(return_value=patched)
        bot.handle_query = AsyncMock()

        await bot.handle_menu_action_text(msg, "Подбери апартаменты")

        msg.model_copy.assert_called_once_with(update={"text": "Подбери апартаменты"})
        bot.handle_query.assert_called_once_with(patched)


# ---------------------------------------------------------------------------
# ReplyKeyboard button routing: handle_menu_button
# ---------------------------------------------------------------------------
class TestHandleMenuButton:
    async def test_routes_search(self, mock_config):
        bot = _create_bot(mock_config)
        bot._handle_search = AsyncMock()
        msg = _make_message("🏠 Подбор апартаментов")
        await bot.handle_menu_button(msg, _make_state())
        bot._handle_search.assert_called_once_with(msg)

    async def test_routes_services(self, mock_config):
        bot = _create_bot(mock_config)
        bot._handle_services = AsyncMock()
        msg = _make_message("🔑 Услуги")
        await bot.handle_menu_button(msg, _make_state())
        bot._handle_services.assert_called_once_with(msg)

    async def test_routes_viewing_with_state(self, mock_config):
        bot = _create_bot(mock_config)
        bot._handle_viewing = AsyncMock()
        msg = _make_message("📅 Запись на осмотр")
        state = _make_state()
        await bot.handle_menu_button(msg, state)
        bot._handle_viewing.assert_called_once_with(msg, state)

    async def test_routes_bookmarks(self, mock_config):
        bot = _create_bot(mock_config)
        bot._handle_bookmarks = AsyncMock()
        msg = _make_message("📌 Мои закладки")
        await bot.handle_menu_button(msg, _make_state())
        bot._handle_bookmarks.assert_called_once_with(msg)

    async def test_routes_promotions(self, mock_config):
        bot = _create_bot(mock_config)
        bot._handle_promotions = AsyncMock()
        msg = _make_message("🎁 Акции")
        await bot.handle_menu_button(msg, _make_state())
        bot._handle_promotions.assert_called_once_with(msg)

    async def test_routes_manager(self, mock_config):
        bot = _create_bot(mock_config)
        bot._handle_manager = AsyncMock()
        msg = _make_message("👤 Связь с менеджером")
        await bot.handle_menu_button(msg, _make_state())
        bot._handle_manager.assert_called_once_with(msg)

    async def test_unknown_button_ignored(self, mock_config):
        bot = _create_bot(mock_config)
        msg = _make_message("Random text")
        await bot.handle_menu_button(msg, _make_state())
        msg.answer.assert_not_called()


# ---------------------------------------------------------------------------
# Dedicated handlers
# ---------------------------------------------------------------------------
class TestDedicatedHandlers:
    async def test_search_dispatches_query(self, mock_config):
        bot = _create_bot(mock_config)
        bot.handle_menu_action_text = AsyncMock()
        msg = _make_message()
        await bot._handle_search(msg)
        bot.handle_menu_action_text.assert_called_once_with(msg, "Подбери апартаменты")

    async def test_promotions_dispatches_query(self, mock_config):
        bot = _create_bot(mock_config)
        bot.handle_menu_action_text = AsyncMock()
        msg = _make_message()
        await bot._handle_promotions(msg)
        bot.handle_menu_action_text.assert_called_once_with(msg, "Покажи актуальные акции")

    async def test_manager_dispatches_query(self, mock_config):
        bot = _create_bot(mock_config)
        bot.handle_menu_action_text = AsyncMock()
        msg = _make_message()
        await bot._handle_manager(msg)
        bot.handle_menu_action_text.assert_called_once_with(msg, "Соедини с менеджером")

    async def test_services_shows_inline_menu(self, mock_config):
        bot = _create_bot(mock_config)
        msg = _make_message()
        await bot._handle_services(msg)
        msg.answer.assert_called_once()
        assert msg.answer.call_args[1]["reply_markup"] is not None

    async def test_viewing_starts_phone_collection(self, mock_config):
        bot = _create_bot(mock_config)
        msg = _make_message()
        state = _make_state()
        with patch(
            "telegram_bot.handlers.phone_collector.start_phone_collection",
            new_callable=AsyncMock,
        ) as mock_phone:
            await bot._handle_viewing(msg, state)
            mock_phone.assert_called_once_with(msg, state, source="viewing_main_menu")


# ---------------------------------------------------------------------------
# _handle_bookmarks — all branches
# ---------------------------------------------------------------------------
class TestHandleBookmarks:
    async def test_no_user_returns_silently(self, mock_config):
        bot = _create_bot(mock_config)
        msg = _make_message()
        msg.from_user = None
        await bot._handle_bookmarks(msg)
        msg.answer.assert_not_called()

    async def test_service_unavailable(self, mock_config):
        bot = _create_bot(mock_config)
        bot._favorites_service = None
        msg = _make_message()
        await bot._handle_bookmarks(msg)
        assert "недоступны" in msg.answer.call_args[0][0]

    async def test_empty_list(self, mock_config):
        bot = _create_bot(mock_config)
        svc = AsyncMock()
        svc.list = AsyncMock(return_value=[])
        bot._favorites_service = svc
        msg = _make_message()
        await bot._handle_bookmarks(msg)
        assert "нет закладок" in msg.answer.call_args[0][0]

    async def test_shows_cards_and_footer(self, mock_config):
        bot = _create_bot(mock_config)
        fav = MagicMock()
        fav.property_id = "apt-1"
        fav.property_data = {
            "complex_name": "Test",
            "location": "Beach",
            "property_type": "Apt",
            "floor": 3,
            "area_m2": 50,
            "view": "Sea",
            "price_eur": 100000,
        }
        svc = AsyncMock()
        svc.list = AsyncMock(return_value=[fav])
        bot._favorites_service = svc
        msg = _make_message()
        await bot._handle_bookmarks(msg)
        # 1 property card + 1 footer
        assert msg.answer.call_count == 2


# ---------------------------------------------------------------------------
# handle_service_callback — svc: prefix
# ---------------------------------------------------------------------------
class TestServiceCallback:
    async def test_back_deletes_message(self, mock_config):
        bot = _create_bot(mock_config)
        cb = _make_callback("svc:back")
        await bot.handle_service_callback(cb)
        cb.message.delete.assert_called_once()
        cb.answer.assert_called_once()

    async def test_menu_edits_text(self, mock_config):
        bot = _create_bot(mock_config)
        cb = _make_callback("svc:menu")
        await bot.handle_service_callback(cb)
        cb.message.edit_text.assert_called_once()
        cb.answer.assert_called_once()

    async def test_service_card_edits_text(self, mock_config):
        bot = _create_bot(mock_config)
        cb = _make_callback("svc:passive_income")
        await bot.handle_service_callback(cb)
        cb.message.edit_text.assert_called_once()
        cb.answer.assert_called_once()

    async def test_unknown_data_answers_empty(self, mock_config):
        bot = _create_bot(mock_config)
        cb = _make_callback("unknown:data")
        await bot.handle_service_callback(cb)
        cb.answer.assert_called_once_with()


# ---------------------------------------------------------------------------
# handle_cta_callback — cta: prefix
# ---------------------------------------------------------------------------
class TestCtaCallback:
    async def test_get_offer_starts_phone(self, mock_config):
        bot = _create_bot(mock_config)
        cb = _make_callback("cta:get_offer:property_management")
        state = _make_state()
        with patch(
            "telegram_bot.handlers.phone_collector.start_phone_collection",
            new_callable=AsyncMock,
        ) as mock_phone:
            await bot.handle_cta_callback(cb, state)
            mock_phone.assert_called_once_with(
                cb, state, source="service", source_detail="property_management"
            )

    async def test_manager_sends_message(self, mock_config):
        bot = _create_bot(mock_config)
        cb = _make_callback("cta:manager")
        await bot.handle_cta_callback(cb, _make_state())
        cb.message.answer.assert_called_once()
        assert "Менеджер" in cb.message.answer.call_args[0][0]

    async def test_unknown_action(self, mock_config):
        bot = _create_bot(mock_config)
        cb = _make_callback("cta:unknown")
        await bot.handle_cta_callback(cb, _make_state())
        cb.answer.assert_called_once_with()

    async def test_invalid_prefix(self, mock_config):
        bot = _create_bot(mock_config)
        cb = _make_callback("invalid_data")
        await bot.handle_cta_callback(cb, _make_state())
        cb.answer.assert_called_once_with()


# ---------------------------------------------------------------------------
# handle_favorite_callback — fav: prefix
# ---------------------------------------------------------------------------
class TestFavoriteCallback:
    async def test_add_success(self, mock_config):
        bot = _create_bot(mock_config)
        svc = AsyncMock()
        svc.add = AsyncMock(return_value=MagicMock())
        bot._favorites_service = svc
        cb = _make_callback("fav:add:apt-1")
        await bot.handle_favorite_callback(cb, _make_state())
        svc.add.assert_called_once()
        cb.answer.assert_called_once_with("Добавлено в закладки")

    async def test_add_duplicate(self, mock_config):
        bot = _create_bot(mock_config)
        svc = AsyncMock()
        svc.add = AsyncMock(return_value=None)
        bot._favorites_service = svc
        cb = _make_callback("fav:add:apt-1")
        await bot.handle_favorite_callback(cb, _make_state())
        cb.answer.assert_called_once_with("Уже в закладках")

    async def test_remove_deletes_message(self, mock_config):
        bot = _create_bot(mock_config)
        svc = AsyncMock()
        svc.remove = AsyncMock()
        bot._favorites_service = svc
        cb = _make_callback("fav:remove:apt-1")
        await bot.handle_favorite_callback(cb, _make_state())
        svc.remove.assert_called_once()
        cb.message.delete.assert_called_once()
        cb.answer.assert_called_once_with("Удалено из закладок")

    async def test_viewing_starts_phone(self, mock_config):
        bot = _create_bot(mock_config)
        bot._favorites_service = AsyncMock()
        cb = _make_callback("fav:viewing:apt-1")
        state = _make_state()
        with patch(
            "telegram_bot.handlers.phone_collector.start_phone_collection",
            new_callable=AsyncMock,
        ) as mock_phone:
            await bot.handle_favorite_callback(cb, state)
            mock_phone.assert_called_once_with(cb, state, source="viewing", source_detail="apt-1")

    async def test_viewing_all_starts_phone(self, mock_config):
        bot = _create_bot(mock_config)
        bot._favorites_service = AsyncMock()
        cb = _make_callback("fav:viewing_all")
        state = _make_state()
        with patch(
            "telegram_bot.handlers.phone_collector.start_phone_collection",
            new_callable=AsyncMock,
        ) as mock_phone:
            await bot.handle_favorite_callback(cb, state)
            mock_phone.assert_called_once_with(
                cb, state, source="viewing_all", source_detail="all_favorites"
            )

    async def test_no_service(self, mock_config):
        bot = _create_bot(mock_config)
        bot._favorites_service = None
        cb = _make_callback("fav:add:apt-1")
        await bot.handle_favorite_callback(cb, _make_state())
        cb.answer.assert_called_once_with("Закладки недоступны")

    async def test_no_user(self, mock_config):
        bot = _create_bot(mock_config)
        cb = _make_callback("fav:add:apt-1")
        cb.from_user = None
        await bot.handle_favorite_callback(cb, _make_state())
        cb.answer.assert_called_once_with()

    async def test_malformed_data(self, mock_config):
        bot = _create_bot(mock_config)
        cb = _make_callback("fav")
        await bot.handle_favorite_callback(cb, _make_state())
        cb.answer.assert_called_once_with()

    async def test_unknown_action(self, mock_config):
        bot = _create_bot(mock_config)
        bot._favorites_service = AsyncMock()
        cb = _make_callback("fav:unknown")
        await bot.handle_favorite_callback(cb, _make_state())
        cb.answer.assert_called_once_with()


# ---------------------------------------------------------------------------
# Handler registration: all callback prefixes present
# ---------------------------------------------------------------------------
class TestCallbackRegistration:
    @pytest.mark.parametrize(
        "expected_handler",
        [
            "handle_feedback",
            "handle_hitl_callback",
            "handle_clearcache_callback",
            "handle_service_callback",
            "handle_cta_callback",
            "handle_favorite_callback",
            "handle_results_callback",
        ],
    )
    def test_callback_handler_registered(self, mock_config, expected_handler):
        bot = _create_bot(mock_config)
        registered = {getattr(h.callback, "__name__", "") for h in bot.dp.callback_query.handlers}
        assert expected_handler in registered

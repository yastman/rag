"""Test HotLeadNotifier surface after bot wiring removal (#402, #2625)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from telegram_bot.config import BotConfig


def _make_config() -> BotConfig:
    return BotConfig(
        _env_file=None,
        telegram_token="123456789:ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghi",
        llm_api_key="llm-key",
        llm_base_url="https://api.example.com/v1",
        llm_model="gpt-4o-mini",
        qdrant_url="http://localhost:6333",
        redis_url="redis://localhost:6379",
        rerank_provider="none",
        manager_ids=[123],
        manager_hot_lead_threshold=60,
        manager_hot_lead_dedupe_sec=3600,
    )


def _create_bot(config: BotConfig):
    """Create PropertyBot with deps mocked at actual lookup sites."""
    # Unit conftest may stub aiogram CallbackData / BaseMiddleware as MagicMock.
    # Patch filter + middleware setup at the actual lookup sites used during init.
    # Prefer the _services DI seam so build_services is not exercised here.
    from telegram_bot.bot import PropertyBot
    from telegram_bot.lifecycle.services import Services

    services = Services(
        graph_config=MagicMock(),
        cache=MagicMock(),
        hybrid=MagicMock(),
        embeddings=MagicMock(),
        sparse=MagicMock(),
        qdrant=MagicMock(),
        qdrant_apartments=MagicMock(),
        apartments_service=MagicMock(),
        reranker=None,
        llm=MagicMock(),
        apartment_pipeline=MagicMock(),
        redis_monitor=MagicMock(),
        i18n_hub=None,
    )
    _cb_filter = MagicMock(name="CallbackData.filter")
    with (
        patch("telegram_bot.bot.Bot"),
        patch("telegram_bot.bot.setup_throttling_middleware"),
        patch("telegram_bot.bot.setup_error_handler"),
        patch("telegram_bot.bot.FSMCancelMiddleware", MagicMock()),
        patch(
            "telegram_bot.handlers.demo_handler.DemoCB.filter",
            create=True,
            return_value=_cb_filter,
        ),
        patch("telegram_bot.bot.FeedbackCB.filter", create=True, return_value=_cb_filter),
        patch(
            "telegram_bot.bot.FeedbackReasonCB.filter",
            create=True,
            return_value=_cb_filter,
        ),
        patch(
            "telegram_bot.handlers.favorites_callbacks.FavoriteCB.filter",
            create=True,
            return_value=_cb_filter,
        ),
        patch(
            "telegram_bot.handlers.results_callbacks.ResultsCB.filter",
            create=True,
            return_value=_cb_filter,
        ),
    ):
        return PropertyBot(config, _services=services)


class TestHotLeadNotifierWiring:
    """HotLeadNotifier remains importable; bot no longer owns the attribute (#2625)."""

    def test_bot_has_no_removed_notifier_attribute(self):
        """PropertyBot intentionally no longer declares _hot_lead_notifier (#2625)."""
        bot = _create_bot(_make_config())
        assert not hasattr(bot, "_hot_lead_notifier")

    def test_notifier_importable_and_has_interface(self):
        """HotLeadNotifier is importable and has notify_if_hot method."""
        from telegram_bot.services.crm.hot_lead_notifier import HotLeadNotifier

        assert hasattr(HotLeadNotifier, "notify_if_hot")
        assert callable(getattr(HotLeadNotifier, "notify_if_hot", None))

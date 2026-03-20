"""Regression tests for catalog ownership cutover."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from telegram_bot.bot import PropertyBot
from telegram_bot.config import BotConfig


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


def _sample_result(property_id: str = "apt-1") -> dict:
    return {
        "id": property_id,
        "score": 0.95,
        "payload": {
            "complex_name": "Ocean Vista",
            "city": "Dubai",
            "property_type": "Apartment",
            "floor": 5,
            "area_m2": 55,
            "view_primary": "Sea",
            "view_tags": ["Sea"],
            "price_eur": 250000,
        },
    }


def _make_state(data: dict | None = None) -> MagicMock:
    state = MagicMock()
    state.get_data = AsyncMock(return_value=data or {})
    state.update_data = AsyncMock()
    state.set_data = AsyncMock()
    return state


def _make_message() -> MagicMock:
    message = MagicMock()
    message.answer = AsyncMock(return_value=MagicMock(message_id=999, delete=AsyncMock()))
    message.from_user = MagicMock(id=123)
    message.chat = MagicMock(id=456)
    message.bot = MagicMock(delete_message=AsyncMock())
    return message


@pytest.mark.asyncio
async def test_apartment_fast_path_bootstraps_catalog_runtime_and_dialog() -> None:
    bot = _create_bot()
    bot._cache.store_embedding = AsyncMock()
    bot._cache.store_sparse_embedding = AsyncMock()
    bot._apartments_service.search_with_filters = AsyncMock(
        return_value=([_sample_result("apt-1")], 1)
    )
    bot._embeddings.aembed_hybrid_with_colbert = AsyncMock(
        return_value=([0.1], {"indices": [], "values": []}, None)
    )
    bot._send_property_card = AsyncMock()
    bot._apartment_pipeline.extract = AsyncMock(
        return_value=SimpleNamespace(
            meta=SimpleNamespace(confidence="HIGH", semantic_remainder=""),
            hard=SimpleNamespace(to_filters_dict=dict),
        )
    )

    state = _make_state({"apartment_footer_msg_id": 777, "apartment_results": [{"id": "old"}]})
    dialog_manager = AsyncMock()
    dialog_manager.middleware_data = {"state": state}
    message = _make_message()

    with (
        patch("telegram_bot.services.apartments_service.check_escalation", return_value=False),
        patch(
            "telegram_bot.services.generate_response.generate_response",
            new=AsyncMock(return_value={"response": "ok", "response_sent": True}),
        ),
    ):
        result = await bot._handle_apartment_fast_path(
            user_text="двушка",
            message=message,
            state=state,
            dialog_manager=dialog_manager,
        )

    assert result is not None
    update_kwargs = state.update_data.await_args.kwargs
    runtime = update_kwargs["catalog_runtime"]
    assert runtime["source"] == "free_text"
    assert runtime["results"][0]["id"] == "apt-1"
    assert "apartment_results" not in update_kwargs
    dialog_manager.start.assert_awaited_once()

"""Unit tests for bot-level Langfuse trace metadata (#310: supervisor-only)."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from telegram_bot.bot import PropertyBot
from telegram_bot.config import BotConfig


pytestmark = pytest.mark.skip(
    reason="ARCH-16: requires telegram adapter extra; sdk-agent path removed"
)


def _create_bot(mock_config: BotConfig) -> PropertyBot:
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


@pytest.fixture(autouse=True)
def _isolate_env(monkeypatch):
    """Prevent .env leaking CLIENT_DIRECT_PIPELINE_ENABLED into tests."""
    monkeypatch.delenv("CLIENT_DIRECT_PIPELINE_ENABLED", raising=False)
    monkeypatch.delenv("MANAGERS_GROUP_ID", raising=False)


@pytest.fixture
def mock_config() -> BotConfig:
    return BotConfig(
        telegram_token="test-token",
        voyage_api_key="voyage-key",
        llm_api_key="llm-key",
        llm_base_url="https://api.example.com/v1",
        llm_model="gpt-4o-mini",
        qdrant_url="http://localhost:6333",
        qdrant_api_key="qdrant-key",
        qdrant_collection="test_collection",
        redis_url="redis://localhost:6379",
        rerank_provider="none",
        _env_file=None,
    )


@pytest.fixture
def mock_message() -> MagicMock:
    message = MagicMock()
    message.text = "квартиры до 100000 евро"
    message.from_user = MagicMock()
    message.from_user.id = 123456789
    message.chat = MagicMock()
    message.chat.id = 987654321
    message.bot = MagicMock()
    message.bot.send_chat_action = AsyncMock()
    message.answer = AsyncMock()
    return message


def _mock_agent_result(**overrides):
    """Create a standard SDK agent result dict (#413)."""
    base = {
        "messages": [MagicMock(content="ok")],
    }
    base.update(overrides)
    return base


class TestHandleQueryObservability:
    async def test_handle_query_updates_trace(
        self, mock_config: BotConfig, mock_message: MagicMock
    ):
        from src.core import AssistantResult

        bot = _create_bot(mock_config)
        mock_lf = MagicMock()

        mock_result = AssistantResult(
            response_text="ok",
            route="rag_search",
            request_type="GENERAL",
        )

        with (
            patch("telegram_bot.bot.get_client", return_value=mock_lf),
            patch("telegram_bot.bot.propagate_attributes"),
            patch(
                "telegram_bot.assistant_core_adapter.run_core_text_request",
                new_callable=AsyncMock,
                return_value=mock_result,
            ),
            patch("telegram_bot.bot.maybe_store_semantic_response", new_callable=AsyncMock),
            patch("telegram_bot.bot.ChatActionSender") as mock_cas,
        ):
            mock_cm = AsyncMock()
            mock_cm.__aenter__ = AsyncMock()
            mock_cm.__aexit__ = AsyncMock()
            mock_cas.typing.return_value = mock_cm

            await bot.handle_query(mock_message)

        # update_current_span called: first with query input, then with output/metadata
        assert mock_lf.update_current_span.call_count >= 1
        # The input call (first child span call)
        first_call = mock_lf.update_current_span.call_args_list[0].kwargs
        assert first_call["input"]["query"] == "квартиры до 100000 евро"
        # The output call (metadata with pipeline_mode)
        output_calls = [
            c for c in mock_lf.update_current_span.call_args_list if c.kwargs.get("output")
        ]
        assert output_calls, "update_current_span must be called with output"
        assert output_calls[0].kwargs["output"]["response"] == "ok"

    async def test_handle_query_includes_expected_metadata_fields(
        self,
        mock_config: BotConfig,
        mock_message: MagicMock,
    ):
        from src.core import AssistantResult

        bot = _create_bot(mock_config)
        mock_lf = MagicMock()

        mock_result = AssistantResult(
            response_text="ok",
            route="rag_search",
            request_type="GENERAL",
        )

        with (
            patch("telegram_bot.bot.get_client", return_value=mock_lf),
            patch("telegram_bot.bot.propagate_attributes"),
            patch(
                "telegram_bot.assistant_core_adapter.run_core_text_request",
                new_callable=AsyncMock,
                return_value=mock_result,
            ),
            patch("telegram_bot.bot.maybe_store_semantic_response", new_callable=AsyncMock),
            patch("telegram_bot.bot.ChatActionSender") as mock_cas,
        ):
            mock_cm = AsyncMock()
            mock_cm.__aenter__ = AsyncMock()
            mock_cm.__aexit__ = AsyncMock()
            mock_cas.typing.return_value = mock_cm

            await bot.handle_query(mock_message)

        # Metadata should include pipeline_mode and pipeline_wall_ms
        metadata_calls = [
            c.kwargs["metadata"]
            for c in mock_lf.update_current_span.call_args_list
            if "metadata" in c.kwargs
        ]
        assert metadata_calls, "update_current_span must be called with metadata"
        meta = next(m for m in metadata_calls if "pipeline_mode" in m)
        assert meta["pipeline_mode"] == "sdk_agent"
        assert "pipeline_wall_ms" in meta

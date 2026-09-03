"""Unit tests for bot query handler edge cases."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from telegram_bot.bot import PropertyBot
from tests.unit._bot_config_factory import make_full_bot_config


@pytest.fixture
def mock_config(monkeypatch):
    """Create mock bot config."""
    monkeypatch.delenv("CLIENT_DIRECT_PIPELINE_ENABLED", raising=False)
    monkeypatch.delenv("KOMMO_ACCESS_TOKEN", raising=False)
    return make_full_bot_config()


def _create_bot(mock_config):
    """Create PropertyBot with all deps mocked."""
    with (
        patch("telegram_bot.bot.Bot"),
        patch("src.runtime.integrations.cache.CacheLayerManager"),
        patch("src.runtime.integrations.embeddings.BGEM3HybridEmbeddings"),
        patch("src.runtime.integrations.embeddings.BGEM3SparseEmbeddings"),
        patch("src.runtime.services.qdrant.QdrantService"),
        patch("src.runtime.config.GraphConfig.create_llm"),
        patch("src.runtime.config.GraphConfig.create_supervisor_llm"),
    ):
        return PropertyBot(mock_config)


class TestClientDirectIntentPrecheck:
    """Regression tests for client-direct pre-agent intent detection (#1369)."""

    async def test_pre_agent_intent_check_does_not_call_traced_detector(self, mock_config):
        """PropertyBot precheck must avoid creating extra detect-agent-intent spans."""
        bot = _create_bot(mock_config)
        message = MagicMock()

        with (
            patch(
                "telegram_bot.pipelines.client.detect_agent_intent",
                side_effect=AssertionError(
                    "traced detect_agent_intent must not run in bot precheck"
                ),
            ),
            patch(
                "telegram_bot.pipelines.client.run_client_pipeline",
                AsyncMock(return_value=SimpleNamespace(needs_agent=False, answer="ok")),
            ) as mock_run_pipeline,
        ):
            result = await bot._handle_client_direct_pipeline(
                message=message,
                user_text="какие документы нужны",
                user_id=123,
                session_id="s1",
                role="client",
                query_type="GENERAL",
                rag_result_store={},
            )

        assert result == "ok"
        assert mock_run_pipeline.await_count == 1

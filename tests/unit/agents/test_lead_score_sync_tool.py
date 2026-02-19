"""Tests for crm_sync_lead_score supervisor tool (#384)."""

from __future__ import annotations

import logging
from unittest.mock import AsyncMock

import pytest

from telegram_bot.agents.context import BotContext
from telegram_bot.agents.manager_tools import create_crm_score_sync_tool
from telegram_bot.services.lead_scoring_models import LeadScoreRecord


logger = logging.getLogger(__name__)


@pytest.fixture
def mock_scoring_store():
    store = AsyncMock()
    store.list_pending_sync = AsyncMock(
        return_value=[
            LeadScoreRecord(
                lead_id=11,
                user_id=99,
                session_id="chat-1",
                score_value=74,
                score_band="hot",
                reason_codes=["timeline_asap"],
                kommo_lead_id=5001,
            ),
        ]
    )
    store.mark_synced = AsyncMock()
    store.mark_failed = AsyncMock()
    return store


@pytest.fixture
def mock_kommo_client():
    client = AsyncMock()
    client.update_lead_score = AsyncMock(return_value={"id": 5001})
    return client


@pytest.fixture
def mock_kommo_client_error():
    client = AsyncMock()
    client.update_lead_score = AsyncMock(side_effect=RuntimeError("kommo outage"))
    return client


@pytest.fixture
def runnable_config():
    return {"configurable": {"user_id": 99, "session_id": "chat-1", "role": "manager"}}


class TestCrmSyncLeadScoreTool:
    async def test_syncs_pending_scores(
        self, mock_scoring_store, mock_kommo_client, runnable_config
    ):
        sync_tool = create_crm_score_sync_tool(
            scoring_store=mock_scoring_store,
            kommo_client=mock_kommo_client,
            score_field_id=701,
            band_field_id=702,
        )
        result = await sync_tool.ainvoke({"query": "sync scores"}, config=runnable_config)

        assert "synced 1" in result.lower() or "completed" in result.lower()
        mock_kommo_client.update_lead_score.assert_called_once()
        mock_scoring_store.mark_synced.assert_called_once_with(lead_id=11)

    async def test_fail_soft_on_kommo_error(
        self, mock_scoring_store, mock_kommo_client_error, runnable_config
    ):
        sync_tool = create_crm_score_sync_tool(
            scoring_store=mock_scoring_store,
            kommo_client=mock_kommo_client_error,
            score_field_id=701,
            band_field_id=702,
        )
        result = await sync_tool.ainvoke({"query": "sync scores"}, config=runnable_config)

        assert "failed" in result.lower() or "error" in result.lower()
        mock_scoring_store.mark_failed.assert_called_once()

    async def test_skips_records_without_kommo_lead_id(self, mock_kommo_client, runnable_config):
        store = AsyncMock()
        store.list_pending_sync = AsyncMock(
            return_value=[
                LeadScoreRecord(
                    lead_id=22,
                    user_id=99,
                    session_id="chat-1",
                    score_value=30,
                    score_band="cold",
                    kommo_lead_id=None,
                ),
            ]
        )
        store.mark_synced = AsyncMock()

        sync_tool = create_crm_score_sync_tool(
            scoring_store=store,
            kommo_client=mock_kommo_client,
            score_field_id=701,
            band_field_id=702,
        )
        result = await sync_tool.ainvoke({"query": "sync scores"}, config=runnable_config)

        mock_kommo_client.update_lead_score.assert_not_called()
        assert "skipped" in result.lower() or "0" in result or "no" in result.lower()

    async def test_idempotency_key_includes_score_value(
        self, mock_scoring_store, mock_kommo_client, runnable_config
    ):
        sync_tool = create_crm_score_sync_tool(
            scoring_store=mock_scoring_store,
            kommo_client=mock_kommo_client,
            score_field_id=701,
            band_field_id=702,
        )
        await sync_tool.ainvoke({"query": "sync scores"}, config=runnable_config)

        call_kwargs = mock_kommo_client.update_lead_score.call_args[1]
        key = call_kwargs["idempotency_key"]
        assert key == "lead-score:11:chat-1:74:hot"


def _make_bot_context_for_sync(role: str = "client") -> BotContext:
    """Minimal BotContext for crm_sync_lead_score role-path tests (#479)."""
    return BotContext(
        telegram_user_id=99,
        session_id="chat-1",
        language="ru",
        kommo_client=None,
        history_service=None,
        embeddings=AsyncMock(),
        sparse_embeddings=AsyncMock(),
        qdrant=AsyncMock(),
        cache=AsyncMock(),
        reranker=None,
        llm=AsyncMock(),
        role=role,
    )


class TestCrmSyncLeadScoreToolBotContextPath:
    """Verify crm_sync_lead_score reads role from ctx.role (BotContext path) (#479)."""

    async def test_allows_manager_via_bot_context(self, mock_scoring_store, mock_kommo_client):
        sync_tool = create_crm_score_sync_tool(
            scoring_store=mock_scoring_store,
            kommo_client=mock_kommo_client,
            score_field_id=701,
            band_field_id=702,
        )
        ctx = _make_bot_context_for_sync(role="manager")
        config = {"configurable": {"bot_context": ctx}}
        result = await sync_tool.ainvoke({"query": "sync scores"}, config=config)

        assert "Access denied" not in result
        mock_kommo_client.update_lead_score.assert_called_once()

    async def test_denies_client_via_bot_context(self, mock_scoring_store, mock_kommo_client):
        sync_tool = create_crm_score_sync_tool(
            scoring_store=mock_scoring_store,
            kommo_client=mock_kommo_client,
            score_field_id=701,
            band_field_id=702,
        )
        ctx = _make_bot_context_for_sync(role="client")
        config = {"configurable": {"bot_context": ctx}}
        result = await sync_tool.ainvoke({"query": "sync scores"}, config=config)

        assert "Access denied" in result
        mock_kommo_client.update_lead_score.assert_not_called()

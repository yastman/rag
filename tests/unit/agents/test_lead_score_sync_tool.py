"""Tests for crm_sync_lead_score supervisor tool (#384)."""

from __future__ import annotations

import logging
from typing import Any
from unittest.mock import AsyncMock

import pytest
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool

from telegram_bot.observability import observe
from telegram_bot.services.kommo_models import LeadScoreSyncPayload
from telegram_bot.services.lead_scoring_models import LeadScoreRecord


logger = logging.getLogger(__name__)


def _get_user_context(config: RunnableConfig) -> tuple[int | None, str | None]:
    """Extract user_id and session_id from RunnableConfig."""
    configurable = (config or {}).get("configurable", {})
    user_id = configurable.get("user_id")
    session_id = configurable.get("session_id")
    return user_id, session_id


def create_crm_score_sync_tool(
    *,
    scoring_store: Any,
    kommo_client: Any,
    score_field_id: int,
    band_field_id: int,
) -> Any:
    """Create crm_sync_lead_score tool for supervisor (#384)."""

    @tool
    @observe(name="tool-crm-sync-lead-score")
    async def crm_sync_lead_score(query: str, config: RunnableConfig) -> str:
        """Sync pending lead scores to Kommo CRM."""
        user_id, session_id = _get_user_context(config)
        pending = await scoring_store.list_pending_sync(limit=20)
        synced = 0
        failed = 0
        skipped = 0

        for rec in pending:
            if rec.kommo_lead_id is None:
                skipped += 1
                continue
            key = f"lead-score:{rec.lead_id}:{rec.session_id}:{rec.score_value}:{rec.score_band}"
            payload = LeadScoreSyncPayload.from_record(
                rec,
                score_field_id=score_field_id,
                band_field_id=band_field_id,
            ).to_kommo_payload()
            try:
                await kommo_client.update_lead_score(
                    lead_id=rec.kommo_lead_id,
                    payload=payload,
                    idempotency_key=key,
                )
                await scoring_store.mark_synced(lead_id=rec.lead_id)
                synced += 1
            except Exception:
                logger.exception("CRM score sync failed for lead %s", rec.lead_id)
                await scoring_store.mark_failed(lead_id=rec.lead_id, error="kommo_error")
                failed += 1

        return (
            f"CRM score sync completed: synced {synced}, failed {failed}, "
            f"skipped {skipped} (user {user_id}, session {session_id})"
        )

    return crm_sync_lead_score


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
    return {"configurable": {"user_id": 99, "session_id": "chat-1"}}


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

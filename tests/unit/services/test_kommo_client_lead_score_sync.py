"""Tests for KommoClient.update_lead_score (#384)."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import httpx
import pytest


_DUMMY_REQ = httpx.Request("PATCH", "https://testcompany.kommo.com/api/v4/leads/5001")


@pytest.fixture
def mock_token_store():
    store = AsyncMock()
    store.get_valid_token = AsyncMock(return_value="test_access_token")
    store.force_refresh = AsyncMock(return_value="refreshed_token")
    return store


@pytest.fixture
def kommo_client(mock_token_store):
    from telegram_bot.services.kommo_client import KommoClient

    return KommoClient(subdomain="testcompany", token_store=mock_token_store)


class TestUpdateLeadScore:
    async def test_update_lead_score_sends_patch(self, kommo_client):
        mock_resp = httpx.Response(200, json={"id": 5001}, request=_DUMMY_REQ)
        with patch.object(kommo_client._client, "request", return_value=mock_resp) as mock_req:
            payload = {
                "custom_fields_values": [
                    {"field_id": 701, "values": [{"value": 74}]},
                    {"field_id": 702, "values": [{"value": "hot"}]},
                ]
            }
            result = await kommo_client.update_lead_score(
                lead_id=5001,
                payload=payload,
                idempotency_key="lead-score:11:chat-1:74",
            )

            assert result["id"] == 5001
            call_args = mock_req.call_args
            # Verify PATCH method
            assert call_args[0][0] == "PATCH"
            # Verify idempotency key header
            headers = call_args[1].get("headers", {})
            assert headers.get("X-Idempotency-Key") == "lead-score:11:chat-1:74"

    async def test_update_lead_score_retries_on_429(self, kommo_client):
        """429 should be retried via existing _request retry policy."""
        resp_429 = httpx.Response(429, headers={"Retry-After": "1"}, request=_DUMMY_REQ)
        resp_200 = httpx.Response(200, json={"id": 5001}, request=_DUMMY_REQ)
        with patch.object(kommo_client._client, "request", side_effect=[resp_429, resp_200]):
            result = await kommo_client.update_lead_score(
                lead_id=5001,
                payload={"custom_fields_values": []},
                idempotency_key="lead-score:11:chat-1:74",
            )
            assert result["id"] == 5001

    async def test_update_lead_score_retries_on_5xx(self, kommo_client):
        resp_503 = httpx.Response(503, request=_DUMMY_REQ)
        resp_200 = httpx.Response(200, json={"id": 5001}, request=_DUMMY_REQ)
        with patch.object(kommo_client._client, "request", side_effect=[resp_503, resp_200]):
            result = await kommo_client.update_lead_score(
                lead_id=5001,
                payload={"custom_fields_values": []},
                idempotency_key="lead-score:11:chat-1:74",
            )
            assert result["id"] == 5001

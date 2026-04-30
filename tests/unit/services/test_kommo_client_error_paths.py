"""Tests for KommoClient error and retry paths (#1090)."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import httpx
import pytest
from tenacity import wait_none


_DUMMY_REQ = httpx.Request("GET", "https://test-co.kommo.com/api/v4/leads/1")


@pytest.fixture
def mock_token_store():
    store = AsyncMock()
    store.get_valid_token = AsyncMock(return_value="test-token")
    store.force_refresh = AsyncMock(return_value="refreshed-token")
    return store


@pytest.fixture
def kommo_client(mock_token_store):
    from telegram_bot.services.kommo_client import KommoClient

    return KommoClient(subdomain="test-co", token_store=mock_token_store)


async def test_400_bad_request_raises_http_error_without_force_refresh(
    kommo_client, mock_token_store, httpx_mock
):
    """400 Bad Request raises HTTPStatusError and does not call force_refresh."""
    httpx_mock.add_response(
        url="https://test-co.kommo.com/api/v4/leads/1",
        status_code=400,
    )

    with pytest.raises(httpx.HTTPStatusError, match="400"):
        await kommo_client.get_lead(1)

    mock_token_store.force_refresh.assert_not_called()


async def test_429_retries_and_succeeds(kommo_client):
    """429 retries and then succeeds."""
    resp_429 = httpx.Response(429, headers={"Retry-After": "1"}, request=_DUMMY_REQ)
    resp_200 = httpx.Response(200, json={"id": 1, "name": "Lead"}, request=_DUMMY_REQ)
    with (
        patch.object(kommo_client._request.retry, "wait", wait_none()),
        patch.object(kommo_client._client, "request", side_effect=[resp_429, resp_200]),
    ):
        lead = await kommo_client.get_lead(1)
        assert lead.id == 1


async def test_503_retries_and_succeeds(kommo_client):
    """503 retries and then succeeds."""
    resp_503 = httpx.Response(503, request=_DUMMY_REQ)
    resp_200 = httpx.Response(200, json={"id": 1, "name": "Lead"}, request=_DUMMY_REQ)
    with (
        patch.object(kommo_client._request.retry, "wait", wait_none()),
        patch.object(kommo_client._client, "request", side_effect=[resp_503, resp_200]),
    ):
        lead = await kommo_client.get_lead(1)
        assert lead.id == 1


async def test_read_timeout_retries_and_succeeds(kommo_client):
    """httpx.ReadTimeout retries and then succeeds."""
    resp_200 = httpx.Response(200, json={"id": 1, "name": "Lead"}, request=_DUMMY_REQ)
    with (
        patch.object(kommo_client._request.retry, "wait", wait_none()),
        patch.object(
            kommo_client._client,
            "request",
            side_effect=[httpx.ReadTimeout("timed out"), httpx.ReadTimeout("timed out"), resp_200],
        ),
    ):
        lead = await kommo_client.get_lead(1)
        assert lead.id == 1


async def test_401_with_force_refresh_runtime_error_raises_original_401(
    mock_token_store, httpx_mock
):
    """401 with force_refresh raising RuntimeError raises the original 401 HTTPStatusError."""
    from telegram_bot.services.kommo_client import KommoClient

    mock_token_store.force_refresh = AsyncMock(
        side_effect=RuntimeError("No refresh_token available for Kommo.")
    )
    client = KommoClient(subdomain="test-co", token_store=mock_token_store)

    httpx_mock.add_response(
        url="https://test-co.kommo.com/api/v4/leads/1",
        status_code=401,
    )

    with pytest.raises(httpx.HTTPStatusError, match="401"):
        await client.get_lead(1)

    mock_token_store.force_refresh.assert_called_once()

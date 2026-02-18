"""Tests for Kommo async client with rate limiting and 429 handling (#389)."""

from unittest.mock import AsyncMock, patch

import httpx
import pytest

from telegram_bot.services.kommo_client import KommoClient


@pytest.fixture
def token_store():
    store = AsyncMock()
    store.get_valid_token = AsyncMock(return_value="token")
    return store


@pytest.fixture
def client(token_store):
    return KommoClient(
        subdomain="demo",
        token_store=token_store,
        rate_limit_rps=7,
        max_retries=3,
    )


async def test_request_honors_retry_after_on_429(client):
    req = httpx.Request("GET", "https://demo.kommo.com/api/v4/leads")
    resp_429 = httpx.Response(429, json={"retry_after": 2}, request=req)
    resp_200 = httpx.Response(200, json={"ok": True}, request=req)

    with (
        patch.object(client._http, "request", side_effect=[resp_429, resp_200]),
        patch("telegram_bot.services.kommo_client.asyncio.sleep", new=AsyncMock()) as sleep_mock,
    ):
        payload = await client._request_json("GET", "/leads")

    assert payload == {"ok": True}
    sleep_mock.assert_awaited_with(2.0)


async def test_request_raises_after_max_retries(client):
    req = httpx.Request("GET", "https://demo.kommo.com/api/v4/leads")
    resp_429 = httpx.Response(429, json={"retry_after": 1}, request=req)

    with (
        patch.object(client._http, "request", return_value=resp_429),
        patch("telegram_bot.services.kommo_client.asyncio.sleep", new=AsyncMock()),
    ):
        with pytest.raises(httpx.HTTPStatusError):
            await client._request_json("GET", "/leads")


async def test_successful_request(client):
    req = httpx.Request("GET", "https://demo.kommo.com/api/v4/leads")
    resp_200 = httpx.Response(200, json={"_embedded": {"leads": []}}, request=req)

    with patch.object(client._http, "request", return_value=resp_200):
        result = await client._request_json("GET", "/leads")

    assert result == {"_embedded": {"leads": []}}


async def test_close_closes_http_client(client):
    with patch.object(client._http, "aclose", new=AsyncMock()) as close_mock:
        await client.close()
    close_mock.assert_awaited_once()

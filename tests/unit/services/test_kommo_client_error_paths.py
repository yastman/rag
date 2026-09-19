"""Tests for KommoClient error and retry paths (#1090)."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import httpx
import pytest
from tenacity import wait_none

from src.services.kommo_client import KommoOutcomeUncertain
from src.services.kommo_models import LeadCreate


_DUMMY_REQ = httpx.Request("GET", "https://test-co.kommo.com/api/v4/leads/1")


@pytest.fixture
def mock_token_store():
    store = AsyncMock()
    store.get_valid_token = AsyncMock(return_value="123456789:ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghi")
    store.force_refresh = AsyncMock(return_value="refreshed-token")
    return store


@pytest.fixture
def kommo_client(mock_token_store):
    from telegram_bot.services.crm.kommo_client import KommoClient

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
    from telegram_bot.services.crm.kommo_client import KommoClient

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


async def test_accepted_write_lost_response_is_never_reissued(kommo_client, httpx_mock):
    accepted_writes = []

    def accepted_then_lost(request):
        accepted_writes.append((request.method, request.url.path))
        raise httpx.ReadTimeout("response lost after acceptance")

    httpx_mock.add_callback(accepted_then_lost)
    with (
        patch.object(kommo_client._request.retry, "wait", wait_none()),
        pytest.raises(KommoOutcomeUncertain, match="reconcile before retrying"),
    ):
        await kommo_client.create_lead(LeadCreate(name="example"))
    assert accepted_writes == [("POST", "/api/v4/leads")]


@pytest.mark.parametrize("method", ["POST", "PATCH"])
@pytest.mark.parametrize(
    "failure",
    [
        httpx.ReadTimeout,
        httpx.WriteTimeout,
        httpx.ReadError,
        httpx.WriteError,
        httpx.RemoteProtocolError,
    ],
)
async def test_mutation_transport_loss_is_uncertain_once(kommo_client, method, failure, caplog):
    with (
        patch.object(kommo_client._request.retry, "wait", wait_none()),
        patch.object(kommo_client._client, "request", side_effect=failure("private-token")) as send,
        pytest.raises(KommoOutcomeUncertain) as error,
    ):
        await kommo_client._request(method, "/leads", json={"name": "private-person"})
    assert send.await_count == 1
    assert "private" not in str(error.value)
    assert "private" not in caplog.text


@pytest.mark.parametrize("status", [500, 502, 503, 504])
async def test_mutation_server_error_is_uncertain_once(kommo_client, status):
    with (
        patch.object(kommo_client._request.retry, "wait", wait_none()),
        patch.object(kommo_client._client, "request", return_value=httpx.Response(status)) as send,
        pytest.raises(KommoOutcomeUncertain),
    ):
        await kommo_client._request("PATCH", "/leads/1", json={"price": 1})
    assert send.await_count == 1


async def test_unverified_idempotency_header_does_not_enable_replay(kommo_client):
    with (
        patch.object(kommo_client._request.retry, "wait", wait_none()),
        patch.object(
            kommo_client._client, "request", side_effect=httpx.ReadTimeout("lost")
        ) as send,
        pytest.raises(KommoOutcomeUncertain),
    ):
        await kommo_client.update_lead_score(lead_id=1, payload={}, idempotency_key="opaque-key")
    assert send.await_count == 1
    assert send.call_args.kwargs["headers"] == {"X-Idempotency-Key": "opaque-key"}


@pytest.mark.parametrize("failure", [httpx.ConnectError, httpx.ConnectTimeout, httpx.PoolTimeout])
async def test_mutation_presend_failures_retain_bounded_retry(kommo_client, failure, caplog):
    with (
        patch.object(kommo_client._request.retry, "wait", wait_none()),
        patch.object(kommo_client._client, "request", side_effect=failure("private-token")) as send,
        pytest.raises(failure),
    ):
        await kommo_client._request("POST", "/leads", json={"name": "private-person"})
    assert send.await_count == 3
    assert "private" not in caplog.text


@pytest.mark.parametrize("status", [400, 401, 403, 422])
async def test_rejected_mutation_is_distinct_from_uncertain(kommo_client, status):
    with (
        patch.object(
            kommo_client._client, "request", return_value=httpx.Response(status, request=_DUMMY_REQ)
        ) as send,
        pytest.raises(httpx.HTTPStatusError),
    ):
        await kommo_client._request("POST", "/leads")
    assert send.await_count == 1


async def test_rate_limit_rejection_can_retry_without_logging_contact_query(kommo_client, caplog):
    request = httpx.Request("POST", "https://test-co.kommo.com/api/v4/leads?private-person")
    with (
        patch.object(kommo_client._request.retry, "wait", wait_none()),
        patch.object(
            kommo_client._client,
            "request",
            side_effect=[
                httpx.Response(429, request=request),
                httpx.Response(204, request=request),
            ],
        ) as send,
    ):
        assert await kommo_client._request("POST", "/leads") == {}
    assert send.await_count == 2
    assert "Retrying Kommo" in caplog.text
    assert "private-person" not in caplog.text


@pytest.mark.parametrize(
    "body",
    [
        b'{"_embedded":',
        b"[]",
        b"{}",
        b'{"_embedded":{"leads":[]}}',
        b'{"_embedded":{"leads":[{}]}}',
    ],
)
async def test_unusable_write_acknowledgement_is_uncertain(kommo_client, httpx_mock, body):
    httpx_mock.add_response(method="POST", content=body)
    with pytest.raises(KommoOutcomeUncertain):
        await kommo_client.create_lead(LeadCreate(name="example"))
    assert len(httpx_mock.get_requests()) == 1


async def test_malformed_read_is_not_a_mutation_outcome(kommo_client, httpx_mock):
    httpx_mock.add_response(method="GET", content=b'{"id":')
    with pytest.raises(ValueError):
        await kommo_client.get_lead(1)
    assert len(httpx_mock.get_requests()) == 1


async def test_mutation_cancellation_is_never_retried(kommo_client):
    import asyncio

    with (
        patch.object(kommo_client._client, "request", side_effect=asyncio.CancelledError) as send,
        pytest.raises(asyncio.CancelledError),
    ):
        await kommo_client.create_lead(LeadCreate(name="example"))
    assert send.await_count == 1

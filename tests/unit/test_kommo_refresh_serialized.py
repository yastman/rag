"""Regression test: concurrent force_refresh calls must be serialized.

Two near-simultaneous refreshes MUST NOT both POST the refresh token to Kommo —
Kommo rotates on the first request, so the second would get invalid_grant.
"""

from __future__ import annotations

import asyncio
from unittest.mock import patch

import pytest

from src.services.kommo_tokens import KommoTokenStore


class FakeRedis:
    """Minimal Redis stand-in that actually tracks hset writes."""

    def __init__(self, initial: dict[bytes, bytes]) -> None:
        self._store: dict[bytes, bytes] = dict(initial)

    async def hgetall(self, key: str) -> dict[bytes, bytes]:
        return dict(self._store)

    async def hset(self, key: str, mapping: dict) -> None:
        for k, v in mapping.items():
            self._store[k.encode() if isinstance(k, str) else k] = (
                v.encode() if isinstance(v, str) else str(v).encode()
            )


@pytest.fixture
def fake_redis():
    return FakeRedis(
        {
            b"access_token": b"old-access",
            b"refresh_token": b"old-refresh",
            b"expires_at": b"0",  # already expired
        }
    )


@pytest.fixture
def store(fake_redis):
    return KommoTokenStore(
        redis=fake_redis,
        client_id="cid",
        client_secret="csec",
        subdomain="test",
        redirect_uri="https://example.com/cb",
    )


@pytest.mark.asyncio
async def test_kommo_refresh_serialized(store):
    """Concurrent force_refresh calls must result in exactly one HTTP POST."""
    call_count = 0

    async def fake_token_request(payload):
        nonlocal call_count
        call_count += 1
        await asyncio.sleep(0)  # yield to allow concurrent task to run
        return {
            "access_token": "new-access",
            "refresh_token": "new-refresh",
            "expires_in": 86400,
        }

    with patch.object(store, "_token_request", side_effect=fake_token_request):
        # Fire two concurrent force_refresh calls
        results = await asyncio.gather(
            store.force_refresh(),
            store.force_refresh(),
        )

    # Exactly one HTTP POST should have occurred
    assert call_count == 1, f"Expected 1 HTTP call, got {call_count}"
    # Both callers get the same access token
    assert results[0] == results[1] == "new-access"

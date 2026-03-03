"""Unit tests for KommoClient (#717).

Tests upsert_contact ContactUpdate construction — fix for mypy arg-type error.
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from telegram_bot.services.kommo_client import KommoClient
from telegram_bot.services.kommo_models import Contact, ContactCreate, ContactUpdate


@pytest.fixture
def mock_token_store() -> AsyncMock:
    ts = AsyncMock()
    ts.get_valid_token.return_value = "test-token"
    ts.force_refresh.return_value = "test-token"
    return ts


@pytest.fixture
def kommo_client(mock_token_store: AsyncMock) -> KommoClient:
    return KommoClient(subdomain="testdomain", token_store=mock_token_store)


class TestUpsertContactUpdate:
    """upsert_contact fills empty name fields via ContactUpdate with explicit args."""

    async def test_updates_first_name_when_empty(self, kommo_client: KommoClient) -> None:
        """Existing contact with empty first_name gets ContactUpdate(first_name=...) called."""
        existing_raw = {"id": 42, "first_name": None, "last_name": "Doe"}
        kommo_client._request = AsyncMock(  # type: ignore[method-assign]
            return_value={"_embedded": {"contacts": [existing_raw]}}
        )
        captured: list[tuple[int, ContactUpdate]] = []

        async def _mock_update(contact_id: int, update: ContactUpdate) -> Contact:
            captured.append((contact_id, update))
            return Contact(id=contact_id)

        kommo_client.update_contact = _mock_update  # type: ignore[method-assign]

        await kommo_client.upsert_contact("+1234567890", ContactCreate(first_name="John"))

        assert len(captured) == 1
        cid, cu = captured[0]
        assert cid == 42
        assert isinstance(cu, ContactUpdate)
        assert cu.first_name == "John"
        assert cu.last_name is None

    async def test_updates_last_name_when_empty(self, kommo_client: KommoClient) -> None:
        """Existing contact with empty last_name gets ContactUpdate(last_name=...) called."""
        existing_raw = {"id": 7, "first_name": "Jane", "last_name": None}
        kommo_client._request = AsyncMock(  # type: ignore[method-assign]
            return_value={"_embedded": {"contacts": [existing_raw]}}
        )
        captured: list[tuple[int, ContactUpdate]] = []

        async def _mock_update(contact_id: int, update: ContactUpdate) -> Contact:
            captured.append((contact_id, update))
            return Contact(id=contact_id)

        kommo_client.update_contact = _mock_update  # type: ignore[method-assign]

        await kommo_client.upsert_contact(
            "+1234567890", ContactCreate(first_name="Jane", last_name="Smith")
        )

        assert len(captured) == 1
        cid, cu = captured[0]
        assert cid == 7
        assert isinstance(cu, ContactUpdate)
        assert cu.first_name is None
        assert cu.last_name == "Smith"

    async def test_no_update_when_names_already_filled(self, kommo_client: KommoClient) -> None:
        """If existing contact already has all names, update_contact must NOT be called."""
        existing_raw = {"id": 99, "first_name": "Alice", "last_name": "Wonder"}
        kommo_client._request = AsyncMock(  # type: ignore[method-assign]
            return_value={"_embedded": {"contacts": [existing_raw]}}
        )
        update_called = False

        async def _mock_update(contact_id: int, update: ContactUpdate) -> Contact:
            nonlocal update_called
            update_called = True
            return Contact(id=contact_id)

        kommo_client.update_contact = _mock_update  # type: ignore[method-assign]

        result = await kommo_client.upsert_contact(
            "+1234567890", ContactCreate(first_name="X", last_name="Y")
        )

        assert not update_called
        assert result.id == 99

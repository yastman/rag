"""Tests for smart upsert_contact in KommoClient."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest


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


async def test_upsert_returns_existing_contact_unchanged(kommo_client, httpx_mock) -> None:
    """When existing contact already has first_name, no PATCH is sent."""
    from telegram_bot.services.kommo_models import ContactCreate

    httpx_mock.add_response(
        url="https://test-co.kommo.com/api/v4/contacts?query=%2B1234567890",
        json={"_embedded": {"contacts": [{"id": 42, "first_name": "Alice", "last_name": "Smith"}]}},
    )

    contact = await kommo_client.upsert_contact("+1234567890", ContactCreate(first_name="Bob"))
    assert contact.id == 42
    assert contact.first_name == "Alice"


async def test_upsert_updates_empty_first_name(kommo_client, httpx_mock) -> None:
    """When existing contact has empty first_name, PATCH is sent with the new value."""
    from telegram_bot.services.kommo_models import ContactCreate

    httpx_mock.add_response(
        url="https://test-co.kommo.com/api/v4/contacts?query=%2B1234567890",
        json={"_embedded": {"contacts": [{"id": 99, "first_name": None, "last_name": None}]}},
    )
    httpx_mock.add_response(
        url="https://test-co.kommo.com/api/v4/contacts/99",
        method="PATCH",
        json={"id": 99, "first_name": "Bob", "last_name": None},
    )

    contact = await kommo_client.upsert_contact("+1234567890", ContactCreate(first_name="Bob"))
    assert contact.id == 99


async def test_upsert_creates_new_when_not_found(kommo_client, httpx_mock) -> None:
    """When no contact found by phone, a new one is created via POST."""
    from telegram_bot.services.kommo_models import ContactCreate

    httpx_mock.add_response(
        url="https://test-co.kommo.com/api/v4/contacts?query=%2B9990000000",
        json={},
    )
    httpx_mock.add_response(
        url="https://test-co.kommo.com/api/v4/contacts",
        method="POST",
        json={"_embedded": {"contacts": [{"id": 7, "first_name": "Charlie"}]}},
    )

    contact = await kommo_client.upsert_contact("+9990000000", ContactCreate(first_name="Charlie"))
    assert contact.id == 7

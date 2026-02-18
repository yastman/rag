"""Tests for UserService (asyncpg CRUD)."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from telegram_bot.services.user_service import UserService


@pytest.fixture
def mock_pool():
    return AsyncMock()


@pytest.fixture
def service(mock_pool):
    return UserService(pool=mock_pool)


@pytest.mark.asyncio
async def test_get_or_create_existing_user(service, mock_pool):
    """Existing user returned from DB."""
    row = {
        "id": 1,
        "telegram_id": 123,
        "locale": "uk",
        "role": "client",
        "first_name": "Test",
        "telegram_language_code": "uk",
        "notifications_enabled": True,
    }
    mock_pool.fetchrow.return_value = row

    user = await service.get_or_create(telegram_id=123, first_name="Test")
    assert user.telegram_id == 123
    assert user.locale == "uk"
    mock_pool.fetchrow.assert_called_once()


@pytest.mark.asyncio
async def test_get_or_create_new_user(service, mock_pool):
    """New user created when not found."""
    # First call (SELECT) returns None, second call (INSERT) returns new row
    mock_pool.fetchrow.side_effect = [
        None,  # SELECT
        {
            "id": 2,
            "telegram_id": 456,
            "locale": "ru",
            "role": "client",
            "first_name": "New",
            "telegram_language_code": "ru",
            "notifications_enabled": True,
        },  # INSERT ... RETURNING
    ]

    user = await service.get_or_create(telegram_id=456, first_name="New", language_code="ru")
    assert user.telegram_id == 456
    assert user.locale == "ru"
    assert mock_pool.fetchrow.call_count == 2


@pytest.mark.asyncio
async def test_get_role(service, mock_pool):
    """Get user role by telegram_id."""
    mock_pool.fetchval.return_value = "manager"
    role = await service.get_role(telegram_id=123)
    assert role == "manager"


@pytest.mark.asyncio
async def test_get_role_unknown_user(service, mock_pool):
    """Unknown user returns 'client' as default."""
    mock_pool.fetchval.return_value = None
    role = await service.get_role(telegram_id=999)
    assert role == "client"


@pytest.mark.asyncio
async def test_set_locale(service, mock_pool):
    """Set user locale (PG + Redis cache concept)."""
    mock_pool.execute.return_value = "UPDATE 1"
    await service.set_locale(telegram_id=123, locale="en")
    mock_pool.execute.assert_called_once()


@pytest.mark.asyncio
async def test_get_locale(service, mock_pool):
    """Get user locale."""
    mock_pool.fetchval.return_value = "uk"
    locale = await service.get_locale(telegram_id=123)
    assert locale == "uk"


@pytest.mark.asyncio
async def test_get_locale_default(service, mock_pool):
    """Unknown user returns default locale."""
    mock_pool.fetchval.return_value = None
    locale = await service.get_locale(telegram_id=999)
    assert locale == "ru"

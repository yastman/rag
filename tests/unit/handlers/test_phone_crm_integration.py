# tests/unit/handlers/test_phone_crm_integration.py
"""TDD tests for phone collector -> Kommo CRM integration (#660)."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from telegram_bot.services.crm.kommo_models import Contact, Lead, Note, Task


@pytest.fixture
def mock_kommo():
    """AsyncMock Kommo client with all required methods."""
    kommo = AsyncMock()
    kommo.upsert_contact = AsyncMock(return_value=Contact(id=1, first_name="Iван"))
    kommo.create_lead = AsyncMock(return_value=Lead(id=101, name="Консультация — Iван"))
    kommo.link_contact_to_lead = AsyncMock(return_value=None)
    kommo.create_task = AsyncMock(return_value=Task(id=201, entity_id=101))
    kommo.add_note = AsyncMock(return_value=Note(id=301))
    return kommo


@pytest.fixture
def mock_message():
    """AsyncMock aiogram Message with phone text."""
    from types import SimpleNamespace

    msg = AsyncMock()
    msg.text = "+380501234567"
    msg.from_user = SimpleNamespace(id=12345, first_name="Iван", last_name=None, username=None)
    msg.answer = AsyncMock()
    return msg


@pytest.fixture
def mock_state():
    """AsyncMock FSMContext returning service_key."""
    state = AsyncMock()
    state.get_data = AsyncMock(return_value={"service_key": "manager", "viewing_objects": []})
    state.clear = AsyncMock()
    return state


@pytest.fixture
def mock_config():
    """Patch load_services_config with test data."""
    return {
        "entry_points": {
            "manager": {
                "crm_title": "Консультация",
                "phone_success": "✅ Заявка оформлена! Менеджер перезвонит вам в ближайшее время.",
            }
        }
    }


class TestPhoneCollectorSearchSummary:
    async def test_sends_success_before_crm_work(self, mock_kommo, mock_config) -> None:
        """Юзер получает подтверждение до CRM-работы."""
        from telegram_bot.handlers.phone_collector import on_phone_received

        message = AsyncMock()
        message.text = "+359881234567"
        message.from_user = SimpleNamespace(
            id=42, first_name="Ivan", last_name=None, username="ivan"
        )

        state = AsyncMock()
        state.get_data = AsyncMock(return_value={"service_key": "viewing", "viewing_objects": []})

        mock_store = AsyncMock()
        mock_store.get_user_events = AsyncMock(
            return_value=[
                {
                    "query": "двушка",
                    "filters": {"rooms": 2},
                    "results_count": 5,
                    "created_at": "2026-03-03 14:00:00+00",
                },
            ]
        )

        with patch(
            "src.services.content_loader.load_services_config",
            return_value=mock_config,
        ):
            await on_phone_received(
                message,
                state,
                kommo_client=mock_kommo,
                search_event_store=mock_store,
            )

        # message.answer вызван — подтверждение заявки
        message.answer.assert_called_once()

    async def test_note_includes_search_summary(self, mock_kommo, mock_config) -> None:
        """Нота содержит самари поиска."""
        from telegram_bot.handlers.phone_collector import on_phone_received

        message = AsyncMock()
        message.text = "+359881234567"
        message.from_user = SimpleNamespace(
            id=42, first_name="Ivan", last_name=None, username="ivan"
        )

        state = AsyncMock()
        state.get_data = AsyncMock(return_value={"service_key": "viewing", "viewing_objects": []})

        mock_store = AsyncMock()
        mock_store.get_user_events = AsyncMock(
            return_value=[
                {
                    "query": "двушка у моря",
                    "filters": {"rooms": 2, "view_tags": ["sea"]},
                    "results_count": 12,
                    "created_at": "2026-03-03 14:00:00+00",
                },
            ]
        )

        with patch(
            "src.services.content_loader.load_services_config",
            return_value=mock_config,
        ):
            await on_phone_received(
                message,
                state,
                kommo_client=mock_kommo,
                search_event_store=mock_store,
            )

        # add_note вызван с текстом включающим самари
        mock_kommo.add_note.assert_called_once()
        note_text = mock_kommo.add_note.call_args[0][2]
        assert "двушка у моря" in note_text

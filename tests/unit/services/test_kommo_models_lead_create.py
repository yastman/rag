"""Tests for LeadCreate model additions."""

from telegram_bot.services.kommo_models import LeadCreate


def test_lead_create_has_responsible_user_id() -> None:
    lead = LeadCreate(name="Test Lead", responsible_user_id=123)
    assert lead.responsible_user_id == 123


def test_lead_create_responsible_user_id_defaults_to_none() -> None:
    lead = LeadCreate(name="Test Lead")
    assert lead.responsible_user_id is None


def test_lead_create_serializes_responsible_user_id() -> None:
    lead = LeadCreate(name="Test", responsible_user_id=42)
    dumped = lead.model_dump(exclude_none=True)
    assert dumped["responsible_user_id"] == 42

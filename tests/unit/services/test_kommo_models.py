"""Tests for Kommo CRM Pydantic models (#413)."""

from __future__ import annotations


def test_lead_create_minimal():
    """LeadCreate with only required fields."""
    from telegram_bot.services.kommo_models import LeadCreate

    lead = LeadCreate(name="Показ: Иван")
    assert lead.name == "Показ: Иван"
    assert lead.budget is None
    assert lead.pipeline_id is None


def test_lead_create_full():
    """LeadCreate with all fields."""
    from telegram_bot.services.kommo_models import LeadCreate

    lead = LeadCreate(name="Показ", budget=100000, pipeline_id=1, status_id=2)
    assert lead.budget == 100000


def test_lead_model():
    """Lead response model from API."""
    from telegram_bot.services.kommo_models import Lead

    lead = Lead(id=123, name="Показ", budget=50000, status_id=1, pipeline_id=2)
    assert lead.id == 123


def test_contact_create():
    """ContactCreate with phone."""
    from telegram_bot.services.kommo_models import ContactCreate

    contact = ContactCreate(first_name="Иван", phone="+359888123456")
    assert contact.first_name == "Иван"
    assert contact.phone == "+359888123456"


def test_contact_model():
    """Contact response model."""
    from telegram_bot.services.kommo_models import Contact

    contact = Contact(id=456, first_name="Иван")
    assert contact.id == 456


def test_task_create():
    """TaskCreate for CRM task."""
    from telegram_bot.services.kommo_models import TaskCreate

    task = TaskCreate(
        text="Показ квартиры",
        entity_id=123,
        entity_type="leads",
        complete_till=1708300800,
    )
    assert task.text == "Показ квартиры"
    assert task.entity_id == 123


def test_note_response():
    """Note response model."""
    from telegram_bot.services.kommo_models import Note

    note = Note(id=789, text="Клиент заинтересован")
    assert note.id == 789

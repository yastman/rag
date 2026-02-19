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


# --- Phase 2: extended models (#443) ---


def test_lead_with_responsible_user_id():
    """Lead model accepts responsible_user_id field."""
    from telegram_bot.services.kommo_models import Lead

    lead = Lead(id=1, name="Deal", responsible_user_id=42)
    assert lead.responsible_user_id == 42


def test_lead_with_loss_reason_id():
    """Lead model accepts loss_reason_id field."""
    from telegram_bot.services.kommo_models import Lead

    lead = Lead(id=1, name="Lost Deal", loss_reason_id=7)
    assert lead.loss_reason_id == 7


def test_task_with_extended_fields():
    """Task model accepts is_completed, responsible_user_id, created_at, updated_at."""
    from telegram_bot.services.kommo_models import Task

    task = Task(
        id=200,
        text="Follow up",
        responsible_user_id=42,
        is_completed=False,
        created_at=1700000000,
        updated_at=1700003600,
    )
    assert task.responsible_user_id == 42
    assert task.is_completed is False
    assert task.created_at == 1700000000
    assert task.updated_at == 1700003600


def test_task_result_field():
    """Task model accepts result dict field."""
    from telegram_bot.services.kommo_models import Task

    task = Task(id=201, text="Done", is_completed=True, result={"text": "Completed"})
    assert task.result == {"text": "Completed"}


def test_contact_update_minimal():
    """ContactUpdate model with minimal fields."""
    from telegram_bot.services.kommo_models import ContactUpdate

    update = ContactUpdate(first_name="Ivan")
    assert update.first_name == "Ivan"
    assert update.last_name is None
    assert update.custom_fields_values is None


def test_contact_update_build_phone():
    """ContactUpdate.build_contact_fields builds phone entry."""
    from telegram_bot.services.kommo_models import ContactUpdate

    fields = ContactUpdate.build_contact_fields(phone="+380991234567")
    assert len(fields) == 1
    assert fields[0]["field_code"] == "PHONE"
    assert fields[0]["values"][0]["value"] == "+380991234567"


def test_contact_update_build_email():
    """ContactUpdate.build_contact_fields builds email entry."""
    from telegram_bot.services.kommo_models import ContactUpdate

    fields = ContactUpdate.build_contact_fields(email="test@example.com")
    assert len(fields) == 1
    assert fields[0]["field_code"] == "EMAIL"
    assert fields[0]["values"][0]["value"] == "test@example.com"


def test_contact_update_build_phone_and_email():
    """ContactUpdate.build_contact_fields builds both phone and email."""
    from telegram_bot.services.kommo_models import ContactUpdate

    fields = ContactUpdate.build_contact_fields(phone="+380", email="x@y.com")
    assert len(fields) == 2
    codes = {f["field_code"] for f in fields}
    assert codes == {"PHONE", "EMAIL"}


def test_contact_update_build_empty():
    """ContactUpdate.build_contact_fields returns empty list when both None."""
    from telegram_bot.services.kommo_models import ContactUpdate

    fields = ContactUpdate.build_contact_fields()
    assert fields == []

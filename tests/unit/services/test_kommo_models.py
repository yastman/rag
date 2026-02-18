"""Tests for Kommo CRM Pydantic models."""

from __future__ import annotations


class TestDealDraft:
    def test_minimal_draft(self):
        from telegram_bot.services.kommo_models import DealDraft

        draft = DealDraft()
        assert draft.client_name is None
        assert draft.source == "telegram_bot"

    def test_full_draft(self):
        from telegram_bot.services.kommo_models import DealDraft

        draft = DealDraft(
            client_name="Иван Петров",
            phone="+380501234567",
            email="ivan@example.com",
            budget=50000,
            property_type="квартира",
            location="Несебр",
            notes="Интересует 2-комнатная у моря",
        )
        assert draft.client_name == "Иван Петров"
        assert draft.budget == 50000
        assert draft.source == "telegram_bot"

    def test_draft_json_roundtrip(self):
        from telegram_bot.services.kommo_models import DealDraft

        draft = DealDraft(client_name="Test", budget=100)
        data = draft.model_dump_json()
        restored = DealDraft.model_validate_json(data)
        assert restored.client_name == "Test"
        assert restored.budget == 100


class TestContactCreate:
    def test_contact_with_phone(self):
        from telegram_bot.services.kommo_models import ContactCreate

        contact = ContactCreate(
            first_name="Иван",
            last_name="Петров",
            phone="+380501234567",
        )
        assert contact.first_name == "Иван"
        assert contact.phone == "+380501234567"

    def test_contact_to_kommo_payload(self):
        from telegram_bot.services.kommo_models import ContactCreate

        contact = ContactCreate(
            first_name="Иван",
            last_name="Петров",
            phone="+380501234567",
            email="ivan@example.com",
            telegram_user_id=123456,
        )
        payload = contact.to_kommo_payload()
        assert payload["first_name"] == "Иван"
        assert payload["last_name"] == "Петров"
        # custom_fields_values should contain phone and email
        cfv = payload.get("custom_fields_values", [])
        assert any(f["field_code"] == "PHONE" for f in cfv)
        assert any(f["field_code"] == "EMAIL" for f in cfv)


class TestLeadCreate:
    def test_lead_minimal(self):
        from telegram_bot.services.kommo_models import LeadCreate

        lead = LeadCreate(name="Сделка по квартире")
        assert lead.name == "Сделка по квартире"
        assert lead.price is None

    def test_lead_to_kommo_payload(self):
        from telegram_bot.services.kommo_models import LeadCreate

        lead = LeadCreate(
            name="Сделка",
            price=50000,
            pipeline_id=123,
            responsible_user_id=456,
            session_id="chat_789_abc",
            session_field_id=999,
        )
        payload = lead.to_kommo_payload()
        assert payload["name"] == "Сделка"
        assert payload["price"] == 50000
        assert payload["pipeline_id"] == 123
        # session_id should be in custom_fields_values
        cfv = payload.get("custom_fields_values", [])
        assert len(cfv) >= 1


class TestTaskCreate:
    def test_task_create(self):
        from telegram_bot.services.kommo_models import TaskCreate

        task = TaskCreate(
            text="Перезвонить клиенту",
            entity_id=100,
            entity_type="leads",
            complete_till=1739900000,
        )
        assert task.text == "Перезвонить клиенту"
        assert task.task_type_id == 1  # default: follow-up

    def test_task_to_kommo_payload(self):
        from telegram_bot.services.kommo_models import TaskCreate

        task = TaskCreate(
            text="Follow up",
            entity_id=100,
            entity_type="leads",
            complete_till=1739900000,
            responsible_user_id=456,
        )
        payload = task.to_kommo_payload()
        assert payload["text"] == "Follow up"
        assert payload["entity_id"] == 100
        assert payload["complete_till"] == 1739900000


class TestKommoResponse:
    def test_lead_response(self):
        from telegram_bot.services.kommo_models import LeadResponse

        resp = LeadResponse(id=12345, name="Сделка", price=50000)
        assert resp.id == 12345

    def test_contact_response(self):
        from telegram_bot.services.kommo_models import ContactResponse

        resp = ContactResponse(id=67890, name="Иван Петров")
        assert resp.id == 67890

    def test_task_response(self):
        from telegram_bot.services.kommo_models import TaskResponse

        resp = TaskResponse(id=111, text="Follow up")
        assert resp.id == 111

"""Tests for Kommo CRM Pydantic models (***REMOVED***413)."""

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


***REMOVED*** --- Phase 2: extended models (***REMOVED***443) ---


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


def test_task_result_field_accepts_list_payload():
    """Task model accepts Kommo payload where result can be an empty list."""
    from telegram_bot.services.kommo_models import Task

    task = Task(id=202, text="Open", is_completed=False, result=[])
    assert task.result == []


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



***REMOVED*** -----------------------------------------------------------------------------
***REMOVED*** KommoCustomField (***REMOVED***1655) — typed builder for custom_fields_values payloads
***REMOVED*** -----------------------------------------------------------------------------


class TestKommoCustomFieldValue:
    """Pydantic model for a single Kommo custom field value entry."""

    def test_string_value_serializes_to_value_dict(self) -> None:
        from telegram_bot.services.kommo_models import KommoCustomFieldValue

        v = KommoCustomFieldValue(value="Telegram-бот")
        assert v.model_dump(exclude_none=True) == {"value": "Telegram-бот"}

    def test_int_value_serializes_to_value_dict(self) -> None:
        from telegram_bot.services.kommo_models import KommoCustomFieldValue

        v = KommoCustomFieldValue(value=12345)
        assert v.model_dump(exclude_none=True) == {"value": 12345}

    def test_enum_code_when_present(self) -> None:
        from telegram_bot.services.kommo_models import KommoCustomFieldValue

        v = KommoCustomFieldValue(value="+380501234567", enum_code="WORK")
        assert v.model_dump(exclude_none=True) == {
            "value": "+380501234567",
            "enum_code": "WORK",
        }


class TestKommoCustomField:
    """Pydantic model for a Kommo custom_fields_values entry (field_id + values)."""

    def test_serialized_payload_matches_kommo_api_shape(self) -> None:
        from telegram_bot.services.kommo_models import (
            KommoCustomField,
            KommoCustomFieldValue,
        )

        f = KommoCustomField(
            field_id=100,
            values=[KommoCustomFieldValue(value="Осмотр объектов")],
        )
        assert f.model_dump(by_alias=True, exclude_none=True) == {
            "field_id": 100,
            "values": [{"value": "Осмотр объектов"}],
        }

    def test_field_id_zero_is_rejected_by_helper(self) -> None:
        """build_simple skips construction when field_id is falsy.

        The handler today guards with ``if service_field_id: ...`` and the
        new helper should preserve that contract — emitting a field with
        id=0 would target a non-existent CRM field.
        """
        from telegram_bot.services.kommo_models import KommoCustomField

        ***REMOVED*** field_id=0 / None must produce an explicit None so callers can filter.
        assert KommoCustomField.build_simple(field_id=0, value="x") is None
        assert KommoCustomField.build_simple(field_id=None, value="x") is None

    def test_build_simple_returns_payload_for_valid_field(self) -> None:
        from telegram_bot.services.kommo_models import KommoCustomField

        f = KommoCustomField.build_simple(field_id=200, value="Telegram-бот")
        assert f is not None
        assert f.model_dump(by_alias=True, exclude_none=True) == {
            "field_id": 200,
            "values": [{"value": "Telegram-бот"}],
        }

    def test_dump_list_filters_none_entries(self) -> None:
        from telegram_bot.services.kommo_models import KommoCustomField

        items = [
            KommoCustomField.build_simple(field_id=100, value="A"),
            None,  ***REMOVED*** represents a missing field — must be skipped
            KommoCustomField.build_simple(field_id=0, value="B"),  ***REMOVED*** also None
            KommoCustomField.build_simple(field_id=300, value="C"),
        ]
        payload = KommoCustomField.dump_list(items)
        assert payload == [
            {"field_id": 100, "values": [{"value": "A"}]},
            {"field_id": 300, "values": [{"value": "C"}]},
        ]


class TestPhoneCollectorBuildsViaPydantic:
    """phone_collector._build_custom_fields must construct entries via KommoCustomField (***REMOVED***1655).

    The function still returns ``list[dict]`` for httpx posting, but each entry
    must come from KommoCustomField.model_dump(by_alias=True, exclude_none=True)
    rather than a hand-rolled dict literal. AST scan keeps the contract enforced
    even if the helper signature changes.
    """

    def test_handler_returns_payload_byte_compatible_with_kommo_api(self) -> None:
        from telegram_bot.handlers.phone_collector import _build_custom_fields

        fields = _build_custom_fields(
            "Осмотр объектов",
            12345,
            "ivan",
            service_field_id=100,
            source_field_id=200,
            telegram_field_id=300,
            telegram_username_field_id=400,
        )

        ***REMOVED*** Existing dict shape preserved — Kommo API contract unchanged.
        assert {"field_id": 100, "values": [{"value": "Осмотр объектов"}]} in fields
        assert {"field_id": 200, "values": [{"value": "Telegram-бот"}]} in fields
        assert {"field_id": 300, "values": [{"value": "12345"}]} in fields
        assert {"field_id": 400, "values": [{"value": "@ivan"}]} in fields

    def test_handler_uses_kommo_custom_field_model(self) -> None:
        """AST contract: phone_collector._build_custom_fields uses KommoCustomField.

        Forbids regressing to hand-built ``{"field_id": ..., "values": [...]}``
        dict literals. The function may still produce dicts via
        ``KommoCustomField.dump_list(...)`` or ``model_dump(by_alias=True)``.
        """
        import ast
        import inspect
        import textwrap

        from telegram_bot.handlers import phone_collector as mod

        source = textwrap.dedent(inspect.getsource(mod._build_custom_fields))
        tree = ast.parse(source)

        uses_model = False
        bad_literals: list[int] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                func = node.func
                if (
                    isinstance(func, ast.Attribute)
                    and func.attr in {"build_simple", "dump_list", "model_dump"}
                ) or (
                    isinstance(func, ast.Name)
                    and func.id in {"KommoCustomField", "KommoCustomFieldValue"}
                ):
                    uses_model = True
            if isinstance(node, ast.Dict):
                ***REMOVED*** A literal dict whose keys include 'field_id' AND 'values'
                ***REMOVED*** is exactly the hand-built shape we want to remove.
                key_strings = {
                    k.value
                    for k in node.keys
                    if isinstance(k, ast.Constant) and isinstance(k.value, str)
                }
                if {"field_id", "values"}.issubset(key_strings):
                    bad_literals.append(node.lineno)

        assert uses_model, (
            "phone_collector._build_custom_fields must build entries via "
            "KommoCustomField (build_simple / dump_list / model_dump), "
            "not raw dict literals (***REMOVED***1655)"
        )
        assert not bad_literals, (
            "phone_collector._build_custom_fields contains hand-built "
            "{field_id, values} dict literals on lines: "
            + ", ".join(map(str, bad_literals))
        )

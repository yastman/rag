"""Tests for CRM note wizard dialog (#697) — Task 7."""

from __future__ import annotations


# --- Dialog object export ---


def test_create_note_dialog_exported():
    """crm_notes module exports create_note_dialog."""
    from telegram_bot.dialogs import crm_notes

    assert hasattr(crm_notes, "create_note_dialog")


def test_create_note_dialog_is_dialog():
    """create_note_dialog is an aiogram-dialog Dialog instance."""
    from aiogram_dialog import Dialog

    from telegram_bot.dialogs.crm_notes import create_note_dialog

    assert isinstance(create_note_dialog, Dialog)


# --- CreateNoteSG states ---


def test_create_note_sg_has_text_state():
    """CreateNoteSG has 'text' state (first step)."""
    from telegram_bot.dialogs.states import CreateNoteSG

    assert hasattr(CreateNoteSG, "text")


def test_create_note_sg_has_entity_type_state():
    """CreateNoteSG has 'entity_type' state."""
    from telegram_bot.dialogs.states import CreateNoteSG

    assert hasattr(CreateNoteSG, "entity_type")


def test_create_note_sg_has_entity_id_state():
    """CreateNoteSG has 'entity_id' state."""
    from telegram_bot.dialogs.states import CreateNoteSG

    assert hasattr(CreateNoteSG, "entity_id")


def test_create_note_sg_has_summary_state():
    """CreateNoteSG has 'summary' state."""
    from telegram_bot.dialogs.states import CreateNoteSG

    assert hasattr(CreateNoteSG, "summary")


# --- Entity type options ---


def test_note_entity_type_options_exported():
    """crm_notes exports NOTE_ENTITY_TYPES constant."""
    from telegram_bot.dialogs.crm_notes import NOTE_ENTITY_TYPES

    assert isinstance(NOTE_ENTITY_TYPES, list)
    assert len(NOTE_ENTITY_TYPES) >= 2


def test_note_entity_type_options_include_leads():
    """NOTE_ENTITY_TYPES includes leads option."""
    from telegram_bot.dialogs.crm_notes import NOTE_ENTITY_TYPES

    keys = [item[1] for item in NOTE_ENTITY_TYPES]
    assert "leads" in keys


def test_note_entity_type_options_include_contacts():
    """NOTE_ENTITY_TYPES includes contacts option."""
    from telegram_bot.dialogs.crm_notes import NOTE_ENTITY_TYPES

    keys = [item[1] for item in NOTE_ENTITY_TYPES]
    assert "contacts" in keys


def test_note_entity_type_options_are_tuples():
    """NOTE_ENTITY_TYPES items are (label, key) tuples."""
    from telegram_bot.dialogs.crm_notes import NOTE_ENTITY_TYPES

    for item in NOTE_ENTITY_TYPES:
        assert isinstance(item, tuple)
        assert len(item) == 2


# --- build_note_summary helper ---


def test_build_note_summary_leads():
    """build_note_summary formats note summary for lead attachment."""
    from telegram_bot.dialogs.crm_notes import build_note_summary

    result = build_note_summary(text="Client called", entity_type="leads", entity_id=42)

    assert "Client called" in result
    assert "42" in result


def test_build_note_summary_contacts():
    """build_note_summary formats note summary for contact attachment."""
    from telegram_bot.dialogs.crm_notes import build_note_summary

    result = build_note_summary(text="Note text", entity_type="contacts", entity_id=7)

    assert "Note text" in result
    assert "7" in result


def test_build_note_summary_no_entity():
    """build_note_summary handles no entity case."""
    from telegram_bot.dialogs.crm_notes import build_note_summary

    result = build_note_summary(text="General note", entity_type=None, entity_id=None)

    assert "General note" in result
    assert isinstance(result, str)

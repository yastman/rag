"""Tests for viewing appointment wizard dialog."""

from telegram_bot.dialogs.states import ViewingSG


def test_viewing_sg_has_all_states():
    assert hasattr(ViewingSG, "objects")
    assert hasattr(ViewingSG, "objects_text")
    assert hasattr(ViewingSG, "date")
    assert hasattr(ViewingSG, "phone")
    assert hasattr(ViewingSG, "summary")

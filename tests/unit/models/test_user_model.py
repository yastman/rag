"""Tests for user model dataclasses."""

from telegram_bot.models.user import Lead, User


def test_user_defaults():
    user = User(telegram_id=123456)
    assert user.locale == "ru"
    assert user.role == "client"
    assert user.notifications_enabled is True
    assert user.id is None


def test_user_with_all_fields():
    user = User(
        id=1,
        telegram_id=123456,
        locale="uk",
        role="manager",
        first_name="Ярослав",
        telegram_language_code="uk",
        notifications_enabled=False,
    )
    assert user.role == "manager"
    assert user.first_name == "Ярослав"


def test_lead_defaults():
    lead = Lead(user_id=1)
    assert lead.stage == "new"
    assert lead.score == 0
    assert lead.preferences == {}


def test_lead_with_preferences():
    lead = Lead(
        user_id=1,
        stage="qualified",
        score=65,
        preferences={"type": "apartment", "area": "Sunny Beach", "budget": "80000"},
    )
    assert lead.score == 65
    assert lead.preferences["type"] == "apartment"

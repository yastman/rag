"""Tests for services inline keyboard."""

from telegram_bot.keyboards.services_keyboard import (
    build_service_card_buttons,
    build_services_menu,
    parse_service_callback,
)


def test_build_services_menu():
    from aiogram.types import InlineKeyboardMarkup

    kb = build_services_menu()
    assert isinstance(kb, InlineKeyboardMarkup)
    # 5 services + 1 back = 6 rows
    assert len(kb.inline_keyboard) == 6


def test_service_buttons_have_correct_callbacks():
    kb = build_services_menu()
    callbacks = [row[0].callback_data for row in kb.inline_keyboard]
    assert "svc:passive_income" in callbacks
    assert "svc:online_deals" in callbacks
    assert "svc:vnzh" in callbacks
    assert "svc:installment" in callbacks
    assert "svc:infotour" in callbacks
    assert "svc:back" in callbacks


def test_build_service_card_buttons():
    from aiogram.types import InlineKeyboardMarkup

    kb = build_service_card_buttons(service_key="installment")
    assert isinstance(kb, InlineKeyboardMarkup)
    callbacks = [btn.callback_data for row in kb.inline_keyboard for btn in row]
    assert "cta:get_offer:installment" in callbacks
    assert "cta:manager" in callbacks
    assert "svc:menu" in callbacks


def test_parse_service_callback():
    assert parse_service_callback("svc:passive_income") == ("service", "passive_income")
    assert parse_service_callback("svc:back") == ("back", None)
    assert parse_service_callback("svc:menu") == ("menu", None)
    assert parse_service_callback("cta:get_offer:installment") == ("get_offer", "installment")
    assert parse_service_callback("cta:manager") == ("manager", None)
    assert parse_service_callback("random") is None

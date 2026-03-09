# tests/unit/keyboards/test_property_card.py
"""Tests for property card rendering."""

import pytest

from telegram_bot.keyboards.property_card import (
    build_card_buttons,
    build_results_footer,
    format_property_card,
)


def test_format_property_card():
    card = format_property_card(
        property_id="p1",
        complex_name="Sunrise Complex",
        location="Солнечный Берег",
        property_type="Студия",
        floor=2,
        area_m2=42,
        view="Бассейн",
        price_eur=48500,
    )
    assert "Sunrise Complex" in card
    assert "48 500 €" in card
    assert "Студия" in card


def test_build_card_buttons():
    from aiogram.types import InlineKeyboardMarkup

    kb = build_card_buttons(property_id="p1")
    assert isinstance(kb, InlineKeyboardMarkup)
    # Row 1: 2 buttons (viewing + favorite)
    assert len(kb.inline_keyboard[0]) == 2
    # Row 2: 1 button (ask manager)
    assert len(kb.inline_keyboard[1]) == 1
    callbacks = [btn.callback_data for row in kb.inline_keyboard for btn in row]
    assert "card:viewing:p1" in callbacks
    assert "fav:add:p1" in callbacks
    assert "card:ask:p1" in callbacks


def test_build_card_buttons_default_not_favorited():
    """3 buttons in 2+1 layout, favorite shows 'add'."""
    from aiogram.types import InlineKeyboardMarkup

    kb = build_card_buttons(property_id="p1")
    assert isinstance(kb, InlineKeyboardMarkup)
    # Row 1: 2 buttons (viewing + favorite)
    assert len(kb.inline_keyboard[0]) == 2
    # Row 2: 1 button (ask manager)
    assert len(kb.inline_keyboard[1]) == 1
    assert len(kb.inline_keyboard) == 2

    callbacks = [btn.callback_data for row in kb.inline_keyboard for btn in row]
    assert "card:viewing:p1" in callbacks
    assert "fav:add:p1" in callbacks
    assert "card:ask:p1" in callbacks


def test_build_card_buttons_favorited():
    """When is_favorited=True, shows 'remove' instead of 'add'."""
    kb = build_card_buttons(property_id="p1", is_favorited=True)
    callbacks = [btn.callback_data for row in kb.inline_keyboard for btn in row]
    assert "fav:remove:p1" in callbacks
    assert "fav:add:p1" not in callbacks


def test_build_results_footer():
    from aiogram.types import InlineKeyboardMarkup

    kb = build_results_footer(shown_total=5, total=23, has_more=True)
    assert isinstance(kb, InlineKeyboardMarkup)
    callbacks = [btn.callback_data for row in kb.inline_keyboard for btn in row]
    assert "results:more" in callbacks
    assert "results:refine" in callbacks
    assert "results:viewing" in callbacks
    assert "18 осталось" in kb.inline_keyboard[0][0].text


# --- Task 10: Redesigned card buttons layout ---


class TestCardButtonsRedesign:
    def test_button_layout_2_plus_1(self):
        """Раскладка: [В избранное][Менеджеру] + [На осмотр]."""
        kb = build_card_buttons("apt-1")
        assert len(kb.inline_keyboard) == 2
        assert len(kb.inline_keyboard[0]) == 2  # избранное + менеджер
        assert len(kb.inline_keyboard[1]) == 1  # осмотр

    def test_first_row_favorite_then_manager(self):
        kb = build_card_buttons("apt-1")
        assert "В избранное" in kb.inline_keyboard[0][0].text
        assert "Менеджеру" in kb.inline_keyboard[0][1].text

    def test_second_row_viewing(self):
        kb = build_card_buttons("apt-1")
        assert "На осмотр" in kb.inline_keyboard[1][0].text


# --- format_promotion_card ---


class TestPromotionCard:
    def test_format_with_discount(self):
        from telegram_bot.keyboards.property_card import format_promotion_card

        card = format_promotion_card(
            property_id="p2",
            complex_name="Royal Beach",
            rooms=2,
            floor=3,
            area_m2=65,
            view="Море",
            price_eur=79000,
            old_price_eur=89000,
        )
        assert "Royal Beach" in card
        assert "79 000" in card
        assert "89 000" in card
        assert "🔥" in card

    def test_discount_percentage(self):
        from telegram_bot.keyboards.property_card import format_promotion_card

        card = format_promotion_card(
            property_id="p3",
            complex_name="Sunrise",
            rooms=1,
            floor=1,
            area_m2=40,
            view="Бассейн",
            price_eur=80000,
            old_price_eur=100000,
        )
        assert "-20%" in card

    def test_zero_old_price_no_crash(self):
        """ZeroDivisionError guard: old_price_eur=0 must not crash."""
        from telegram_bot.keyboards.property_card import format_promotion_card

        card = format_promotion_card(
            property_id="p4",
            complex_name="Test",
            rooms=1,
            floor=1,
            area_m2=30,
            view="",
            price_eur=50000,
            old_price_eur=0,
        )
        assert "-0%" in card
        assert "50 000" in card

    def test_equal_prices_zero_discount(self):
        """Equal prices must show -0% discount, not crash."""
        from telegram_bot.keyboards.property_card import format_promotion_card

        card = format_promotion_card(
            property_id="p5",
            complex_name="Same",
            rooms=2,
            floor=3,
            area_m2=55,
            view="Море",
            price_eur=70000,
            old_price_eur=70000,
        )
        assert "-0%" in card


# --- Edge-case regression tests ---


def test_format_property_card_zero_price():
    card = format_property_card(
        property_id="p0",
        complex_name="Zero Price",
        location="Sofia",
        property_type="Студия",
        floor=1,
        area_m2=30,
        view="Двор",
        price_eur=0,
    )
    assert "0" in card


# --- send_property_card (Task 14 DRY) ---


@pytest.mark.asyncio
async def test_send_property_card_sends_card_text() -> None:
    """send_property_card sends formatted card text to message."""
    from unittest.mock import AsyncMock, patch

    from telegram_bot.keyboards.property_card import send_property_card

    message = AsyncMock()
    message.answer = AsyncMock(return_value=AsyncMock())
    message.answer_media_group = AsyncMock(return_value=[])

    result = {"id": "apt1", "payload": {"complex_name": "Beach Tower", "price_eur": 95000}}

    with patch("telegram_bot.keyboards.property_card.get_demo_photo_paths", return_value=[]):
        card_msg = await send_property_card(message, result)

    message.answer.assert_awaited_once()
    call_text = message.answer.await_args.args[0]
    assert "Beach Tower" in call_text
    assert card_msg is not None


@pytest.mark.asyncio
async def test_send_property_card_checks_favorites_when_service_provided() -> None:
    """send_property_card checks favorites status when service is available."""
    from unittest.mock import AsyncMock, patch

    from telegram_bot.keyboards.property_card import send_property_card

    message = AsyncMock()
    message.answer = AsyncMock(return_value=AsyncMock())

    favorites_service = AsyncMock()
    favorites_service.is_favorited = AsyncMock(return_value=True)

    result = {"id": "apt42", "payload": {"complex_name": "Fort Beach", "price_eur": 120000}}

    with patch("telegram_bot.keyboards.property_card.get_demo_photo_paths", return_value=[]):
        await send_property_card(
            message, result, favorites_service=favorites_service, telegram_id=123
        )

    favorites_service.is_favorited.assert_awaited_once_with(123, "apt42")


class TestCardButtonsRedesign:
    def test_button_layout_2_plus_1(self):
        """Раскладка: [В избранное][Менеджеру] + [На осмотр]."""
        kb = build_card_buttons("apt-1")
        assert len(kb.inline_keyboard) == 2
        assert len(kb.inline_keyboard[0]) == 2  # избранное + менеджер
        assert len(kb.inline_keyboard[1]) == 1  # осмотр

    def test_first_row_favorite_then_manager(self):
        kb = build_card_buttons("apt-1")
        assert "В избранное" in kb.inline_keyboard[0][0].text
        assert "Менеджеру" in kb.inline_keyboard[0][1].text

    def test_second_row_viewing(self):
        kb = build_card_buttons("apt-1")
        assert "На осмотр" in kb.inline_keyboard[1][0].text


def test_build_results_footer_no_more():
    from aiogram.types import InlineKeyboardMarkup

    kb = build_results_footer(shown_total=3, total=3, has_more=False)
    assert isinstance(kb, InlineKeyboardMarkup)
    callbacks = [btn.callback_data for row in kb.inline_keyboard for btn in row]
    assert "results:more" not in callbacks
    assert "results:refine" in callbacks

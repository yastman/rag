"""Tests for welcome message and client keyboard (#628)."""

pytest_plugins = ("pytest_asyncio",)

from telegram_bot.keyboards.client_keyboard import build_client_keyboard
from telegram_bot.services.content_loader import get_welcome_text


def test_welcome_text_contains_fortnoks():
    text = get_welcome_text()
    assert "FortNoks" in text


def test_welcome_text_contains_key_info():
    text = get_welcome_text()
    assert "38 900" in text
    assert "5%" in text


def test_keyboard_buttons_match_design():
    kb = build_client_keyboard()
    all_texts = [btn.text for row in kb.keyboard for btn in row]
    assert "🏠 Подбор апартаментов" in all_texts
    assert "🔑 Услуги" in all_texts
    assert "📅 Запись на осмотр" in all_texts
    assert "📌 Мои закладки" in all_texts
    assert "🎁 Акции" in all_texts
    assert "👤 Связь с менеджером" in all_texts

"""Tests for shared phone keyboard utilities."""

import pytest


pytest.importorskip("aiogram", reason="aiogram not installed")

from telegram_bot.keyboards.phone_keyboard import (
    build_phone_keyboard,
    is_phone_attempt,
    is_phone_cancel,
    normalize_phone,
    validate_phone,
)


class TestBuildPhoneKeyboard:
    def test_returns_reply_keyboard(self):
        from aiogram.types import ReplyKeyboardMarkup

        kb = build_phone_keyboard()
        assert isinstance(kb, ReplyKeyboardMarkup)

    def test_has_contact_button(self):
        kb = build_phone_keyboard()
        buttons = [btn for row in kb.keyboard for btn in row]
        contact_btns = [b for b in buttons if b.request_contact]
        assert len(contact_btns) == 1

    def test_has_cancel_button(self):
        kb = build_phone_keyboard()
        texts = [btn.text for row in kb.keyboard for btn in row]
        assert any("Отмена" in t for t in texts)

    def test_resize_and_one_time(self):
        kb = build_phone_keyboard()
        assert kb.resize_keyboard is True
        assert kb.one_time_keyboard is True


class TestIsPhoneCancel:
    @pytest.mark.parametrize("text", ["❌ Отмена", "Отмена", "отмена", "  Отмена  "])
    def test_cancel_texts(self, text):
        assert is_phone_cancel(text) is True

    @pytest.mark.parametrize("text", ["Привет", "+380501234567", "", "Отменить"])
    def test_non_cancel_texts(self, text):
        assert is_phone_cancel(text) is False


class TestIsPhoneAttempt:
    @pytest.mark.parametrize("text", ["+380501234567", "088 123 4567", "12345"])
    def test_phone_like_texts(self, text):
        assert is_phone_attempt(text) is True

    @pytest.mark.parametrize("text", ["Привет", "Какие апартаменты?", "2 комнаты", "цена 100", ""])
    def test_non_phone_texts(self, text):
        assert is_phone_attempt(text) is False


class TestValidatePhone:
    def test_valid(self):
        assert validate_phone("+380501234567") is True
        assert validate_phone("+359896759292") is True

    def test_invalid(self):
        assert validate_phone("hello") is False
        assert validate_phone("123") is False


class TestNormalizePhone:
    def test_valid_international(self):
        assert normalize_phone("+380501234567") == "+380501234567"

    def test_valid_local_bg(self):
        result = normalize_phone("0896759292")
        assert result is not None
        assert result.startswith("+359")

    def test_invalid(self):
        assert normalize_phone("hello") is None
        assert normalize_phone("") is None

    def test_strips_formatting(self):
        assert normalize_phone("+38 050 123-45-67") == "+380501234567"

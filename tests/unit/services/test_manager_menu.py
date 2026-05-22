"""Tests for manager menu rendering (#388)."""

from telegram_bot.services.manager_menu import render_start_menu


def test_render_start_menu_manager():
    text = render_start_menu(role="manager", domain="real estate")
    assert "Manager menu" in text
    assert "/leads" in text


def test_render_start_menu_client():
    text = render_start_menu(role="client", domain="real estate")
    assert "Ask questions" in text
    assert "Manager menu" not in text

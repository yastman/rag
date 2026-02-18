"""Tests for Kommo lead scoring config fields (#384)."""

from telegram_bot.config import BotConfig


def test_config_reads_kommo_scoring_field_ids(monkeypatch):
    monkeypatch.setenv("KOMMO_LEAD_SCORE_FIELD_ID", "701")
    monkeypatch.setenv("KOMMO_LEAD_BAND_FIELD_ID", "702")

    cfg = BotConfig()

    assert cfg.kommo_lead_score_field_id == 701
    assert cfg.kommo_lead_band_field_id == 702


def test_config_kommo_scoring_fields_default_to_zero():
    cfg = BotConfig()

    assert cfg.kommo_lead_score_field_id == 0
    assert cfg.kommo_lead_band_field_id == 0

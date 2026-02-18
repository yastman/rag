"""Tests for lead scoring models and Kommo payload contract (#384)."""

import pytest


def test_lead_score_record_validates_score_range():
    from telegram_bot.services.lead_scoring_models import LeadScoreRecord

    rec = LeadScoreRecord(
        lead_id=11,
        user_id=99,
        session_id="chat-1",
        score_value=74,
        score_band="hot",
        reason_codes=["timeline_asap", "budget_defined"],
        kommo_lead_id=5001,
    )
    assert rec.score_value == 74
    assert rec.score_band == "hot"


def test_lead_score_record_rejects_invalid_score():
    from telegram_bot.services.lead_scoring_models import LeadScoreRecord

    with pytest.raises(ValueError):
        LeadScoreRecord(
            lead_id=11,
            user_id=99,
            session_id="chat-1",
            score_value=101,
            score_band="hot",
        )


def test_lead_score_payload_uses_field_id_not_field_name():
    from telegram_bot.services.kommo_models import LeadScoreSyncPayload
    from telegram_bot.services.lead_scoring_models import LeadScoreRecord

    rec = LeadScoreRecord(
        lead_id=11,
        user_id=99,
        session_id="chat-1",
        score_value=74,
        score_band="hot",
        reason_codes=["timeline_asap", "budget_defined"],
        kommo_lead_id=5001,
    )

    payload = LeadScoreSyncPayload.from_record(
        rec,
        score_field_id=701,
        band_field_id=702,
    ).to_kommo_payload()

    assert payload["custom_fields_values"][0]["field_id"] == 701
    assert "field_name" not in payload["custom_fields_values"][0]
    assert payload["custom_fields_values"][1]["field_id"] == 702
    assert payload["custom_fields_values"][1]["values"][0]["value"] == "hot"


def test_lead_score_payload_score_value_in_values():
    from telegram_bot.services.kommo_models import LeadScoreSyncPayload
    from telegram_bot.services.lead_scoring_models import LeadScoreRecord

    rec = LeadScoreRecord(
        lead_id=11,
        user_id=99,
        session_id="chat-1",
        score_value=50,
        score_band="warm",
        kommo_lead_id=5001,
    )

    payload = LeadScoreSyncPayload.from_record(
        rec, score_field_id=701, band_field_id=702
    ).to_kommo_payload()

    assert payload["custom_fields_values"][0]["values"][0]["value"] == 50

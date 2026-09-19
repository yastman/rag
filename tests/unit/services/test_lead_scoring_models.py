"""Tests for the canonical Kommo score-payload conversion contract (#384)."""

from types import SimpleNamespace

from src.services.kommo_models import LeadScoreSyncPayload


def test_lead_score_payload_uses_field_id_not_field_name():
    rec = SimpleNamespace(
        score_value=74,
        score_band="hot",
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
    rec = SimpleNamespace(
        score_value=50,
        score_band="warm",
        kommo_lead_id=5001,
    )

    payload = LeadScoreSyncPayload.from_record(
        rec, score_field_id=701, band_field_id=702
    ).to_kommo_payload()

    assert payload["custom_fields_values"][0]["values"][0]["value"] == 50

"""Tests for lead scoring + kommo sync SQL schema owned by bootstrap."""

from telegram_bot.lifecycle.postgres_bootstrap import REALESTATE_SCHEMA_STATEMENTS


def _ddl() -> str:
    return "\n".join(REALESTATE_SCHEMA_STATEMENTS)


def test_lead_scoring_schema_contains_required_tables_and_indexes():
    ddl = _ddl()
    assert "CREATE TABLE IF NOT EXISTS lead_scores" in ddl
    assert "REFERENCES leads(id)" in ddl
    assert "UNIQUE (lead_id)" in ddl
    assert "sync_status" in ddl
    assert "sync_attempts" in ddl
    assert "reason_codes" in ddl
    # Dead audit table must stay out of bootstrap ownership.
    assert "lead_score_sync_audit" not in ddl
    assert "idx_lead_scores_pending_sync" not in ddl


def test_lead_scoring_schema_ml_upgrade_comments():
    ddl = _ddl()
    # Live writers still persist reason_codes as jsonb; ML comments lived only
    # on the deleted docker init SQL and are not required in bootstrap DDL.
    assert "reason_codes JSONB" in ddl

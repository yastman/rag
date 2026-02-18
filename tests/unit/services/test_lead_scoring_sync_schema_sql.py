"""Tests for lead scoring + kommo sync SQL schema."""

from pathlib import Path


def test_lead_scoring_schema_contains_required_tables_and_indexes():
    ddl = Path("docker/postgres/init/06-lead-scoring-sync.sql").read_text(encoding="utf-8")
    assert "CREATE TABLE IF NOT EXISTS lead_scores" in ddl
    assert "CREATE TABLE IF NOT EXISTS lead_score_sync_audit" in ddl
    assert "REFERENCES leads(id)" in ddl
    assert "idx_lead_scores_pending_sync" in ddl


def test_lead_scoring_schema_ml_upgrade_comments():
    ddl = Path("docker/postgres/init/06-lead-scoring-sync.sql").read_text(encoding="utf-8")
    assert "reason_codes" in ddl
    assert "SHAP" in ddl
    assert "ML" in ddl

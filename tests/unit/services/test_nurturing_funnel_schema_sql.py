"""Tests for nurturing jobs + funnel analytics SQL schema (#390)."""

from pathlib import Path


def test_nurturing_schema_has_jobs_metrics_and_leases():
    ddl = Path("docker/postgres/init/07-nurturing-funnel-analytics.sql").read_text(encoding="utf-8")
    assert "CREATE TABLE IF NOT EXISTS nurturing_jobs" in ddl
    assert "CREATE TABLE IF NOT EXISTS funnel_metrics_daily" in ddl
    assert "CREATE TABLE IF NOT EXISTS scheduler_leases" in ddl
    assert "REFERENCES lead_scores(id)" in ddl


def test_nurturing_schema_has_required_indexes():
    ddl = Path("docker/postgres/init/07-nurturing-funnel-analytics.sql").read_text(encoding="utf-8")
    assert "idx_nurturing_jobs_pending" in ddl
    assert "idx_funnel_events_date_stage" in ddl


def test_nurturing_schema_has_step_conversion_columns():
    ddl = Path("docker/postgres/init/07-nurturing-funnel-analytics.sql").read_text(encoding="utf-8")
    assert "prev_stage_count" in ddl
    assert "step_conversion_rate" in ddl


def test_lead_scores_band_sync_index():
    ddl = Path("docker/postgres/init/06-lead-scoring-sync.sql").read_text(encoding="utf-8")
    assert "idx_lead_scores_band_sync" in ddl

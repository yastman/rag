"""Tests for nurturing jobs + funnel analytics SQL schema owned by bootstrap."""

from telegram_bot.lifecycle.postgres_bootstrap import REALESTATE_SCHEMA_STATEMENTS


def _ddl() -> str:
    return "\n".join(REALESTATE_SCHEMA_STATEMENTS)


def test_nurturing_schema_has_jobs_metrics_and_no_dead_tables():
    ddl = _ddl()
    assert "CREATE TABLE IF NOT EXISTS nurturing_jobs" in ddl
    assert "CREATE TABLE IF NOT EXISTS funnel_metrics_daily" in ddl
    assert "REFERENCES lead_scores(id)" in ddl
    assert "UNIQUE (lead_score_id, scheduled_for)" in ddl
    assert "UNIQUE (metric_date, stage_name)" in ddl
    # Truly dead scheduler state must remain absent.
    assert "scheduler_leases" not in ddl
    assert "lead_score_sync_audit" not in ddl


def test_nurturing_schema_has_required_indexes():
    ddl = _ddl()
    assert "idx_nurturing_jobs_pending" in ddl
    assert "idx_funnel_events_created_stage" in ddl
    assert "idx_lead_scores_band_sync" not in ddl
    assert "idx_lead_scores_pending_sync" not in ddl


def test_nurturing_schema_omits_dead_step_conversion_columns():
    ddl = _ddl()
    assert "prev_stage_count" not in ddl
    assert "step_conversion_rate" not in ddl
    assert "entered_count" in ddl
    assert "converted_count" in ddl
    assert "dropoff_count" in ddl
    assert "conversion_rate" in ddl


def test_funnel_events_stage_name_column_added():
    ddl = _ddl()
    assert "ADD COLUMN IF NOT EXISTS stage_name" in ddl


def test_nurturing_jobs_exposes_user_id_for_dispatch():
    """dispatch_pending SELECTs user_id as a column, not only payload JSON."""
    ddl = _ddl()
    jobs = ddl.split("CREATE TABLE IF NOT EXISTS nurturing_jobs", 1)[1]
    jobs = jobs.split("CREATE TABLE IF NOT EXISTS", 1)[0]
    assert "user_id" in jobs

"""Contract: truly orphaned scheduler/voice state stays absent from kept code.

Pins ARCH-11 (#2608) for dead surfaces only. Live CRM/handoff/funnel tables
(lead_scores, nurturing_jobs, funnel_metrics_daily) are owned by bootstrap
again and must remain available to production readers/writers.

Orphaned Postgres tables (no kept writers/readers):
  - lead_score_sync_audit
  - scheduler_leases

Orphaned Redis keyspaces (reader archived in ARCH-06):
  - session:last_active:* (written by bot.py; reader was session_summary_worker)

Orphaned module:
  - telegram_bot/services/funnel_lead_scoring.py (broken imports, no callers)
"""

from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
BOOTSTRAP = REPO_ROOT / "telegram_bot" / "lifecycle" / "postgres_bootstrap.py"
DROP_SQL = (
    REPO_ROOT / "docker" / "postgres" / "init" / "09-drop-orphaned-scheduler-voice-tables.sql"
)
BOT_PY = REPO_ROOT / "telegram_bot" / "bot.py"
FUNNEL_LEAD_SCORING = REPO_ROOT / "telegram_bot" / "services" / "funnel_lead_scoring.py"

# Tables that must NOT appear in the bootstrap DDL (truly dead).
ORPHANED_TABLES = (
    "lead_score_sync_audit",
    "scheduler_leases",
)

# Live tables owned by bootstrap for CRM/nurturing/funnel features.
LIVE_BOOTSTRAP_TABLES = (
    "lead_scores",
    "nurturing_jobs",
    "funnel_metrics_daily",
)


def test_orphaned_tables_absent_from_bootstrap() -> None:
    """Bootstrap must not CREATE truly orphaned scheduler/voice tables."""
    ddl = BOOTSTRAP.read_text(encoding="utf-8").lower()
    present = [t for t in ORPHANED_TABLES if f"create table if not exists {t}" in ddl]
    assert not present, (
        f"Orphaned tables still bootstrapped after ARCH-06/ARCH-12: {present}. "
        "Remove their CREATE TABLE statements from REALESTATE_SCHEMA_STATEMENTS."
    )


def test_live_crm_funnel_tables_present_in_bootstrap() -> None:
    """Bootstrap owns minimal live lead_scores / nurturing / funnel tables."""
    ddl = BOOTSTRAP.read_text(encoding="utf-8").lower()
    missing = [t for t in LIVE_BOOTSTRAP_TABLES if f"create table if not exists {t}" not in ddl]
    assert not missing, (
        f"Live CRM/funnel tables missing from bootstrap: {missing}. "
        "Add CREATE TABLE IF NOT EXISTS statements to REALESTATE_SCHEMA_STATEMENTS."
    )


def test_drop_sql_retains_live_crm_funnel_tables() -> None:
    """Docker init must not DROP live CRM/nurturing/funnel tables."""
    sql = DROP_SQL.read_text(encoding="utf-8").lower()
    destroyed = [t for t in LIVE_BOOTSTRAP_TABLES if f"drop table if exists {t}" in sql]
    assert not destroyed, (
        f"Live CRM/funnel tables still dropped by docker init: {destroyed}. "
        "Remove those DROP TABLE statements from "
        "09-drop-orphaned-scheduler-voice-tables.sql."
    )


def test_drop_sql_still_drops_orphaned_tables() -> None:
    """Docker init must keep DROP for truly orphaned scheduler/voice state."""
    sql = DROP_SQL.read_text(encoding="utf-8").lower()
    missing = [t for t in ORPHANED_TABLES if f"drop table if exists {t}" not in sql]
    assert not missing, (
        f"Orphaned tables missing from docker init drops: {missing}. "
        "Keep DROP TABLE IF EXISTS for lead_score_sync_audit and scheduler_leases."
    )
    assert "drop table if exists call_transcripts" in sql, (
        "call_transcripts DROP missing from docker init (voice ARCH-02)."
    )


def test_session_last_active_write_absent_from_bot() -> None:
    """bot.py must not write session:last_active keys (reader archived in ARCH-06)."""
    text = BOT_PY.read_text(encoding="utf-8")
    assert "session:last_active:" not in text, (
        "bot.py still writes session:last_active Redis keys whose only reader "
        "(session_summary_worker) was archived in ARCH-06. Remove the write."
    )


def test_funnel_lead_scoring_module_deleted() -> None:
    """funnel_lead_scoring.py must be deleted (broken imports, no callers)."""
    assert not FUNNEL_LEAD_SCORING.exists(), (
        "telegram_bot/services/funnel_lead_scoring.py still exists but imports "
        "from non-existent lead_scoring modules archived in ARCH-06. Delete it."
    )

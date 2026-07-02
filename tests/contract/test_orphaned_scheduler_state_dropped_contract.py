"""Contract: orphaned scheduler/CRM/voice state is absent from kept code.

Pins ARCH-11 (#2608): after scheduler/voice/CRM archival, the following
tables and Redis keyspaces must not be bootstrapped or written by kept code.

Orphaned Postgres tables (writers archived in ARCH-06 / ARCH-12):
  - lead_scores
  - lead_score_sync_audit
  - nurturing_jobs
  - funnel_metrics_daily
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
BOT_PY = REPO_ROOT / "telegram_bot" / "bot.py"
FUNNEL_LEAD_SCORING = REPO_ROOT / "telegram_bot" / "services" / "funnel_lead_scoring.py"

# Tables that must NOT appear in the bootstrap DDL post-archival.
ORPHANED_TABLES = (
    "lead_scores",
    "lead_score_sync_audit",
    "nurturing_jobs",
    "funnel_metrics_daily",
    "scheduler_leases",
)


def test_orphaned_tables_absent_from_bootstrap() -> None:
    """Bootstrap must not CREATE the orphaned scheduler/CRM tables."""
    ddl = BOOTSTRAP.read_text(encoding="utf-8").lower()
    present = [t for t in ORPHANED_TABLES if f"create table if not exists {t}" in ddl]
    assert not present, (
        f"Orphaned tables still bootstrapped after ARCH-06/ARCH-12: {present}. "
        "Remove their CREATE TABLE statements from REALESTATE_SCHEMA_STATEMENTS."
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

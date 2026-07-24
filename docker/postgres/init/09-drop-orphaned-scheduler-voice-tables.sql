-- ARCH-11 (#2608): drop orphaned DB/state after scheduler/voice archival
--
-- Writers archived in:
--   ARCH-06 (#2602): session_summary_worker (session:last_active reader)
--   ARCH-02 (#2598): voice/RAG API surfaces
--
-- Live CRM/nurturing/funnel tables are owned by lifecycle bootstrap again and
-- MUST NOT be dropped here:
--   lead_scores, nurturing_jobs, funnel_metrics_daily
--
-- ⚠️  DESTRUCTIVE — irreversible for truly orphaned tables only.
-- Run only after:
--   1. Confirming no kept-code writer (grep evidence in PR description).
--   2. Taking a Postgres backup/snapshot.
--   3. Human approval.
--
-- Tables dropped (dependency order — child tables first):
--   lead_score_sync_audit → orphaned audit trail (no kept readers/writers)
--   scheduler_leases      → standalone orphaned scheduler lock table
--   call_transcripts      → standalone (voice, ARCH-02)

\c realestate;

-- Truly orphaned scheduler/CRM audit state only
DROP TABLE IF EXISTS lead_score_sync_audit;
DROP TABLE IF EXISTS scheduler_leases;

-- Voice transcript table (ARCH-02) — lives in postgres DB (04-voice-schema.sql has no \c switch)
\c postgres;
DROP TABLE IF EXISTS call_transcripts;
\c realestate;

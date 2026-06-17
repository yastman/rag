-- ARCH-11 (#2608): drop orphaned DB/state after scheduler/voice archival
--
-- Writers archived in:
--   ARCH-06 (#2602): nurturing_scheduler, session_summary_worker, lead_score_sync
--   ARCH-02 (#2598): voice/RAG API surfaces
--   ARCH-12 (#2625): CRM/Kommo surface
--
-- ⚠️  DESTRUCTIVE — irreversible.
-- Run only after:
--   1. Confirming no kept-code writer (grep evidence in PR description).
--   2. Taking a Postgres backup/snapshot.
--   3. Human approval.
--
-- Tables dropped (dependency order — child tables first):
--   nurturing_jobs        → lead_score_id FK → lead_scores
--   lead_score_sync_audit → lead_score_id FK → lead_scores
--   lead_scores           → lead_id FK → leads
--   funnel_metrics_daily  → standalone
--   scheduler_leases      → standalone
--   call_transcripts      → standalone (voice, ARCH-02)

\c realestate;

-- Child tables first (FK constraints)
DROP TABLE IF EXISTS nurturing_jobs;
DROP TABLE IF EXISTS lead_score_sync_audit;
DROP TABLE IF EXISTS lead_scores;
DROP TABLE IF EXISTS funnel_metrics_daily;
DROP TABLE IF EXISTS scheduler_leases;

-- Voice transcript table (ARCH-02) — lives in postgres DB (04-voice-schema.sql has no \c switch)
\c postgres;
DROP TABLE IF EXISTS call_transcripts;
\c realestate;

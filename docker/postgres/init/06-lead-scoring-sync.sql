-- Lead Scoring + Kommo CRM Sync State (#384)
-- Depends on: 05-realestate-schema.sql (leads table)

\c realestate;

CREATE TABLE IF NOT EXISTS lead_scores (
    id BIGSERIAL PRIMARY KEY,
    lead_id BIGINT NOT NULL REFERENCES leads(id) ON DELETE CASCADE,
    user_id BIGINT NOT NULL,
    session_id TEXT NOT NULL,
    -- score_value: rule-based 0-100 now; ML model probability * 100 in v2
    score_value INTEGER NOT NULL CHECK (score_value BETWEEN 0 AND 100),
    score_band TEXT NOT NULL CHECK (score_band IN ('hot', 'warm', 'cold')),
    -- reason_codes: rule-based codes now; SHAP feature importances in ML v2
    reason_codes JSONB NOT NULL DEFAULT '[]'::jsonb,
    kommo_lead_id BIGINT,
    sync_status TEXT NOT NULL DEFAULT 'pending' CHECK (sync_status IN ('pending', 'synced', 'failed')),
    sync_attempts INTEGER NOT NULL DEFAULT 0,
    last_synced_at TIMESTAMPTZ,
    sync_error TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (lead_id)
);

CREATE TABLE IF NOT EXISTS lead_score_sync_audit (
    id BIGSERIAL PRIMARY KEY,
    lead_score_id BIGINT NOT NULL REFERENCES lead_scores(id) ON DELETE CASCADE,
    idempotency_key TEXT NOT NULL,
    sync_status TEXT NOT NULL,
    http_status INTEGER,
    response_excerpt TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_lead_scores_pending_sync
    ON lead_scores (sync_status, updated_at DESC);

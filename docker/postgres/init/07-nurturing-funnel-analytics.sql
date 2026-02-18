-- Nurturing Jobs + Funnel Analytics (#390)
-- Depends on: 05-realestate-schema.sql (funnel_events), 06-lead-scoring-sync.sql (lead_scores)

\c realestate;

CREATE TABLE IF NOT EXISTS nurturing_jobs (
    id BIGSERIAL PRIMARY KEY,
    lead_score_id BIGINT NOT NULL REFERENCES lead_scores(id) ON DELETE CASCADE,
    scheduled_for TIMESTAMPTZ NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'running', 'sent', 'failed', 'skipped')),
    channel TEXT NOT NULL DEFAULT 'telegram',
    payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    attempt_count INTEGER NOT NULL DEFAULT 0,
    last_error TEXT,
    sent_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (lead_score_id, scheduled_for)
);

CREATE TABLE IF NOT EXISTS funnel_metrics_daily (
    id BIGSERIAL PRIMARY KEY,
    metric_date DATE NOT NULL,
    stage_name TEXT NOT NULL,
    entered_count INTEGER NOT NULL DEFAULT 0,
    converted_count INTEGER NOT NULL DEFAULT 0,
    dropoff_count INTEGER NOT NULL DEFAULT 0,
    conversion_rate NUMERIC(6,4) NOT NULL DEFAULT 0,
    prev_stage_count INTEGER NOT NULL DEFAULT 0,
    step_conversion_rate NUMERIC(6,4) NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (metric_date, stage_name)
);

CREATE TABLE IF NOT EXISTS scheduler_leases (
    lease_name TEXT PRIMARY KEY,
    owner_id TEXT NOT NULL,
    lease_until TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_nurturing_jobs_pending
    ON nurturing_jobs (status, scheduled_for ASC);

CREATE INDEX IF NOT EXISTS idx_funnel_events_date_stage
    ON funnel_events (DATE(created_at), stage_name);

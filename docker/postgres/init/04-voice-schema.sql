-- Voice bot: call transcripts storage
CREATE TABLE IF NOT EXISTS call_transcripts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    phone VARCHAR(20) NOT NULL,
    lead_data JSONB DEFAULT '{}',
    transcript JSONB DEFAULT '[]',
    langfuse_trace_id VARCHAR(64),
    status VARCHAR(20) NOT NULL DEFAULT 'initiated',
    duration_sec INTEGER DEFAULT 0,
    validation_result JSONB,
    callback_chat_id BIGINT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_call_transcripts_phone ON call_transcripts(phone);
CREATE INDEX IF NOT EXISTS idx_call_transcripts_status ON call_transcripts(status);
CREATE INDEX IF NOT EXISTS idx_call_transcripts_created ON call_transcripts(created_at DESC);

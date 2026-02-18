-- Real Estate: users, leads, funnel events
-- Runs in default postgres DB (tables created there, not in realestate DB)
-- because init scripts run against default DB

\c realestate;

CREATE TABLE IF NOT EXISTS users (
    id SERIAL PRIMARY KEY,
    telegram_id BIGINT UNIQUE NOT NULL,
    locale VARCHAR(5) DEFAULT 'ru',
    role VARCHAR(20) DEFAULT 'client',
    first_name VARCHAR(100),
    telegram_language_code VARCHAR(10),
    notifications_enabled BOOLEAN DEFAULT true,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS leads (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id),
    stage VARCHAR(30) DEFAULT 'new',
    score INTEGER DEFAULT 0,
    preferences JSONB DEFAULT '{}',
    kommo_lead_id BIGINT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS funnel_events (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id),
    event_type VARCHAR(50) NOT NULL,
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_users_telegram_id ON users(telegram_id);
CREATE INDEX IF NOT EXISTS idx_leads_user_id ON leads(user_id);
CREATE INDEX IF NOT EXISTS idx_leads_stage ON leads(stage);
CREATE INDEX IF NOT EXISTS idx_funnel_events_user_id ON funnel_events(user_id);
CREATE INDEX IF NOT EXISTS idx_funnel_events_created ON funnel_events(created_at DESC);

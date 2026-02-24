\c realestate;

CREATE TABLE IF NOT EXISTS user_favorites (
    id BIGSERIAL PRIMARY KEY,
    telegram_id BIGINT NOT NULL,
    property_id TEXT NOT NULL,
    property_data JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (telegram_id, property_id)
);

CREATE INDEX idx_user_favorites_telegram_id ON user_favorites (telegram_id);
CREATE INDEX idx_user_favorites_created_at ON user_favorites (created_at DESC);

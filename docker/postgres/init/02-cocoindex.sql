-- CocoIndex state tables for document ingestion pipeline
-- Database created by 00-init-databases.sh

\c cocoindex;

-- Ingestion state tracking
CREATE TABLE ingestion_state (
    id SERIAL PRIMARY KEY,
    file_id VARCHAR(255) UNIQUE NOT NULL,
    drive_id VARCHAR(255),
    folder_id VARCHAR(255),
    file_name VARCHAR(500),
    mime_type VARCHAR(100),
    modified_time TIMESTAMPTZ,
    content_hash VARCHAR(64),           -- SHA256 of file content
    parser_version VARCHAR(20),          -- e.g., "docling-2.1"
    chunker_version VARCHAR(20),         -- e.g., "hybrid-1.0"
    embedding_model VARCHAR(50),         -- e.g., "voyage-3-large"
    chunk_count INTEGER,
    indexed_at TIMESTAMPTZ DEFAULT NOW(),
    status VARCHAR(20) DEFAULT 'pending', -- pending, processing, indexed, error
    error_message TEXT,
    retry_count INTEGER DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_ingestion_file_id ON ingestion_state(file_id);
CREATE INDEX idx_ingestion_folder_id ON ingestion_state(folder_id);
CREATE INDEX idx_ingestion_status ON ingestion_state(status);
CREATE INDEX idx_ingestion_modified_time ON ingestion_state(modified_time);

-- Dead letter queue for failed items
CREATE TABLE ingestion_dead_letter (
    id SERIAL PRIMARY KEY,
    file_id VARCHAR(255) NOT NULL,
    error_type VARCHAR(100),
    error_message TEXT,
    payload JSONB,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_dead_letter_file_id ON ingestion_dead_letter(file_id);
CREATE INDEX idx_dead_letter_created_at ON ingestion_dead_letter(created_at);

-- Grant permissions to dedicated user (created by 00-init-databases.sh)
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO cocoindex_user;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO cocoindex_user;
-- Backward compat: superuser retains access
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO postgres;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO postgres;

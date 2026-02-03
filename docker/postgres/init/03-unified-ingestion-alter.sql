-- docker/postgres/init/03-unified-ingestion-alter.sql
-- Unified ingestion pipeline schema extensions (idempotent)
-- Extends 02-cocoindex.sql tables

\c cocoindex;

-- Add missing columns to ingestion_state (idempotent)
DO $$
BEGIN
    -- Source info
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                   WHERE table_name = 'ingestion_state' AND column_name = 'source_path') THEN
        ALTER TABLE ingestion_state ADD COLUMN source_path VARCHAR(1000);
    END IF;

    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                   WHERE table_name = 'ingestion_state' AND column_name = 'file_size') THEN
        ALTER TABLE ingestion_state ADD COLUMN file_size BIGINT;
    END IF;

    -- NOTE: ingestion_state already has `modified_time` (TIMESTAMPTZ) from 02-cocoindex.sql.
    -- Use that column for filesystem mtime too (no need to introduce a second timestamp field).

    -- Pipeline versioning
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                   WHERE table_name = 'ingestion_state' AND column_name = 'pipeline_version') THEN
        ALTER TABLE ingestion_state ADD COLUMN pipeline_version VARCHAR(20) DEFAULT 'v3.2.1';
    END IF;

    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                   WHERE table_name = 'ingestion_state' AND column_name = 'chunk_location_version') THEN
        ALTER TABLE ingestion_state ADD COLUMN chunk_location_version VARCHAR(20) DEFAULT 'docling';
    END IF;

    -- Collection tracking
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                   WHERE table_name = 'ingestion_state' AND column_name = 'collection_name') THEN
        ALTER TABLE ingestion_state ADD COLUMN collection_name VARCHAR(100);
    END IF;
END $$;

-- Add indexes for new columns
CREATE INDEX IF NOT EXISTS idx_ingestion_source_path ON ingestion_state(source_path);
CREATE INDEX IF NOT EXISTS idx_ingestion_collection ON ingestion_state(collection_name);
CREATE INDEX IF NOT EXISTS idx_ingestion_pipeline_version ON ingestion_state(pipeline_version);

-- Add retry_after for exponential backoff
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                   WHERE table_name = 'ingestion_state' AND column_name = 'retry_after') THEN
        ALTER TABLE ingestion_state ADD COLUMN retry_after TIMESTAMPTZ;
    END IF;
END $$;

COMMENT ON TABLE ingestion_state IS 'Unified ingestion state tracking (v3.2.1)';

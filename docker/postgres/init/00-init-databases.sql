-- Dev Stack: Auto-create databases for services
-- This script runs automatically on first PostgreSQL start

-- Database for Langfuse (LLM tracing)
CREATE DATABASE langfuse;

-- Grant permissions (using default postgres user)
GRANT ALL PRIVILEGES ON DATABASE langfuse TO postgres;

-- Database for LiteLLM (LLM Gateway)
CREATE DATABASE litellm;
GRANT ALL PRIVILEGES ON DATABASE litellm TO postgres;

-- Database for Real Estate CRM/Funnel
CREATE DATABASE realestate;
GRANT ALL PRIVILEGES ON DATABASE realestate TO postgres;

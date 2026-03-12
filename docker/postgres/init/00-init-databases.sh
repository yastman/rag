#!/bin/bash
set -euo pipefail

# Per-service PostgreSQL users with least-privilege access.
# Passwords default to POSTGRES_PASSWORD for backward compatibility.
# In production, set dedicated *_DB_PASSWORD env vars.

LANGFUSE_DB_PASSWORD="${LANGFUSE_DB_PASSWORD:-$POSTGRES_PASSWORD}"
LITELLM_DB_PASSWORD="${LITELLM_DB_PASSWORD:-$POSTGRES_PASSWORD}"
MLFLOW_DB_PASSWORD="${MLFLOW_DB_PASSWORD:-$POSTGRES_PASSWORD}"
COCOINDEX_DB_PASSWORD="${COCOINDEX_DB_PASSWORD:-$POSTGRES_PASSWORD}"
REALESTATE_DB_PASSWORD="${REALESTATE_DB_PASSWORD:-$POSTGRES_PASSWORD}"
VOICE_DB_PASSWORD="${VOICE_DB_PASSWORD:-$POSTGRES_PASSWORD}"

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<-EOSQL
    -- Create databases
    CREATE DATABASE langfuse;
    CREATE DATABASE mlflow;
    CREATE DATABASE litellm;
    CREATE DATABASE realestate;
    CREATE DATABASE cocoindex;

    -- Create per-service users
    CREATE USER langfuse_user WITH PASSWORD '${LANGFUSE_DB_PASSWORD}';
    CREATE USER litellm_user WITH PASSWORD '${LITELLM_DB_PASSWORD}';
    CREATE USER mlflow_user WITH PASSWORD '${MLFLOW_DB_PASSWORD}';
    CREATE USER cocoindex_user WITH PASSWORD '${COCOINDEX_DB_PASSWORD}';
    CREATE USER realestate_user WITH PASSWORD '${REALESTATE_DB_PASSWORD}';
    CREATE USER voice_user WITH PASSWORD '${VOICE_DB_PASSWORD}';

    -- Grant connect + full schema privileges per database
    GRANT ALL PRIVILEGES ON DATABASE langfuse TO langfuse_user;
    GRANT ALL PRIVILEGES ON DATABASE litellm TO litellm_user;
    GRANT ALL PRIVILEGES ON DATABASE mlflow TO mlflow_user;
    GRANT ALL PRIVILEGES ON DATABASE cocoindex TO cocoindex_user;
    GRANT ALL PRIVILEGES ON DATABASE realestate TO realestate_user;

    -- voice_user uses default postgres DB (call_transcripts table)
    GRANT CREATE ON SCHEMA public TO voice_user;
EOSQL

# Grant schema-level privileges for each service database
for db_user in "langfuse:langfuse_user" "litellm:litellm_user" "mlflow:mlflow_user" "cocoindex:cocoindex_user" "realestate:realestate_user"; do
    db="${db_user%%:*}"
    user="${db_user##*:}"
    psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$db" <<-EOSQL
        GRANT ALL ON SCHEMA public TO ${user};
        ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO ${user};
        ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON SEQUENCES TO ${user};
EOSQL
done

echo "Per-service database users created successfully."

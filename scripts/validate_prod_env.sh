#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd -- "${SCRIPT_DIR}/.." && pwd)"
cd "${REPO_ROOT}"

if [ ! -f .env ]; then
  echo ".env is required for production env validation" >&2
  exit 1
fi

# Safe .env parsing — reject lines that look like shell commands
while IFS= read -r line || [[ -n "$line" ]]; do
  # skip empty lines and comments
  [[ -z "$line" || "$line" =~ ^[[:space:]]*# ]] && continue
  # Must be KEY=VALUE format
  if [[ ! "$line" =~ ^[A-Za-z_][A-Za-z0-9_]*= ]]; then
    echo "Invalid .env line (not KEY=VALUE): $line" >&2
    exit 1
  fi
  key="${line%%=*}"
  value="${line#*=}"
  # Strip surrounding quotes if present
  if [[ "$value" == \"*\" ]]; then
    value="${value:1:-1}"
  elif [[ "$value" == \'*\' ]]; then
    value="${value:1:-1}"
  fi
  export "$key=$value"
done < .env

handoff_enabled="${HANDOFF_ENABLED:-false}"
managers_group_id="${MANAGERS_GROUP_ID:-}"

if [ "${handoff_enabled}" = "true" ] && [ -z "${managers_group_id}" ]; then
  echo "HANDOFF_ENABLED=true but MANAGERS_GROUP_ID is missing in production env" >&2
  exit 1
fi

required_prod_vars=(
  POSTGRES_PASSWORD
  REDIS_PASSWORD
  LITELLM_MASTER_KEY
  TELEGRAM_BOT_TOKEN
  GDRIVE_SYNC_DIR
  NEXTAUTH_SECRET
  SALT
  ENCRYPTION_KEY
  CLICKHOUSE_PASSWORD
  MINIO_ROOT_PASSWORD
  LANGFUSE_REDIS_PASSWORD
)

for var_name in "${required_prod_vars[@]}"; do
  if [ -z "${!var_name:-}" ]; then
    echo "${var_name} is required in production env" >&2
    exit 1
  fi
done

# Minimum password complexity check (≥12 chars) for sensitive credentials
password_vars=(
  POSTGRES_PASSWORD
  REDIS_PASSWORD
  LITELLM_MASTER_KEY
  CLICKHOUSE_PASSWORD
  MINIO_ROOT_PASSWORD
  NEXTAUTH_SECRET
  SALT
  ENCRYPTION_KEY
  LANGFUSE_REDIS_PASSWORD
)

for pw_var in "${password_vars[@]}"; do
  pw_value="${!pw_var:-}"
  if [ "${#pw_value}" -lt 12 ]; then
    echo "${pw_var} must be at least 12 characters long (got ${#pw_value})" >&2
    exit 1
  fi
done

docker compose --env-file .env -f compose.yml -f compose.vps.yml config >/dev/null

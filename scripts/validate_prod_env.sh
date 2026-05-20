#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd -- "${SCRIPT_DIR}/.." && pwd)"
cd "${REPO_ROOT}"

if [ ! -f .env ]; then
  echo ".env is required for production env validation" >&2
  exit 1
fi

# Safe .env parsing - reject lines that look like shell commands
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

# Core required vars (always needed for minimal RAG chatbot runtime)

core_required_vars=(
  POSTGRES_PASSWORD
  REDIS_PASSWORD
  LITELLM_MASTER_KEY
  TELEGRAM_BOT_TOKEN
)

core_password_vars=(
  POSTGRES_PASSWORD
  REDIS_PASSWORD
  LITELLM_MASTER_KEY
)

optional_profile_vars=()
optional_password_vars=()

compose_profiles=",${COMPOSE_PROFILES:-},"

if [[ "${compose_profiles}" == *",ingest,"* || "${compose_profiles}" == *",full,"* || "${compose_profiles}" == *",vps-noncore,"* ]]; then
  optional_profile_vars+=(GDRIVE_SYNC_DIR)
fi

if [[ "${compose_profiles}" == *",ml,"* || "${compose_profiles}" == *",full,"* || "${compose_profiles}" == *",vps-noncore,"* ]]; then
  optional_profile_vars+=(
    NEXTAUTH_SECRET
    SALT
    ENCRYPTION_KEY
    CLICKHOUSE_PASSWORD
    MINIO_ROOT_PASSWORD
    LANGFUSE_REDIS_PASSWORD
  )
  optional_password_vars+=(
    NEXTAUTH_SECRET
    SALT
    ENCRYPTION_KEY
    CLICKHOUSE_PASSWORD
    MINIO_ROOT_PASSWORD
    LANGFUSE_REDIS_PASSWORD
  )
fi

require_present() {
  local var_name
  for var_name in "$@"; do
    if [ -z "${!var_name:-}" ]; then
      echo "${var_name} is required in production env" >&2
      exit 1
    fi
  done
}

require_present "${core_required_vars[@]}"

if [ "${#optional_profile_vars[@]}" -gt 0 ]; then
  require_present "${optional_profile_vars[@]}"
fi

# Minimum password complexity check (>=12 chars) for active sensitive credentials
for pw_var in "${core_password_vars[@]}" "${optional_password_vars[@]}"; do
  pw_value="${!pw_var:-}"
  if [ "${#pw_value}" -lt 12 ]; then
    echo "${pw_var} must be at least 12 characters long (got ${#pw_value})" >&2
    exit 1
  fi
done

# VPS deploy guard: project name must be vps

if [ "${COMPOSE_PROJECT_NAME:-vps}" != "vps" ]; then
  echo "COMPOSE_PROJECT_NAME must be vps for VPS deploys" >&2
  exit 1
fi

# Root disk usage deploy blocker

vps_disk_usage_max_percent="${VPS_DISK_USAGE_MAX_PERCENT:-90}"
root_usage_percent="$(df -P / | awk 'NR==2 {gsub(/%/, "", $5); print $5}')"
if [ -n "$root_usage_percent" ] && [ "$root_usage_percent" -gt "$vps_disk_usage_max_percent" ]; then
  echo "root disk usage ${root_usage_percent}% exceeds ${vps_disk_usage_max_percent}% threshold; run minimal-runtime cleanup before deploy" >&2
  exit 1
fi

# Validate merged Compose config

docker compose --env-file .env -f compose.yml -f compose.vps.yml config >/dev/null

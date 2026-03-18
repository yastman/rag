#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd -- "${SCRIPT_DIR}/.." && pwd)"
cd "${REPO_ROOT}"

if [ ! -f .env ]; then
  echo ".env is required for production env validation" >&2
  exit 1
fi

set -a
# shellcheck disable=SC1091
. ./.env
set +a

handoff_enabled="${HANDOFF_ENABLED:-false}"
managers_group_id="${MANAGERS_GROUP_ID:-}"

if [ "${handoff_enabled}" = "true" ] && [ -z "${managers_group_id}" ]; then
  echo "HANDOFF_ENABLED=true but MANAGERS_GROUP_ID is missing in production env" >&2
  exit 1
fi

docker compose --env-file .env -f compose.yml -f compose.vps.yml config >/dev/null

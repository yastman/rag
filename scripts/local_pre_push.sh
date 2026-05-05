#!/usr/bin/env bash
# Fast local pre-push sanity gate: lightweight checks before code leaves the machine.
# Called by pre-commit pre-push hook and can be run manually via:
#   make local-pre-push
set -euo pipefail

cd "$(git rev-parse --show-toplevel)"

echo "==> Running make check..."
make check

if ! command -v docker >/dev/null 2>&1; then
  echo "WARN: Docker CLI not found; skipping Compose config validation."
  echo "==> Fast local pre-push sanity gate passed."
  exit 0
fi

if ! docker compose version >/dev/null 2>&1; then
  echo "WARN: Docker Compose not available; skipping Compose config validation."
  echo "==> Fast local pre-push sanity gate passed."
  exit 0
fi

echo "==> Validating Compose configs (dev + VPS)..."
COMPOSE_DISABLE_ENV_FILE=1 docker compose --env-file tests/fixtures/compose.ci.env -f compose.yml -f compose.dev.yml config --quiet
COMPOSE_DISABLE_ENV_FILE=1 docker compose --env-file tests/fixtures/compose.ci.env -f compose.yml -f compose.vps.yml config --quiet

echo "==> Fast local pre-push sanity gate passed."

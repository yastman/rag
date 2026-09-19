#!/usr/bin/env bash
# Shared, read-only release topology selection; sourced by the two release gates.
set -euo pipefail

release_compose_init() {
  local file service rendered
  local -a files required
  case "${RELEASE_TOPOLOGY:-minimal}" in
    minimal) release_profile=postgres ;;
    full) release_profile=full ;;
    *) echo "RELEASE_TOPOLOGY must be minimal or full" >&2; return 1 ;;
  esac
  IFS="${COMPOSE_PATH_SEPARATOR:-:}" read -r -a files <<< "${COMPOSE_FILE:-compose.yml}"
  release_compose=(docker compose --env-file .env)
  for file in "${files[@]}"; do
    [ -f "$file" ] || { echo "Compose file missing: $file" >&2; return 1; }
    release_compose+=(-f "$file")
  done
  export COMPOSE_PROJECT_NAME="${COMPOSE_PROJECT_NAME:-vps}"
  export COMPOSE_PROFILES=""
  release_compose+=(--profile "$release_profile")
  if ! rendered="$("${release_compose[@]}" config --services 2>/dev/null)"; then
    echo "Compose configuration invalid (details withheld to protect environment values)" >&2
    return 1
  fi
  required=(redis qdrant bge-m3 bot postgres)
  [ "$release_profile" != full ] || required+=(ingestion)
  mapfile -t release_services <<< "$rendered"
  for service in "${required[@]}"; do
    if ! printf '%s\n' "${release_services[@]}" | grep -Fxq "$service"; then
      echo "Required release service missing: $service" >&2; return 1
    fi
  done
  for service in "${release_services[@]}"; do
    if ! printf '%s\n' "${required[@]}" | grep -Fxq "$service"; then
      echo "Unexpected service in release topology" >&2; return 1
    fi
  done
}

#!/usr/bin/env bash
# Deploy to VPS via git pull + selective Docker rebuild
# Usage: ./scripts/deploy-vps.sh [--dry-run] [service...]
#
# Examples:
#   ./scripts/deploy-vps.sh                    # Auto-detect changes, rebuild affected
#   ./scripts/deploy-vps.sh vps-bot            # Force rebuild specific service
#   ./scripts/deploy-vps.sh --dry-run          # Show what would happen

set -euo pipefail

# VPS connection
VPS_HOST="REDACTED_VPS_IP"
VPS_PORT="1654"
VPS_USER="admin"
VPS_KEY="$HOME/.ssh/vps_access_key"
VPS_DIR="/opt/rag-fresh"
COMPOSE_FILE="docker-compose.vps.yml"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

log() { echo -e "${GREEN}[DEPLOY]${NC} $1"; }
warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
info() { echo -e "${CYAN}[INFO]${NC} $1"; }
error() { echo -e "${RED}[ERROR]${NC} $1"; exit 1; }

ssh_cmd() {
    ssh -i "$VPS_KEY" -p "$VPS_PORT" -o IdentitiesOnly=yes -o StrictHostKeyChecking=no "$VPS_USER@$VPS_HOST" "$@"
}

# Parse args
DRY_RUN=false
FORCE_SERVICES=()
for arg in "$@"; do
    case "$arg" in
        --dry-run) DRY_RUN=true ;;
        *) FORCE_SERVICES+=("$arg") ;;
    esac
done

$DRY_RUN && warn "Dry run mode — no changes will be made"

# Verify SSH key
[[ -f "$VPS_KEY" ]] || error "SSH key not found: $VPS_KEY"

# Step 1: Push local changes
log "Pushing to GitHub..."
if ! $DRY_RUN; then
    git push origin main 2>&1 | tail -3
fi

# Step 2: Pull on VPS
log "Pulling on VPS..."
if ! $DRY_RUN; then
    ssh_cmd "cd $VPS_DIR && git pull origin main" 2>&1 | tail -5
fi

# Step 3: Determine services to rebuild
SERVICES_TO_BUILD=()

if [[ ${#FORCE_SERVICES[@]} -gt 0 ]]; then
    SERVICES_TO_BUILD=("${FORCE_SERVICES[@]}")
    info "Force rebuild: ${SERVICES_TO_BUILD[*]}"
else
    # Auto-detect from git diff
    CHANGED_FILES=$(ssh_cmd "cd $VPS_DIR && git diff --name-only HEAD~1..HEAD 2>/dev/null" || echo "")

    if [[ -z "$CHANGED_FILES" ]]; then
        warn "No changed files detected, skipping rebuild"
    else
        info "Changed files:"
        echo "$CHANGED_FILES" | head -20 | sed 's/^/  /'

        # Map files to services
        echo "$CHANGED_FILES" | grep -qE '^(telegram_bot/|src/)' && SERVICES_TO_BUILD+=(vps-bot)
        echo "$CHANGED_FILES" | grep -qE '^services/bge-m3-api/' && SERVICES_TO_BUILD+=(vps-bge-m3)
        echo "$CHANGED_FILES" | grep -qE '^services/docling/' && SERVICES_TO_BUILD+=(vps-docling)
        echo "$CHANGED_FILES" | grep -qE '^services/user-base/' && SERVICES_TO_BUILD+=(vps-user-base)
        echo "$CHANGED_FILES" | grep -qE '^(Dockerfile\.ingestion|pyproject\.toml|uv\.lock)' && SERVICES_TO_BUILD+=(vps-ingestion)
        echo "$CHANGED_FILES" | grep -qE '^docker/litellm/' && info "LiteLLM config changed — will restart"

        # Config-only changes
        if echo "$CHANGED_FILES" | grep -qE '^docker-compose\.vps\.yml$'; then
            info "Compose file changed — will recreate all"
        fi
    fi
fi

# Step 4: Build and restart
if [[ ${#SERVICES_TO_BUILD[@]} -gt 0 ]]; then
    log "Rebuilding: ${SERVICES_TO_BUILD[*]}"
    if ! $DRY_RUN; then
        ssh_cmd "cd $VPS_DIR && docker compose --compatibility -f $COMPOSE_FILE build ${SERVICES_TO_BUILD[*]}"
    fi
fi

log "Starting services..."
if ! $DRY_RUN; then
    ssh_cmd "cd $VPS_DIR && docker compose --compatibility -f $COMPOSE_FILE up -d"

    # Restart LiteLLM if config changed
    if echo "${CHANGED_FILES:-}" | grep -qE '^docker/litellm/'; then
        ssh_cmd "docker restart vps-litellm"
    fi
fi

# Step 5: Verify
log "Verifying..."
if ! $DRY_RUN; then
    sleep 5
    ssh_cmd "docker ps --format 'table {{.Names}}\t{{.Status}}' | grep vps"
fi

log "Deploy complete!"

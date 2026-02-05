#!/usr/bin/env bash
# Deploy rag-fresh to VPS via rsync
# Usage: ./scripts/deploy-vps.sh [--dry-run]

set -euo pipefail

# VPS connection
VPS_HOST="95.111.252.29"
VPS_PORT="1654"
VPS_USER="admin"
VPS_KEY="$HOME/.ssh/vps_access_key"
VPS_DIR="/home/admin/rag-fresh"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

log() { echo -e "${GREEN}[DEPLOY]${NC} $1"; }
warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
error() { echo -e "${RED}[ERROR]${NC} $1"; exit 1; }

# Parse args
DRY_RUN=""
if [[ "${1:-}" == "--dry-run" ]]; then
    DRY_RUN="--dry-run"
    warn "Dry run mode - no changes will be made"
fi

# Verify SSH key exists
[[ -f "$VPS_KEY" ]] || error "SSH key not found: $VPS_KEY"

# Build rsync command
RSYNC_OPTS=(
    -avz
    --progress
    --delete
    -e "ssh -i $VPS_KEY -p $VPS_PORT -o IdentitiesOnly=yes -o StrictHostKeyChecking=no"
    # Exclude patterns
    --exclude='.git'
    --exclude='.worktrees'
    --exclude='__pycache__'
    --exclude='*.pyc'
    --exclude='.pytest_cache'
    --exclude='.mypy_cache'
    --exclude='.ruff_cache'
    --exclude='logs/'
    --exclude='*.log'
    --exclude='.venv'
    --exclude='node_modules'
    --exclude='data/'
    --exclude='*.egg-info'
    --exclude='.coverage'
    --exclude='htmlcov'
    --exclude='.DS_Store'
    $DRY_RUN
)

log "Syncing to $VPS_USER@$VPS_HOST:$VPS_DIR"

# Create target directory if needed
ssh -i "$VPS_KEY" -p "$VPS_PORT" -o IdentitiesOnly=yes "$VPS_USER@$VPS_HOST" "mkdir -p $VPS_DIR"

# Sync files
rsync "${RSYNC_OPTS[@]}" ./ "$VPS_USER@$VPS_HOST:$VPS_DIR/"

log "Sync complete!"
echo ""
log "Next steps on VPS:"
echo "  ssh vps"
echo "  cd $VPS_DIR"
echo "  docker compose -f docker-compose.dev.yml --profile full up -d"

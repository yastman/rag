***REMOVED***!/usr/bin/env bash
***REMOVED*** Deploy to VPS via rsync + Docker build/up
***REMOVED***
***REMOVED*** Usage:
***REMOVED***   ./scripts/deploy-vps.sh [options]
***REMOVED***
***REMOVED*** Options:
***REMOVED***   --dry-run       Show what would happen, no changes made
***REMOVED***   --clean         Full reinstall: down -v, prune images/builder, then deploy
***REMOVED***   --skip-checks   Skip pre-deploy make check validation
***REMOVED***   -h, --help      Show this help message
***REMOVED***
***REMOVED*** Examples:
***REMOVED***   ./scripts/deploy-vps.sh                    ***REMOVED*** Standard deploy
***REMOVED***   ./scripts/deploy-vps.sh --clean            ***REMOVED*** Full reinstall from scratch
***REMOVED***   ./scripts/deploy-vps.sh --dry-run          ***REMOVED*** Show what would happen
***REMOVED***   ./scripts/deploy-vps.sh --skip-checks      ***REMOVED*** Skip lint/type checks

set -euo pipefail

***REMOVED*** Always sync project root regardless of caller's current directory.
SCRIPT_DIR="$(cd -- "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd -- "${SCRIPT_DIR}/.." && pwd)"
cd "${REPO_ROOT}"

***REMOVED*** =============================================================================
***REMOVED*** VPS connection
***REMOVED*** =============================================================================
VPS_HOST="REDACTED_VPS_IP"
VPS_PORT="1654"
VPS_USER="admin"
VPS_KEY="$HOME/.ssh/vps_access_key"
VPS_DIR="/opt/rag-fresh"
COMPOSE_FILE="docker-compose.vps.yml"

SSH_OPTS="-i ${VPS_KEY} -p ${VPS_PORT} -o IdentitiesOnly=yes -o StrictHostKeyChecking=no"
RSYNC_SSH_OPTS="${SSH_OPTS}"

***REMOVED*** =============================================================================
***REMOVED*** Colors
***REMOVED*** =============================================================================
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

log()   { echo -e "${GREEN}[DEPLOY]${NC} $1"; }
warn()  { echo -e "${YELLOW}[WARN]${NC} $1"; }
info()  { echo -e "${CYAN}[INFO]${NC} $1"; }
error() { echo -e "${RED}[ERROR]${NC} $1" >&2; exit 1; }

usage() {
    sed -n '3,18p' "$0" | sed 's/^***REMOVED*** \{0,1\}//'
    exit 0
}

ssh_cmd() {
    ***REMOVED*** shellcheck disable=SC2086
    ssh $SSH_OPTS "${VPS_USER}@${VPS_HOST}" "$@"
}

***REMOVED*** =============================================================================
***REMOVED*** Parse args
***REMOVED*** =============================================================================
DRY_RUN=false
CLEAN=false
SKIP_CHECKS=false

for arg in "$@"; do
    case "$arg" in
        --dry-run)      DRY_RUN=true ;;
        --clean)        CLEAN=true ;;
        --skip-checks)  SKIP_CHECKS=true ;;
        -h|--help)      usage ;;
        *) error "Unknown argument: $arg. Use --help for usage." ;;
    esac
done

$DRY_RUN  && warn "Dry run mode — no changes will be made"
$CLEAN    && warn "Clean mode — full reinstall (down -v + image prune)"

***REMOVED*** =============================================================================
***REMOVED*** Pre-flight checks
***REMOVED*** =============================================================================
[[ -f "$VPS_KEY" ]] || error "SSH key not found: $VPS_KEY"

***REMOVED*** =============================================================================
***REMOVED*** Step 1: Pre-deploy validation
***REMOVED*** =============================================================================
if ! $SKIP_CHECKS; then
    log "Running pre-deploy checks (make check)..."
    if ! $DRY_RUN; then
        make check || error "Pre-deploy checks failed. Fix errors or use --skip-checks."
    else
        info "[dry-run] Would run: make check"
    fi
else
    warn "Skipping pre-deploy checks (--skip-checks)"
fi

***REMOVED*** =============================================================================
***REMOVED*** Step 2: rsync — sync local files to VPS
***REMOVED*** =============================================================================
RSYNC_EXCLUDES=(
    --exclude '.git'
    --exclude '.venv'
    --exclude '__pycache__'
    --exclude 'node_modules'
    --exclude '.mypy_cache'
    --exclude '.ruff_cache'
    --exclude '.pytest_cache'
    --exclude 'logs/'
    --exclude '.env'
    --exclude '.env.local'
    --exclude '.env.server'
    --exclude '.claude'
    --exclude 'data/'
    --exclude '.cache'
    --exclude '.deepeval'
)

log "Syncing files to VPS via rsync..."
if ! $DRY_RUN; then
    rsync -avz --delete \
        "${RSYNC_EXCLUDES[@]}" \
        -e "ssh ${RSYNC_SSH_OPTS}" \
        ./ \
        "${VPS_USER}@${VPS_HOST}:${VPS_DIR}/"
else
    info "[dry-run] Would run: rsync -avz --delete ${RSYNC_EXCLUDES[*]} -e 'ssh ...' ./ ${VPS_USER}@${VPS_HOST}:${VPS_DIR}/"
fi

***REMOVED*** =============================================================================
***REMOVED*** Step 3: Optional clean — down -v + prune
***REMOVED*** =============================================================================
if $CLEAN; then
    log "Cleaning up old containers, volumes, and images..."
    if ! $DRY_RUN; then
        ssh_cmd "cd ${VPS_DIR} && docker compose -f ${COMPOSE_FILE} down -v"
        ssh_cmd "docker image prune -af && docker builder prune -af"
    else
        info "[dry-run] Would run: docker compose down -v && image/builder prune"
    fi
fi

***REMOVED*** =============================================================================
***REMOVED*** Step 4: Build images on VPS
***REMOVED*** =============================================================================
log "Building Docker images on VPS..."
if ! $DRY_RUN; then
    ssh_cmd "cd ${VPS_DIR} && docker compose -f ${COMPOSE_FILE} build"
else
    info "[dry-run] Would run: docker compose -f ${COMPOSE_FILE} build"
fi

***REMOVED*** =============================================================================
***REMOVED*** Step 5: Start services
***REMOVED*** =============================================================================
log "Starting services..."
if ! $DRY_RUN; then
    ssh_cmd "cd ${VPS_DIR} && docker compose --compatibility -f ${COMPOSE_FILE} up -d"
else
    info "[dry-run] Would run: docker compose --compatibility -f ${COMPOSE_FILE} up -d"
fi

***REMOVED*** =============================================================================
***REMOVED*** Step 6: Health check
***REMOVED*** =============================================================================
log "Verifying running containers..."
if ! $DRY_RUN; then
    sleep 5
    ssh_cmd "docker ps --format 'table {{.Names}}\t{{.Status}}\t{{.Ports}}' | grep vps" \
        || warn "No VPS containers found in docker ps output"
else
    info "[dry-run] Would run: docker ps --format 'table ...' | grep vps"
fi

log "Deploy complete!"

#!/usr/bin/env bash
# Deploy to VPS via rsync + Docker build/up
#
# Usage:
#   ./scripts/deploy-vps.sh [options]
#
# Options:
#   --dry-run       Show what would happen, no changes made
#   --clean         Full reinstall: down -v, prune images/builder, then deploy
#   --skip-checks   Skip pre-deploy make check validation
#   --core-only     Deploy only core RAG services (postgres/redis/qdrant/bge-m3/litellm/bot)
#   --verify        Run VPS RAG preflight after deploy
#   -h, --help      Show this help message
#
# Examples:
#   ./scripts/deploy-vps.sh                    # Standard deploy
#   ./scripts/deploy-vps.sh --clean            # Full reinstall from scratch
#   ./scripts/deploy-vps.sh --core-only        # Deploy only core services
#   ./scripts/deploy-vps.sh --core-only --verify
#   ./scripts/deploy-vps.sh --dry-run          # Show what would happen
#   ./scripts/deploy-vps.sh --skip-checks      # Skip lint/type checks

set -euo pipefail

# Always sync project root regardless of caller's current directory.
SCRIPT_DIR="$(cd -- "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd -- "${SCRIPT_DIR}/.." && pwd)"
cd "${REPO_ROOT}"

# =============================================================================
# VPS connection
# =============================================================================
VPS_HOST="95.111.252.29"
VPS_PORT="1654"
VPS_USER="admin"
VPS_KEY="$HOME/.ssh/vps_access_key"
VPS_DIR="/opt/rag-fresh"

SSH_OPTS="-i ${VPS_KEY} -p ${VPS_PORT} -o IdentitiesOnly=yes -o StrictHostKeyChecking=no"
RSYNC_SSH_OPTS="${SSH_OPTS}"

# =============================================================================
# Colors
# =============================================================================
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
    sed -n '3,22p' "$0" | sed 's/^# \{0,1\}//'
    exit 0
}

ssh_cmd() {
    # shellcheck disable=SC2086
    ssh $SSH_OPTS "${VPS_USER}@${VPS_HOST}" "$@"
}

# =============================================================================
# Parse args
# =============================================================================
DRY_RUN=false
CLEAN=false
SKIP_CHECKS=false
CORE_ONLY=false
VERIFY=false

for arg in "$@"; do
    case "$arg" in
        --dry-run)      DRY_RUN=true ;;
        --clean)        CLEAN=true ;;
        --skip-checks)  SKIP_CHECKS=true ;;
        --core-only)    CORE_ONLY=true ;;
        --verify)       VERIFY=true ;;
        -h|--help)      usage ;;
        *) error "Unknown argument: $arg. Use --help for usage." ;;
    esac
done

$DRY_RUN  && warn "Dry run mode — no changes will be made"
$CLEAN    && warn "Clean mode — full reinstall (down -v + image prune)"
$CORE_ONLY && warn "Core-only mode — deploying: postgres redis qdrant bge-m3 litellm bot"
$VERIFY   && warn "Verify mode — will run scripts/vps_rag_preflight.py after deploy"

# =============================================================================
# Pre-flight checks
# =============================================================================
[[ -f "$VPS_KEY" ]] || error "SSH key not found: $VPS_KEY"

# Verify VPS has COMPOSE_FILE in .env
log "Checking VPS .env for COMPOSE_FILE=compose.yml:compose.vps.yml..."
if ! ssh_cmd "grep -q '^COMPOSE_FILE=compose.yml:compose.vps.yml$' ${VPS_DIR}/.env 2>/dev/null"; then
    error "VPS .env must contain exact value: COMPOSE_FILE=compose.yml:compose.vps.yml"
fi

# =============================================================================
# Step 1: Pre-deploy validation
# =============================================================================
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

# =============================================================================
# Step 2: rsync — sync local files to VPS
# =============================================================================
RSYNC_EXCLUDES=(
    # VCS & tooling caches
    --exclude '.git'
    --exclude '.venv'
    --exclude '__pycache__'
    --exclude 'node_modules'
    --exclude '.mypy_cache'
    --exclude '.ruff_cache'
    --exclude '.pytest_cache'
    --exclude '.cache'
    --exclude '.deepeval'
    # Env & secrets
    --exclude '.env'
    --exclude '.env.local'
    --exclude '.env.server'
    # Dev-only data & logs
    --exclude 'logs/'
    --exclude 'data/'
    --exclude '.claude'
    # Tests & evaluation (~5.5MB — not run on VPS)
    --exclude 'tests/'
    --exclude 'evaluation/'
    --exclude 'coverage*'
    --exclude 'test_*.py'
    --exclude 'test_output*.txt'
    # Documentation (~11MB — dev-only)
    --exclude 'docs/'
    # Unused on VPS (docker compose, not k3s)
    --exclude 'k8s/'
    --exclude 'legacy/'
    --exclude 'deploy/'
    # Planning & continuity artifacts
    --exclude '.planning/'
    --exclude '.signals/'
    --exclude '*.session'
    # Legacy dep files (project uses uv.lock)
    --exclude 'requirements*.txt'
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

# =============================================================================
# Step 3: Optional clean — down -v + prune
# =============================================================================
if $CLEAN; then
    log "Cleaning up old containers, volumes, and images..."
    if ! $DRY_RUN; then
        ssh_cmd "cd ${VPS_DIR} && docker compose down -v"
        ssh_cmd "docker image prune -af && docker builder prune -af"
    else
        info "[dry-run] Would run: docker compose down -v && image/builder prune"
    fi
fi

# =============================================================================
# Step 4: Validate docker compose config on VPS
# =============================================================================
log "Validating docker compose config on VPS..."
if ! $DRY_RUN; then
    ssh_cmd "cd ${VPS_DIR} && docker compose config >/dev/null"
else
    info "[dry-run] Would run: docker compose config >/dev/null"
fi

# =============================================================================
# Step 5: Build images on VPS
# =============================================================================
log "Building Docker images on VPS..."
CORE_SERVICES=(postgres redis qdrant bge-m3 litellm bot)
CORE_SERVICES_ARGS="${CORE_SERVICES[*]}"
if ! $DRY_RUN; then
    if $CORE_ONLY; then
        ssh_cmd "cd ${VPS_DIR} && docker compose build ${CORE_SERVICES_ARGS}"
    else
        ssh_cmd "cd ${VPS_DIR} && docker compose build"
    fi
else
    if $CORE_ONLY; then
        info "[dry-run] Would run: docker compose build ${CORE_SERVICES_ARGS}"
    else
        info "[dry-run] Would run: docker compose build"
    fi
fi

# =============================================================================
# Step 6: Start services
# =============================================================================
log "Starting services..."
if ! $DRY_RUN; then
    if $CORE_ONLY; then
        ssh_cmd "cd ${VPS_DIR} && docker compose --compatibility up -d ${CORE_SERVICES_ARGS}"
    else
        ssh_cmd "cd ${VPS_DIR} && docker compose --compatibility up -d"
    fi
else
    if $CORE_ONLY; then
        info "[dry-run] Would run: docker compose --compatibility up -d ${CORE_SERVICES_ARGS}"
    else
        info "[dry-run] Would run: docker compose --compatibility up -d"
    fi
fi

# =============================================================================
# Step 7: Health check
# =============================================================================
log "Verifying running containers..."
if ! $DRY_RUN; then
    sleep 5
    ssh_cmd "docker ps --format 'table {{.Names}}\t{{.Status}}\t{{.Ports}}' | grep vps" \
        || warn "No VPS containers found in docker ps output"
else
    info "[dry-run] Would run: docker ps --format 'table ...' | grep vps"
fi

# =============================================================================
# Step 8: Optional VPS preflight verification
# =============================================================================
if $VERIFY; then
    log "Running VPS RAG preflight verification..."
    if ! $DRY_RUN; then
        uv run python scripts/vps_rag_preflight.py --host vps --project-dir /opt/rag-fresh
    else
        info "[dry-run] Would run: uv run python scripts/vps_rag_preflight.py --host vps --project-dir /opt/rag-fresh"
    fi
fi

log "Deploy complete!"

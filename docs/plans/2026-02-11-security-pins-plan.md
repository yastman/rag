# Security: Pin UV Images + Update MinIO — Implementation Plan

**Goal:** Harden Docker images by pinning uv builder images to SHA256 digests and replacing vulnerable MinIO image.

**Issue:** #71 — security: pin uv builder images + update minio (CVE)
**Milestone:** Stream-F: Infra-Sec
**Source audit:** `docs/plans/2026-02-09-docker-services-audit.md`

## Current State

### UV Image References (all use floating tag `0.9`)

| File | Line | Current Reference | Usage |
|------|------|-------------------|-------|
| `telegram_bot/Dockerfile` | 5 | `ghcr.io/astral-sh/uv:0.9-python3.12-bookworm-slim` | FROM builder |
| `Dockerfile` | 6 | `ghcr.io/astral-sh/uv:0.9-python3.12-bookworm-slim` | FROM builder |
| `Dockerfile.ingestion` | 10 | `ghcr.io/astral-sh/uv:0.9-python3.12-bookworm-slim` | FROM builder |
| `Dockerfile.ingestion` | 60 | `COPY --from=ghcr.io/astral-sh/uv:0.10 /uv` | Runtime uv binary |
| `services/bge-m3-api/Dockerfile` | 6 | `ghcr.io/astral-sh/uv:0.9-python3.12-bookworm-slim` | FROM builder |
| `services/user-base/Dockerfile` | 6 | `ghcr.io/astral-sh/uv:0.9-python3.12-bookworm-slim` | FROM builder |
| `services/docling/Dockerfile` | 18 | `ghcr.io/astral-sh/uv:0.9-python${PYTHON_VERSION}-bookworm-slim` | FROM builder |
| `services/bm42/Dockerfile` | 8 | `COPY --from=ghcr.io/astral-sh/uv:0.9 /uv` | COPY binary |

### MinIO Image

| File | Line | Current | CVE Status |
|------|------|---------|------------|
| `docker-compose.dev.yml` | 219 | `minio/minio:RELEASE.2024-11-07T00-52-20Z` | Vulnerable to CVE-2025-62506 (CVSS 8.1 HIGH — privilege escalation) |

### MinIO Distribution Status (Oct 2025)

MinIO stopped publishing free Docker images to Docker Hub in October 2025.
Options:
- **Chainguard** `cgr.dev/chainguard/minio` — free, minimal, continuously patched
- **Build from source** via `go install github.com/minio/minio@latest`
- **Bitnami** `bitnami/minio` — still maintained

### Alertmanager

| File | Line | Current |
|------|------|---------|
| `docker-compose.dev.yml` | 421 | `prom/alertmanager:v0.28.1` |

### .dockerignore Coverage

| Location | Status |
|----------|--------|
| Root `.dockerignore` | Present, comprehensive (128 lines) |
| `services/bge-m3-api/.dockerignore` | Present, minimal (9 lines) |
| `services/user-base/.dockerignore` | Present, minimal (9 lines) |
| `services/bm42/` | MISSING |
| `services/docling/` | MISSING |
| `telegram_bot/` | MISSING (uses root) |

### Non-root User Status

| Dockerfile | Non-root? | Details |
|------------|-----------|---------|
| `telegram_bot/Dockerfile` | YES | `botuser:botgroup` (1001:1001) |
| `Dockerfile` | YES | `botuser:botgroup` (1001:1001) |
| `Dockerfile.ingestion` | YES | `ingestion` (1000) |
| `services/bge-m3-api/Dockerfile` | YES | `appuser:appgroup` (1001:1001) |
| `services/user-base/Dockerfile` | YES | `appuser:appgroup` (1001:1001) |
| `services/bm42/Dockerfile` | YES | `appuser:appgroup` (1001:1001) |
| `services/docling/Dockerfile` | YES | `docling:docling` (1001:1001) |
| `docker/mlflow/Dockerfile` | NO | Runs as root (FROM mlflow base) |

## Implementation Steps

### Step 1: Get UV Digest and Pin All Dockerfiles (3 min)

**Resolve current digest:**

    docker pull ghcr.io/astral-sh/uv:0.9-python3.12-bookworm-slim
    docker inspect --format='{{index .RepoDigests 0}}' ghcr.io/astral-sh/uv:0.9-python3.12-bookworm-slim

    docker pull ghcr.io/astral-sh/uv:0.10
    docker inspect --format='{{index .RepoDigests 0}}' ghcr.io/astral-sh/uv:0.10

    docker pull ghcr.io/astral-sh/uv:0.9
    docker inspect --format='{{index .RepoDigests 0}}' ghcr.io/astral-sh/uv:0.9

**Pin pattern** (tag + digest for readability + reproducibility):

    FROM ghcr.io/astral-sh/uv:0.9-python3.12-bookworm-slim@sha256:<DIGEST> AS builder

**Files to update (6 builder FROMs + 2 COPY --from):**

1. `telegram_bot/Dockerfile:5` — FROM line
2. `Dockerfile:6` — FROM line
3. `Dockerfile.ingestion:10` — FROM builder line
4. `Dockerfile.ingestion:60` — COPY --from uv:0.10 line
5. `services/bge-m3-api/Dockerfile:6` — FROM line
6. `services/user-base/Dockerfile:6` — FROM line
7. `services/docling/Dockerfile:18` — FROM line (uses ARG PYTHON_VERSION)
8. `services/bm42/Dockerfile:8` — COPY --from uv:0.9 line

**Renovate compatibility:** `renovate.json` line 94 already groups `ghcr.io/astral-sh/uv`. Renovate supports digest pinning natively — it will update both tag and digest on new releases.

### Step 2: Replace MinIO Image (3 min)

**Problem:** `minio/minio:RELEASE.2024-11-07T00-52-20Z` is vulnerable (CVE-2025-62506, CVSS 8.1) and official Docker images are no longer published.

**Solution:** Switch to Chainguard MinIO image (free, continuously patched, distroless):

    image: cgr.dev/chainguard/minio:latest

**Alternative (if Chainguard has issues):** Bitnami `bitnami/minio:latest`

**File:** `docker-compose.dev.yml:219`

**Change:**

    # Before
    image: minio/minio:RELEASE.2024-11-07T00-52-20Z

    # After
    image: cgr.dev/chainguard/minio:latest

**Verify entrypoint compatibility:**
- Current: `entrypoint: sh` + `command: -c 'mkdir -p /data/langfuse && minio server ...'`
- Chainguard images are distroless (no shell) — need to adjust entrypoint
- Alternative: use `bitnami/minio` which has shell, or pre-create bucket via init container

**Validation:**

    docker compose --profile ml up -d minio
    curl -f http://localhost:9090/minio/health/live

**Update `renovate.json`:**
- Line 79-84: change `matchPackageNames` from `minio/minio` to new image name
- Update versioning regex if needed (Chainguard uses semver, Bitnami uses semver)

### Step 3: Add Missing .dockerignore Files (2 min)

Create `.dockerignore` for services without one:

**`services/bm42/.dockerignore`:**

    __pycache__/
    *.pyc
    .venv/
    .git/
    *.md
    tests/
    .ruff_cache/
    .pytest_cache/
    .env
    .env.*

**`services/docling/.dockerignore`:**

    __pycache__/
    *.pyc
    .venv/
    .git/
    *.md
    tests/
    .ruff_cache/
    .pytest_cache/
    .env
    .env.*

**`telegram_bot/.dockerignore`:**
Not needed — `telegram_bot/Dockerfile` uses root context, covered by root `.dockerignore`.

### Step 4: Add Non-root User to MLflow (2 min)

**File:** `docker/mlflow/Dockerfile`

**Current state (lines 1-13):** No USER directive, runs as root.

**Add after line 6 (after pip install):**

    RUN useradd -m -u 1001 -s /bin/false mlflow
    USER mlflow

**Verify:** MLflow writes to `/mlflow` mount — ensure volume permissions are correct.
May need `chown` on the volume mount or `runAsUser` in compose:

    user: "1001:1001"

### Step 5: Verify Alertmanager Version (1 min)

**Current:** `prom/alertmanager:v0.28.1` (docker-compose.dev.yml:421)
**Status:** v0.28.x is current stable branch (latest is v0.28.1 as of Feb 2026).
No Prometheus in compose (uses Loki + Promtail stack) — no version alignment needed.

**Action:** No change needed. Renovate tracks this via `monitoring` group (renovate.json:69-77).

## Test Strategy

1. **Build all images** — verify digest-pinned images resolve correctly:

        docker compose build bot
        docker compose -f docker-compose.dev.yml --profile ml build ingestion
        docker compose -f docker-compose.dev.yml --profile ml up -d minio
        # Check MinIO health
        curl -f http://localhost:9090/minio/health/live

2. **Verify non-root** — check all containers run as non-root:

        for c in dev-bot dev-bge-m3 dev-minio dev-mlflow; do
            echo "$c: $(docker exec $c whoami 2>/dev/null || echo 'N/A')"
        done

3. **Renovate dry-run** — verify Renovate can parse new digest format:

        # Check renovate.json is valid JSON
        python -m json.tool renovate.json > /dev/null

4. **Langfuse integration** — verify Langfuse connects to new MinIO:

        docker compose --profile full up -d
        # Check Langfuse web logs for S3 connection errors

## Acceptance Criteria

- [ ] All 8 uv image references pinned with `@sha256:` digests
- [ ] MinIO updated to patched image (CVE-2025-62506 resolved)
- [ ] MinIO healthcheck passes
- [ ] Langfuse connects to new MinIO successfully
- [ ] Missing `.dockerignore` files added (bm42, docling)
- [ ] MLflow runs as non-root user
- [ ] Renovate config updated for new MinIO image source
- [ ] All images build successfully
- [ ] `make check` passes (no code changes, only Docker)

## Effort Estimate

| Step | Time | Risk |
|------|------|------|
| 1. Pin uv digests | 3 min | Low — mechanical, Renovate handles future |
| 2. Replace MinIO | 3 min | Medium — entrypoint compatibility with distroless |
| 3. Add .dockerignore | 2 min | Low — copy existing pattern |
| 4. MLflow non-root | 2 min | Low — volume permissions to verify |
| 5. Alertmanager check | 1 min | None — already current |
| **Total** | **~11 min** | |

## Risks and Mitigations

| Risk | Mitigation |
|------|------------|
| Chainguard MinIO distroless has no shell | Use bitnami/minio as fallback, or docker-entrypoint script |
| MLflow non-root breaks volume writes | Add `user: "1001:1001"` in compose |
| Digest changes break CI | Renovate auto-updates digests |
| Floating `0.9` tag means digest changes frequently | Pin to exact version like `0.9.26` + digest for stability |

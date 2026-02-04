# Docker Infrastructure Hardening

**Date:** 2026-02-04
**Status:** Draft
**Branch:** `fix/docker-hardening`

## Problem Statement

Audit выявил несколько проблем в Docker-конфигурации, от критических (ломают запуск) до средних (безопасность/воспроизводимость).

## Scope

### In Scope (Critical + Important)

| Priority | Issue | Location | Fix |
|----------|-------|----------|-----|
| P0 | ENTRYPOINT + command duplication | `docker-compose.dev.yml:550` | Remove command or use args only |
| P0 | Healthchecks use `requests` | `docker-compose.dev.yml:106,125` | Switch to `urllib.request` |
| P1 | Unpinned image tags | minio, docling | Pin to specific versions |
| P1 | Ports open to network | langfuse, litellm | Bind to `127.0.0.1` |

### Out of Scope

- Non-root users in service Dockerfiles (bm42, user-base, bge-m3)
- Pinning pip dependencies in service Dockerfiles
- Multi-stage builds for root Dockerfile
- `deploy.resources.limits` enforcement (requires `--compatibility` flag)

## Design

### Fix 1: Ingestion Command Duplication (P0)

**Current state:**

```dockerfile
# Dockerfile.ingestion:93-94
ENTRYPOINT ["uv", "run", "python", "-m", "src.ingestion.unified.cli"]
CMD ["run", "--watch"]
```

```yaml
# docker-compose.dev.yml:550
command: ["uv", "run", "python", "-m", "src.ingestion.unified.cli", "run", "--watch"]
```

**Problem:** Docker concatenates ENTRYPOINT + command, resulting in:
```
uv run python -m src.ingestion.unified.cli uv run python -m src.ingestion.unified.cli run --watch
```

**Solution:** Remove `command` from docker-compose.dev.yml. The Dockerfile already has correct ENTRYPOINT + CMD.

```yaml
# docker-compose.dev.yml - REMOVE line 550
# command: ["uv", "run", "python", "-m", "src.ingestion.unified.cli", "run", "--watch"]
```

**Alternative (if override needed):** Use only arguments:
```yaml
command: ["run", "--watch"]  # Appended to ENTRYPOINT
```

### Fix 2: Healthchecks Without requests (P0)

**Current state:**

```yaml
# docker-compose.dev.yml:106 (bm42)
healthcheck:
  test: ["CMD", "python", "-c", "import requests; requests.get('http://localhost:8000/health', timeout=5)"]

# docker-compose.dev.yml:125 (user-base)
healthcheck:
  test: ["CMD", "python", "-c", "import requests; requests.get('http://localhost:8000/health', timeout=5)"]
```

**Problem:** `requests` is not explicitly installed in bm42/user-base Dockerfiles. Works only if pulled transitively.

**Solution:** Use `urllib.request` (stdlib, always available):

```yaml
healthcheck:
  test: ["CMD", "python", "-c", "import urllib.request; urllib.request.urlopen('http://localhost:8000/health', timeout=5)"]
```

**Affected services:**
- bm42 (line 106)
- user-base (line 125)
- bge-m3 (line 88) — same pattern, fix for consistency
- lightrag (line 177) — same pattern

### Fix 3: Pin Image Tags (P1)

**Current state:**

| Image | Tag | Location |
|-------|-----|----------|
| `minio/minio` | `latest` | docker-compose.dev.yml:213 |
| `ghcr.io/docling-project/docling-serve-cpu` | `main` | docker-compose.dev.yml:136 |
| `quay.io/docling-project/docling-serve` | `latest` | docker-compose.local.yml:64 |

**Solution:** Pin to current working versions:

```yaml
# docker-compose.dev.yml
minio:
  image: minio/minio:RELEASE.2024-11-07T00-52-20Z  # or latest stable

docling:
  image: ghcr.io/docling-project/docling-serve-cpu:v2.2.0  # check actual version
```

```yaml
# docker-compose.local.yml
docling:
  image: quay.io/docling-project/docling-serve:v2.2.0
```

**Note:** Need to verify current working versions before pinning.

### Fix 4: Bind Ports to Localhost (P1)

**Current state:**

```yaml
# docker-compose.dev.yml:319
langfuse:
  ports:
    - "3001:3000"  # Open to all interfaces

# docker-compose.dev.yml:461
litellm:
  ports:
    - "4000:4000"  # Open to all interfaces
```

**Problem:** On dev machine in network, these services are accessible from other hosts.

**Solution:** Bind to localhost only:

```yaml
langfuse:
  ports:
    - "127.0.0.1:3001:3000"

litellm:
  ports:
    - "127.0.0.1:4000:4000"
```

## Implementation Plan

### Task 1: Fix ingestion command
- File: `docker-compose.dev.yml`
- Action: Remove line 550 (`command: [...]`)

### Task 2: Fix healthchecks
- File: `docker-compose.dev.yml`
- Lines: 88, 106, 125, 177
- Action: Replace `requests.get` with `urllib.request.urlopen`

### Task 3: Bind ports to localhost
- File: `docker-compose.dev.yml`
- Lines: 319, 461
- Action: Add `127.0.0.1:` prefix

### Task 4: Pin image tags
- Files: `docker-compose.dev.yml`, `docker-compose.local.yml`
- Action: Replace `latest`/`main` with specific versions
- Prerequisite: Verify current working versions

## Testing

```bash
# 1. Verify ingestion starts correctly
docker compose -f docker-compose.dev.yml --profile ingest up -d ingestion
docker logs dev-ingestion  # Should show normal startup, not command error

# 2. Verify healthchecks pass
docker compose -f docker-compose.dev.yml up -d bm42
docker inspect dev-bm42 --format='{{.State.Health.Status}}'  # Should be "healthy"

# 3. Verify ports are bound to localhost
docker compose -f docker-compose.dev.yml --profile bot up -d litellm
ss -tlnp | grep 4000  # Should show 127.0.0.1:4000, not 0.0.0.0:4000

# 4. Full stack smoke test
make docker-core-up
docker compose -f docker-compose.dev.yml ps  # All services healthy
```

## Rollback

All changes are in docker-compose files. Rollback via `git checkout`:

```bash
git checkout HEAD -- docker-compose.dev.yml docker-compose.local.yml
```

## Future Improvements (Out of Scope)

1. **Non-root users in service Dockerfiles** — Add `USER` directive to bm42, user-base, bge-m3
2. **Pin pip dependencies** — Use requirements.txt with pinned versions
3. **Multi-stage root Dockerfile** — Remove gcc from runtime layer
4. **Resource limits** — Document `--compatibility` flag requirement

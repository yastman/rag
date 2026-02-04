# Docker Infrastructure Hardening Implementation Plan

**Date:** 2026-02-04

**Goal:** Fix critical Docker issues that can break container startup and improve security/reproducibility.

**Scope:** Direct edits to Compose files only (no application code changes).

**Non-goals:**
- Redesigning service architecture, networks, or volumes
- Refactoring Dockerfiles (beyond Compose hardening)

**Tech stack:** Docker Compose, Python `urllib.request` (stdlib)

**Acceptance criteria (global):**
- `docker compose -f docker-compose.dev.yml config --quiet` succeeds
- `docker compose -f docker-compose.local.yml config --quiet` succeeds
- Core dev services can reach `healthy` without relying on optional Python deps in healthchecks
- No `latest`/`main` tags remain in Compose files for 3rd-party services where pinning is feasible

---

## Task 1: Fix Ingestion Command Duplication

**Files:**
- Modify: `docker-compose.dev.yml` (service: `ingestion`)

**Context:**
`Dockerfile.ingestion` has:
```dockerfile
ENTRYPOINT ["uv", "run", "python", "-m", "src.ingestion.unified.cli"]
CMD ["run", "--watch"]
```
If the compose file also sets the full `command: ["uv", "run", ...]`, Docker concatenates `ENTRYPOINT + command`, producing an invalid invocation.

**Step 1: Remove the full command override**

In `docker-compose.dev.yml`, remove this line from the `ingestion` service:
```yaml
    command: ["uv", "run", "python", "-m", "src.ingestion.unified.cli", "run", "--watch"]
```

Alternative (if you want Compose to override behavior): keep `ENTRYPOINT` from image and set only args:
```yaml
    command: ["run", "--watch"]
```

**Step 2: Verify syntax**

Run: `docker compose -f docker-compose.dev.yml config --quiet`
Expected: No output (valid YAML)

**Step 3: Acceptance**
- `docker compose -f docker-compose.dev.yml --profile ingest up -d ingestion` starts the container without argument-concatenation errors.

**Step 4: Commit (optional)**

```bash
git add docker-compose.dev.yml
git commit -m "fix(docker): remove duplicate ingestion command

Dockerfile.ingestion already has ENTRYPOINT + CMD. The compose command
was causing Docker to concatenate them into invalid invocation."
```

---

## Task 2: Fix Healthchecks to Use stdlib

**Files:**
- Modify: `docker-compose.dev.yml` (services: `bge-m3`, `bm42`, `user-base`, `lightrag`)

**Context:**
Healthchecks use `import requests`, but not all service images explicitly install `requests`. Switch to `urllib.request` (stdlib) to make healthchecks deterministic.

**Step 1: Replace healthcheck snippets**

Change each of these patterns:
```yaml
    healthcheck:
      test: ["CMD", "python", "-c", "import requests; requests.get('http://localhost:PORT/health', timeout=5)"]
```

To:
```yaml
    healthcheck:
      test: ["CMD", "python", "-c", "import urllib.request; urllib.request.urlopen('http://localhost:PORT/health', timeout=5)"]
```

**Step 2: Verify syntax**

Run: `docker compose -f docker-compose.dev.yml config --quiet`
Expected: No output (valid YAML)

**Step 3: Acceptance**
- `bm42` and `user-base` can become `healthy` without adding new Python deps to their images.

**Step 4: Commit (optional)**

```bash
git add docker-compose.dev.yml
git commit -m "fix(docker): use urllib.request in healthchecks

Replace requests.get with urllib.request.urlopen (stdlib).
bm42 and user-base don't explicitly install requests, making
healthchecks fragile. urllib.request is always available."
```

---

## Task 3: Bind Exposed Ports to Localhost

**Files:**
- Modify: `docker-compose.dev.yml` (services: `langfuse`, `litellm`)

**Context:**
langfuse and litellm expose ports to all interfaces (0.0.0.0). On a dev machine in a network, this exposes services to other hosts. Bind to 127.0.0.1 like other services.

**Step 1: Bind ports to 127.0.0.1**

Change from:
```yaml
    ports:
      - "3001:3000"
```

To:
```yaml
    ports:
      - "127.0.0.1:3001:3000"
```

And:
```yaml
    ports:
      - "4000:4000"
```

To:
```yaml
    ports:
      - "127.0.0.1:4000:4000"
```

**Step 2: Verify syntax**

Run: `docker compose -f docker-compose.dev.yml config --quiet`
Expected: No output (valid YAML)

**Step 3: Acceptance**
- `ss -tlnp | grep 3001` shows `127.0.0.1:3001` (not `0.0.0.0:3001`)
- `ss -tlnp | grep 4000` shows `127.0.0.1:4000` (not `0.0.0.0:4000`)

**Step 4: Commit (optional)**

```bash
git add docker-compose.dev.yml
git commit -m "fix(docker): bind langfuse/litellm ports to localhost

Prevent exposure to LAN. Matches pattern used by other services
(postgres, redis, qdrant all bind to 127.0.0.1)."
```

---

## Task 4: Pin Floating Image Tags

**Files:**
- Modify: `docker-compose.dev.yml` (services: `minio`, `docling`)
- Modify: `docker-compose.local.yml` (service: `docling`)

**Context:**
`latest` and `main` tags change without notice, breaking builds. Pin to specific versions.

**Step 1: Pin MinIO to a release tag (or digest)**

Preferred (human-readable, stable): pin to a specific `RELEASE.*` tag.

Change:
```yaml
  minio:
    image: minio/minio:latest
```

To:
```yaml
  minio:
    image: minio/minio:RELEASE.2024-11-07T00-52-20Z
```

Optional (most reproducible): additionally resolve and pin digest:
```bash
docker manifest inspect --verbose minio/minio:RELEASE.2024-11-07T00-52-20Z | head
```

**Step 2: Pin Docling images by digest**

Docling tags may be `main`/`latest` without a stable semver tag available in registry. Use digest pinning to freeze the exact image.

Resolve digests:
```bash
docker manifest inspect --verbose ghcr.io/docling-project/docling-serve-cpu:main | head -20
docker manifest inspect --verbose quay.io/docling-project/docling-serve:latest | head -20
```

As of **2026-02-04**, the digests observed:
- `ghcr.io/docling-project/docling-serve-cpu:main@sha256:4e93e8ec95accd74474a60d0cbbd1292b333bba2c53bb43074ae966d3f1becc8`
- `quay.io/docling-project/docling-serve:latest@sha256:0acc75bd86219a8c8cdf38970cb651b0567844d6c97ec9d9023624c8209c6efc`

Pin in `docker-compose.dev.yml`:
```yaml
  docling:
    image: ghcr.io/docling-project/docling-serve-cpu@sha256:4e93e8ec95accd74474a60d0cbbd1292b333bba2c53bb43074ae966d3f1becc8
```

Pin in `docker-compose.local.yml`:
```yaml
  docling:
    image: quay.io/docling-project/docling-serve@sha256:0acc75bd86219a8c8cdf38970cb651b0567844d6c97ec9d9023624c8209c6efc
```

**Step 3: Verify syntax for both files**

Run: `docker compose -f docker-compose.dev.yml config --quiet && docker compose -f docker-compose.local.yml config --quiet`
Expected: No output (valid YAML)

**Step 4: Acceptance**
- `docker pull` succeeds for the pinned `minio` tag and both Docling digests.

**Step 5: Commit (optional)**

```bash
git add docker-compose.dev.yml docker-compose.local.yml
git commit -m "fix(docker): pin minio and docling image tags

Replace floating tags (latest, main) with stable refs.
Prevents 'works today, breaks tomorrow' scenarios.

- minio: latest → RELEASE.2024-11-07T00-52-20Z
- docling-serve-cpu: main → @sha256:4e93e8e...
- docling-serve: latest → @sha256:0acc75b..."
```

---

## Task 5: Integration Test

**Files:**
- None (verification only)

**Step 1: Start core services**

Run (warning: `down -v` deletes volumes): `docker compose -f docker-compose.dev.yml down -v && docker compose -f docker-compose.dev.yml up -d postgres redis qdrant bm42`

Expected: All 4 services start

**Step 2: Wait for healthy status**

Run: `sleep 30 && docker compose -f docker-compose.dev.yml ps`

Expected: All services show "healthy" or "running"

**Step 3: Verify bm42 healthcheck works**

Run: `docker inspect dev-bm42 --format='{{.State.Health.Status}}'`

Expected: `healthy`

**Step 4: Verify port bindings**

Run: `docker compose -f docker-compose.dev.yml --profile bot up -d litellm && sleep 5 && ss -tlnp | grep 4000`

Expected: Shows `127.0.0.1:4000` (not `0.0.0.0:4000`)

**Step 5: Test ingestion starts correctly (if profile available)**

Run: `docker compose -f docker-compose.dev.yml --profile ingest up -d ingestion && sleep 10 && docker logs dev-ingestion 2>&1 | head -20`

Expected: Normal startup logs, NOT "uv: error: unrecognized arguments"

**Step 6: Cleanup**

Run: `docker compose -f docker-compose.dev.yml down`

---

## Summary

| Task | Files | Commits |
|------|-------|---------|
| 1. Fix ingestion command | docker-compose.dev.yml | 1 |
| 2. Fix healthchecks | docker-compose.dev.yml | 1 |
| 3. Bind ports to localhost | docker-compose.dev.yml | 1 |
| 4. Pin image tags | docker-compose.dev.yml, docker-compose.local.yml | 1 |
| 5. Integration test | — | 0 |

**Total:** 4 commits, 2 files modified

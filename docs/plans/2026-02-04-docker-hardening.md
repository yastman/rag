# Docker Infrastructure Hardening Implementation Plan

**Date:** 2026-02-04

**Goal:** Fix critical Docker issues + improve operational hygiene (memory limits, log rotation, secrets management).

**Scope:**
- Direct edits to Compose files
- Makefile updates for --compatibility
- DOCKER.md policy documentation

**Non-goals:**
- Redesigning service architecture, networks, or volumes
- Refactoring Dockerfiles (see phase2 plan)

**Tech stack:** Docker Compose, Python `urllib.request` (stdlib)

**Acceptance criteria (global):**
- `docker compose -f docker-compose.dev.yml config --quiet` succeeds
- `docker compose -f docker-compose.local.yml config --quiet` succeeds
- Core dev services can reach `healthy` without relying on optional Python deps in healthchecks
- No `latest`/`main` tags remain in Compose files for 3rd-party services
- Memory limits enforced via `--compatibility` flag
- Log rotation configured for noisy services
- Missing secrets cause immediate fail with clear error message

---

## Task 1: Fix Ingestion Command Duplication ✅

**Status:** Done

**Files:**
- Modified: `docker-compose.dev.yml` (service: `ingestion`)

**Context:**
`Dockerfile.ingestion` has:
```dockerfile
ENTRYPOINT ["uv", "run", "python", "-m", "src.ingestion.unified.cli"]
CMD ["run", "--watch"]
```
If the compose file also sets the full `command: ["uv", "run", ...]`, Docker concatenates `ENTRYPOINT + command`, producing an invalid invocation.

**Change:** Removed the full command override from compose file.

---

## Task 2: Fix Healthchecks to Use stdlib ✅

**Status:** Done

**Files:**
- Modified: `docker-compose.dev.yml` (services: `bge-m3`, `bm42`, `user-base`, `lightrag`)

**Context:**
Healthchecks used `import requests`, but not all service images explicitly install `requests`. Switched to `urllib.request` (stdlib) to make healthchecks deterministic.

**Change:** Replaced `requests.get()` with `urllib.request.urlopen()` in all healthchecks.

---

## Task 3: Bind Exposed Ports to Localhost ✅

**Status:** Done

**Files:**
- Modified: `docker-compose.dev.yml` (services: `langfuse`, `litellm`)

**Context:**
langfuse and litellm exposed ports to all interfaces (0.0.0.0). On a dev machine in a network, this exposes services to other hosts.

**Change:** Bound ports to `127.0.0.1:3001:3000` and `127.0.0.1:4000:4000`.

---

## Task 4: Pin Floating Image Tags ✅

**Status:** Done

**Files:**
- Modified: `docker-compose.dev.yml` (services: `minio`, `docling`)
- Modified: `docker-compose.local.yml` (service: `docling`)

**Context:**
`latest` and `main` tags change without notice, breaking builds.

**Change:**
- `minio/minio:latest` → `minio/minio:RELEASE.2024-11-07T00-52-20Z`
- `docling-serve-cpu:main` → `@sha256:4e93e8ec95accd74474a60d0cbbd1292b333bba2c53bb43074ae966d3f1becc8`
- `docling-serve:latest` → `@sha256:0acc75bd86219a8c8cdf38970cb651b0567844d6c97ec9d9023624c8209c6efc`

---

## Task 5: Memory Limits via --compatibility

**Status:** New

**Files:**
- Modify: `Makefile`

**Context:**
`deploy.resources.limits.memory` in compose only works with `docker compose --compatibility` or Swarm mode. Currently limits are defined but not enforced.

**Step 1: Add COMPOSE_CMD variable**

In `Makefile`, define a common compose command:

```makefile
COMPOSE_CMD := docker compose --compatibility -f docker-compose.dev.yml
```

**Step 2: Update all docker targets**

All docker compose commands must use `$(COMPOSE_CMD)`:

```makefile
# Up commands
docker-up:
	$(COMPOSE_CMD) up -d postgres redis qdrant docling bm42

docker-bot-up:
	$(COMPOSE_CMD) --profile bot up -d

docker-full-up:
	$(COMPOSE_CMD) --profile full up -d

docker-ml-up:
	$(COMPOSE_CMD) --profile ml up -d

docker-obs-up:
	$(COMPOSE_CMD) --profile obs up -d

docker-ai-up:
	$(COMPOSE_CMD) --profile ai up -d

docker-ingest-up:
	$(COMPOSE_CMD) --profile ingest up -d

# Down/logs/ps/build
docker-down:
	$(COMPOSE_CMD) down

docker-logs:
	$(COMPOSE_CMD) logs -f

docker-ps:
	$(COMPOSE_CMD) ps

docker-build:
	$(COMPOSE_CMD) build
```

**Step 3: Acceptance**

```bash
make docker-bot-up
docker inspect dev-litellm --format '{{.HostConfig.Memory}}'
# Expected: 536870912 (512M in bytes), NOT 0

docker inspect dev-bm42 --format '{{.HostConfig.Memory}}'
# Expected: 1073741824 (1G in bytes), NOT 0
```

Value must be > 0 and match the service's configured limit.

**Step 4: Commit**

```bash
git add Makefile
git commit -m "fix(docker): enable memory limits via --compatibility flag

deploy.resources.limits now enforced in non-Swarm mode.
All Makefile compose commands use \$(COMPOSE_CMD) with --compatibility."
```

---

## Task 6: Log Rotation for Noisy Services

**Status:** New

**Files:**
- Modify: `docker-compose.dev.yml`

**Context:**
Only `ingestion` has logging config (10m/3). Noisy services (bot, litellm, langfuse*) can grow logs unboundedly.

**Step 1: Add logging config to noisy services**

Add to `bot`, `litellm`, `langfuse`, `langfuse-worker`:

```yaml
  bot:
    # ... existing config ...
    logging:
      driver: "json-file"
      options:
        max-size: "50m"
        max-file: "5"

  litellm:
    # ... existing config ...
    logging:
      driver: "json-file"
      options:
        max-size: "50m"
        max-file: "5"

  langfuse:
    # ... existing config ...
    logging:
      driver: "json-file"
      options:
        max-size: "50m"
        max-file: "5"

  langfuse-worker:
    # ... existing config ...
    logging:
      driver: "json-file"
      options:
        max-size: "50m"
        max-file: "5"
```

**Not modified:**
- `ingestion` — already has `10m/3`
- `postgres`, `qdrant`, `redis` — databases typically don't log heavily

**Step 2: Acceptance**

Container must be recreated to pick up new LogConfig:

```bash
docker compose --compatibility -f docker-compose.dev.yml --profile bot up -d --force-recreate litellm
docker inspect dev-litellm --format '{{json .HostConfig.LogConfig}}'
# Expected: {"Type":"json-file","Config":{"max-file":"5","max-size":"50m"}}
```

**Step 3: Commit**

```bash
git add docker-compose.dev.yml
git commit -m "fix(docker): add log rotation for noisy services

bot, litellm, langfuse, langfuse-worker: max-size 50m, max-file 5.
Prevents unbounded log growth on dev machines."
```

---

## Task 7: Image Versioning Policy

**Status:** New

**Files:**
- Modify: `DOCKER.md`

**Context:**
Need to document the image versioning policy: when to use tags vs digests.

**Step 1: Add policy section to DOCKER.md**

```markdown
## Image Versioning Policy

| Type | Strategy | Example |
|------|----------|---------|
| Stable 3rd-party | Versioned tag | `redis:8.4.0`, `qdrant/qdrant:v1.16`, `clickhouse:24.8` |
| Floating tag only | Digest pin | `docling-serve-cpu@sha256:4e93e8e...` |
| Self-built | Local build | `services/bm42/Dockerfile` |

**Rules:**
- Never use `latest` or `main` tags in compose files
- Versioned tags (semver, release tags, version numbers) are sufficient for reproducibility
- Digest pinning required only when no stable tag exists (e.g., Docling)
- Update tags explicitly via Renovate PR or manual bump

**Current pinned digests:**
- `ghcr.io/docling-project/docling-serve-cpu@sha256:4e93e8ec95accd74474a60d0cbbd1292b333bba2c53bb43074ae966d3f1becc8`
- `quay.io/docling-project/docling-serve@sha256:0acc75bd86219a8c8cdf38970cb651b0567844d6c97ec9d9023624c8209c6efc`
```

**Step 2: Acceptance**

```bash
rg -n '\b(latest|main)\b' docker-compose.dev.yml docker-compose.local.yml
# Expected: empty output (no floating tags)
```

**Step 3: Commit**

```bash
git add DOCKER.md
git commit -m "docs(docker): document image versioning policy

Versioned tags for stable images, digest pins for floating-only.
No latest/main tags allowed in compose files."
```

---

## Task 8: Dev-Secrets Fail-Fast

**Status:** New

**Files:**
- Modify: `docker-compose.dev.yml`
- Modify: `.env.example`
- Modify: `DOCKER.md`

**Context:**
Dev compose has default values for secrets that could accidentally leak to production or cause silent misconfiguration. Critical secrets should fail immediately if missing.

**Step 1: Add fail-fast for bot profile secrets**

In `docker-compose.dev.yml`, update `litellm` service:

```yaml
  litellm:
    environment:
      LITELLM_MASTER_KEY: ${LITELLM_MASTER_KEY:?LITELLM_MASTER_KEY is required}
      # LLM providers — optional, at least one needed
      CEREBRAS_API_KEY: ${CEREBRAS_API_KEY:-}
      GROQ_API_KEY: ${GROQ_API_KEY:-}
      OPENAI_API_KEY: ${OPENAI_API_KEY:-}
```

Update `bot` service:

```yaml
  bot:
    environment:
      TELEGRAM_BOT_TOKEN: ${TELEGRAM_BOT_TOKEN:?TELEGRAM_BOT_TOKEN is required}
      VOYAGE_API_KEY: ${VOYAGE_API_KEY:?VOYAGE_API_KEY is required}
      LLM_API_KEY: ${LITELLM_MASTER_KEY:?LITELLM_MASTER_KEY is required}
```

**Step 2: Add fail-fast for ml profile secrets**

Update `langfuse` environment anchor (`&langfuse-env`):

```yaml
  langfuse-worker:
    environment: &langfuse-env
      # ... existing config ...
      NEXTAUTH_SECRET: ${NEXTAUTH_SECRET:?NEXTAUTH_SECRET is required}
      SALT: ${SALT:?SALT is required}
      ENCRYPTION_KEY: ${ENCRYPTION_KEY:?ENCRYPTION_KEY is required}
```

**Step 3: Keep dev defaults for core**

These remain unchanged (OK for local dev):
- `POSTGRES_PASSWORD: postgres`
- `redis-langfuse --requirepass langfuseredis`
- `MINIO_ROOT_PASSWORD: miniosecret`
- `CLICKHOUSE_PASSWORD: clickhouse`

**Step 4: Update .env.example**

```bash
# =============================================================================
# Required for bot profile
# =============================================================================
TELEGRAM_BOT_TOKEN=
VOYAGE_API_KEY=
LITELLM_MASTER_KEY=

# =============================================================================
# Required for ml profile
# =============================================================================
NEXTAUTH_SECRET=   # generate: openssl rand -base64 32
SALT=              # generate: openssl rand -base64 32
ENCRYPTION_KEY=    # generate: openssl rand -hex 32

# =============================================================================
# LLM Providers (at least one required for bot profile)
# =============================================================================
CEREBRAS_API_KEY=
GROQ_API_KEY=
OPENAI_API_KEY=
```

**Step 5: Update DOCKER.md**

Add section:

```markdown
## Required Environment Variables

| Profile | Required Variables | Notes |
|---------|-------------------|-------|
| core | None | Dev defaults for postgres/redis/qdrant |
| bot | TELEGRAM_BOT_TOKEN, VOYAGE_API_KEY, LITELLM_MASTER_KEY | + at least one LLM provider |
| ml | NEXTAUTH_SECRET, SALT, ENCRYPTION_KEY | Crypto keys for Langfuse |
| full | All of the above | |

**LLM Providers:** At least one of CEREBRAS_API_KEY, GROQ_API_KEY, or OPENAI_API_KEY must be set for the bot profile. LiteLLM uses fallback chain: Cerebras → Groq → OpenAI.

**Behavior:** Missing required variables cause compose to abort immediately with a clear error message (e.g., "TELEGRAM_BOT_TOKEN is required").
```

**Step 6: Acceptance**

```bash
# Test fail-fast (without editing .env)
TELEGRAM_BOT_TOKEN= make docker-bot-up
# Expected: compose aborts with "TELEGRAM_BOT_TOKEN is required"

# Core profile still works without secrets
make docker-up
# Expected: postgres, redis, qdrant, docling, bm42 start successfully
```

**Step 7: Commit**

```bash
git add docker-compose.dev.yml .env.example DOCKER.md
git commit -m "fix(docker): fail-fast for missing secrets in bot/ml profiles

Required: TELEGRAM_BOT_TOKEN, VOYAGE_API_KEY, LITELLM_MASTER_KEY (bot)
Required: NEXTAUTH_SECRET, SALT, ENCRYPTION_KEY (ml)
LLM providers optional but at least one needed (documented).
Core profile keeps dev defaults for local development."
```

---

## Task 9: Integration Test

**Status:** Updated (covers all changes)

**Files:** None (verification only)

**Step 1: Verify compose syntax**

```bash
docker compose --compatibility -f docker-compose.dev.yml config --quiet
docker compose --compatibility -f docker-compose.local.yml config --quiet
# Expected: no output (valid YAML)
```

**Step 2: Dev base stack without secrets**

```bash
make docker-down
make docker-up
sleep 30
docker compose --compatibility -f docker-compose.dev.yml ps
# Expected: postgres, redis, qdrant, docling, bm42 — healthy/running
```

**Step 3: Memory limits work (base stack)**

```bash
docker inspect dev-bm42 --format '{{.HostConfig.Memory}}'
# Expected: 1073741824 (1G), NOT 0
```

**Step 4: Bot profile + memory limits via Makefile**

```bash
make docker-bot-up
docker inspect dev-litellm --format '{{.HostConfig.Memory}}'
# Expected: 536870912 (512M), NOT 0
# This confirms Makefile uses --compatibility
```

**Step 5: Log rotation after recreate**

```bash
docker compose --compatibility -f docker-compose.dev.yml --profile bot up -d --force-recreate litellm
docker inspect dev-litellm --format '{{json .HostConfig.LogConfig}}'
# Expected: {"Type":"json-file","Config":{"max-file":"5","max-size":"50m"}}
```

**Step 6: Fail-fast works**

```bash
TELEGRAM_BOT_TOKEN= make docker-bot-up
# Expected: compose aborts with "TELEGRAM_BOT_TOKEN is required"
```

**Step 7: Port bindings (from original plan)**

```bash
ss -tlnp | grep -E '(3001|4000)'
# Expected: 127.0.0.1:3001, 127.0.0.1:4000 (NOT 0.0.0.0)
```

**Step 8: No floating tags**

```bash
rg -n '\b(latest|main)\b' docker-compose.dev.yml docker-compose.local.yml
# Expected: empty output
```

**Step 9: Cleanup**

```bash
make docker-down
```

---

## Summary

| Task | Files | Status |
|------|-------|--------|
| 1. Fix ingestion command | docker-compose.dev.yml | ✅ Done |
| 2. Fix healthchecks | docker-compose.dev.yml | ✅ Done |
| 3. Bind ports to localhost | docker-compose.dev.yml | ✅ Done |
| 4. Pin floating tags | docker-compose.dev.yml, docker-compose.local.yml | ✅ Done |
| 5. Memory limits | Makefile | New |
| 6. Log rotation | docker-compose.dev.yml | New |
| 7. Image pin policy | DOCKER.md | New |
| 8. Dev-secrets fail-fast | docker-compose.dev.yml, .env.example, DOCKER.md | New |
| 9. Integration test | — | Verification |

**Total:** 4 commits (Tasks 5–8), 4 files modified (Makefile, docker-compose.dev.yml, .env.example, DOCKER.md)

---

## Phase 2 (Separate Plan)

Dockerfile hardening tasks deferred to `docs/plans/2026-02-04-docker-hardening-phase2.md`:
- Non-root users for custom services (bm42, user-base, bge-m3-api)
- Pin dependency versions in Dockerfiles
- Multi-stage builds optimization

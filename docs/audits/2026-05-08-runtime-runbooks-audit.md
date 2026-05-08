# Runtime & Runbooks Documentation Audit

**Date:** 2026-05-08
**Auditor:** pr-worker (opencode-go/kimi-k2.6)
**Branch:** `docs/docs-runtime-runbooks-audit-20260508`
**Base:** `origin/dev`
**Scope:** `DOCKER.md`, `docs/LOCAL-DEVELOPMENT.md`, `docs/runbooks/*.md`, `services/README.md`, `services/*/README.md`
**Verification source:** `compose.yml`, `compose.dev.yml`, `Makefile`, `tests/fixtures/compose.ci.env`, service Dockerfiles, `docker/litellm/config.yaml`

## Executive Summary

- **Total findings:** 11
- **P1 (blocks quick orientation or factually wrong):** 7
- **P2 (inconsistency, stale format, missing info):** 4
- **Blockers for "quick orientation" workflows:** 5
- **Docs impact check:** Canonical runtime docs contain contradictions with live Compose contracts; operational runbooks contain commands that fail on a clean dev stack.

## Method

1. `rg` keyword sweep across scope files and Compose manifests.
2. `COMPOSE_DISABLE_ENV_FILE=1 docker compose --env-file tests/fixtures/compose.ci.env -f compose.yml -f compose.dev.yml --compatibility config --services` to verify default service set.
3. `make docs-check` — passed (no broken relative links).
4. `git diff --check` — passed.
5. Direct file reads of all scoped Markdown files, `compose.yml`, `compose.dev.yml`, `Makefile`, `docker/litellm/config.yaml`, `tests/fixtures/compose.ci.env`, `telegram_bot/Dockerfile`.
6. Runtime probes where possible (`docker run --rm qdrant/qdrant:v1.17.1 which curl`).

---

## Findings

### P1 — Alertmanager host endpoint documented but port not published

| | |
|---|---|
| **Doc** | `DOCKER.md` (line 74), `docs/runbooks/README.md` (line 12) |
| **Claim** | Alertmanager reachable at `http://localhost:9093`; health check `curl -fsS http://localhost:9093/-/healthy` |
| **Reality** | Neither `compose.yml` nor `compose.dev.yml` publishes Alertmanager port `9093` to the host. The service only binds internally. |
| **Evidence** | `grep -n "ports:" compose.yml compose.dev.yml` — no `ports` stanza for `alertmanager`. `compose.yml:728` sets `--web.external-url=http://localhost:9093` inside the container. |
| **Impact** | `make monitoring-up` + `curl http://localhost:9093/-/healthy` fails with `Connection refused`. Blocks the monitoring health validation workflow documented in `DOCKER.md`. |
| **Canonical owner** | `DOCKER.md` |
| **Proposed fix** | Add `ports: ["127.0.0.1:9093:9093"]` to `alertmanager` in `compose.dev.yml`, or remove/replace the host endpoint claim with the internal-only note. |
| **Priority** | P1 |
| **Blocks quick orientation** | Yes |

---

### P1 — LiteLLM runbook health endpoint mismatches Compose healthcheck

| | |
|---|---|
| **Doc** | `docs/runbooks/LITEllm_FAILURE.md` (lines 62, 65, 275) |
| **Claim** | Health check is `curl -s http://localhost:4000/health` or `curl -s ${LITELLM_URL}/health` |
| **Reality** | `compose.yml:212` healthcheck uses `/health/liveliness`. `DOCKER.md:131` and `Makefile:test-bot-health` both reference `/health/liveliness`. LiteLLM exposes `/health`, `/health/liveliness`, and `/health/readiness`; they return different payloads. |
| **Evidence** | `compose.yml:212`: `urllib.request.urlopen('http://localhost:4000/health/liveliness', timeout=5)`; `LITEllm_FAILURE.md:62`: `curl -s http://localhost:4000/health` |
| **Impact** | Operator may see a different response body/format than expected and misdiagnose proxy health. |
| **Canonical owner** | `docs/runbooks/LITEllm_FAILURE.md` |
| **Proposed fix** | Align runbook with canonical health endpoint (`/health/liveliness`) or explicitly document the difference between `/health` and `/health/liveliness`. |
| **Priority** | P1 |
| **Blocks quick orientation** | Yes |

---

### P1 — VPS ingestion recovery runbook uses `curl` inside Qdrant container, but Qdrant image lacks `curl`

| | |
|---|---|
| **Doc** | `docs/runbooks/vps-gdrive-ingestion-recovery.md` (lines 74–75, 93–94) |
| **Claim** | `docker compose exec qdrant curl -fsS http://localhost:6333/collections` |
| **Reality** | The `qdrant/qdrant:v1.17.1` image does not ship `curl`. The Qdrant healthcheck in `compose.yml:81` uses raw bash TCP sockets (`exec 3<>/dev/tcp/localhost/6333`), confirming the absence of `curl`. |
| **Evidence** | `docker run --rm qdrant/qdrant:v1.17.1 sh -c "which curl || echo 'curl not found'"` → `curl not found`. `compose.yml:81` healthcheck uses `printf 'GET /readyz HTTP/1.1...'` via `/dev/tcp`. |
| **Impact** | Runbook commands fail on a clean stack, forcing the operator to improvise. |
| **Canonical owner** | `docs/runbooks/vps-gdrive-ingestion-recovery.md` |
| **Proposed fix** | Replace `docker compose exec qdrant curl ...` with `docker compose exec qdrant sh -c "exec 3<>/dev/tcp/localhost/6333 && ..."` (matching the healthcheck pattern), or run `curl` from the host when the host port is published. |
| **Priority** | P1 |
| **Blocks quick orientation** | Yes |

---

### P1 — Redis runbook uses `redis-cli` inside bot container, but bot image lacks `redis-cli`

| | |
|---|---|
| **Doc** | `docs/runbooks/REDIS_CACHE_DEGRADATION.md` (line 117) |
| **Claim** | `docker compose ... exec bot redis-cli -h redis -a test-redis-password ping` |
| **Reality** | `telegram_bot/Dockerfile` installs `procps` (for `pgrep` healthcheck) and `gcc g++`, but no `redis-tools` or `redis-cli`. |
| **Evidence** | `grep -n "redis-cli\|curl\|wget" telegram_bot/Dockerfile` → no match. `compose.yml:318` bot healthcheck uses `pgrep -f 'telegram_bot.main'`. |
| **Impact** | Network connectivity verification step fails. The operator must instead exec into the `redis` container (which has `redis-cli`) or install the client. |
| **Canonical owner** | `docs/runbooks/REDIS_CACHE_DEGRADATION.md` |
| **Proposed fix** | Change command to exec into the `redis` container, e.g. `docker compose ... exec redis redis-cli -h redis -a <redacted> ping`, or add `redis-tools` to the bot Dockerfile. |
| **Priority** | P1 |
| **Blocks quick orientation** | Yes |

---

### P1 — PostgreSQL WAL recovery runbook assumes host bind mount, but compose uses named volume

| | |
|---|---|
| **Doc** | `docs/runbooks/POSTGRESQL_WAL_RECOVERY.md` (lines 28–29, 51, 83–84, 88–89) |
| **Claim** | Postgres data is on host at `${DATABASE_DIR:-./data}/postgres/`; `pg_resetwal` and `rm -rf` target that path. |
| **Reality** | `compose.yml:33` mounts a **named Docker volume** `postgres_data:/var/lib/postgresql/data`. There is no host bind mount to `./data/postgres`. The directory either does not exist or is empty on the host. |
| **Evidence** | `compose.yml:33`: `volumes: [postgres_data:/var/lib/postgresql/data]`; no `./data/postgres` bind mount. |
| **Impact** | All WAL recovery commands that reference the host path operate on the wrong location. `pg_resetwal` would run against an empty directory and silently fail or create a new empty cluster. Data loss recovery is impossible via the documented path. |
| **Canonical owner** | `docs/runbooks/POSTGRESQL_WAL_RECOVERY.md` |
| **Proposed fix** | Rewrite the runbook to use the named volume path (`docker run --rm -v postgres_data:/var/lib/postgresql/data ...`) or document the volume-first inspection steps (`docker volume inspect dev_postgres_data`, `docker compose exec postgres df -h /var/lib/postgresql/data`). |
| **Priority** | P1 |
| **Blocks quick orientation** | Yes |

---

### P1 — PostgreSQL WAL recovery runbook uses `postgres:16` image on PG17 data directory

| | |
|---|---|
| **Doc** | `docs/runbooks/POSTGRESQL_WAL_RECOVERY.md` (line 51) |
| **Claim** | `docker run --rm -v ... postgres:16 pg_resetwal -f /var/lib/postgresql/data` |
| **Reality** | `compose.yml:24` uses `pgvector/pgvector:pg17`. PostgreSQL `pg_resetwal` is major-version-specific; running the 16 binary against a 17 data directory is unsupported and may fail or corrupt the catalog. |
| **Evidence** | `compose.yml:24`: `image: pgvector/pgvector:pg17@sha256:...`; runbook uses `postgres:16`. |
| **Impact** | `pg_resetwal` may refuse to run or produce an incompatible WAL state, preventing recovery. |
| **Canonical owner** | `docs/runbooks/POSTGRESQL_WAL_RECOVERY.md` |
| **Proposed fix** | Use the same image as the running service: `pgvector/pgvector:pg17` (or at minimum `postgres:17`). |
| **Priority** | P1 |
| **Blocks quick orientation** | Yes |

---

### P1 — Two runbooks rely on non-deterministic Compose commands

| | |
|---|---|
| **Doc** | `docs/runbooks/POSTGRESQL_WAL_RECOVERY.md` (lines 21, 46, 57, 79, 89); `docs/runbooks/vps-gdrive-ingestion-recovery.md` (lines 52, 74, 85, 93) |
| **Claim** | Bare `docker compose logs postgres`, `docker compose stop postgres`, `docker compose exec ingestion ...`, etc. |
| **Reality** | The repo contract (`AGENTS.md`, `Makefile:393`) expects deterministic Compose usage with `COMPOSE_PROJECT_NAME=dev docker compose --env-file tests/fixtures/compose.ci.env -f compose.yml -f compose.dev.yml ...`, but this pattern is not yet consistent across runbooks. In addition to the two runbooks listed in this finding, other runbooks still contain bare `docker compose` commands (for example `LITEllm_FAILURE.md` and `LANGFUSE_TRACING_GAPS.md`). |
| **Evidence** | `docs/runbooks/REDIS_CACHE_DEGRADATION.md:36`: `COMPOSE_PROJECT_NAME=dev docker compose --env-file tests/fixtures/compose.ci.env -f compose.yml -f compose.dev.yml ps redis`. `POSTGRESQL_WAL_RECOVERY.md:21`: `docker compose logs postgres --tail=100`. |
| **Impact** | If `.env` is missing or incomplete, the bare `docker compose` commands fail because `POSTGRES_PASSWORD` and other required variables are undefined. This breaks the incident-response workflow when an operator is working from a fresh clone or CI environment. |
| **Canonical owner** | `docs/runbooks/POSTGRESQL_WAL_RECOVERY.md`, `docs/runbooks/vps-gdrive-ingestion-recovery.md` |
| **Proposed fix** | Update every command in both runbooks to the deterministic pattern, or at minimum add a preamble note about sourcing `.env` or using the CI fixture. |
| **Priority** | P1 |
| **Blocks quick orientation** | Yes |

---

### P2 — Two runbooks lack `Last verified` date header

| | |
|---|---|
| **Doc** | `docs/runbooks/POSTGRESQL_WAL_RECOVERY.md`; `docs/runbooks/vps-gdrive-ingestion-recovery.md` |
| **Claim** | — (no date header present) |
| **Reality** | All other runbooks (`LANGFUSE_TRACING_GAPS.md`, `LITEllm_FAILURE.md`, `REDIS_CACHE_DEGRADATION.md`, `QDRANT_TROUBLESHOOTING.md`) include `- **Last verified:** 2026-05-07`. |
| **Evidence** | Direct file reads show missing front-matter fields. |
| **Impact** | Operators cannot gauge staleness at a glance. |
| **Canonical owner** | `docs/runbooks/POSTGRESQL_WAL_RECOVERY.md`, `docs/runbooks/vps-gdrive-ingestion-recovery.md` |
| **Proposed fix** | Add `Last verified` and `Verification command` headers to match the runbook template. |
| **Priority** | P2 |
| **Blocks quick orientation** | No |

---

### P2 — Makefile has duplicate targets for observability stack

| | |
|---|---|
| **Doc** | `DOCKER.md` (line 46) documents `make docker-obs-up`; `docs/LOCAL-DEVELOPMENT.md` (line 51) documents `make monitoring-up` |
| **Claim** | Both are valid ways to start the observability profile. |
| **Reality** | `Makefile:407` (`docker-obs-up`) and `Makefile:748` (`monitoring-up`) both run `$(LOCAL_COMPOSE_CMD) --profile obs up -d`. They are functionally identical. |
| **Evidence** | `Makefile:407-410` and `Makefile:748-751`. |
| **Impact** | Confusion about canonical target; duplicate maintenance surface. |
| **Canonical owner** | `Makefile` (primary); `docs/LOCAL-DEVELOPMENT.md` and `DOCKER.md` (secondary) |
| **Proposed fix** | Deprecate one target (e.g., alias `docker-obs-up` to `monitoring-up` or vice versa) and document only the canonical name in both docs. |
| **Priority** | P2 |
| **Blocks quick orientation** | No |

---

### P2 — DOCKER.md Service Endpoints table omits Mini App ports

| | |
|---|---|
| **Doc** | `DOCKER.md` (line 63–76) "Service Endpoints (Host)" |
| **Claim** | Lists Qdrant, Redis, BGE-M3, Docling, LiteLLM, Langfuse, Loki, Alertmanager, RAG API, LiveKit. |
| **Reality** | `compose.dev.yml:159-169` publishes `mini-app-api` on `127.0.0.1:8090:8090` and `mini-app-frontend` on `127.0.0.1:8091:80`. Both are default (unprofiled) services. |
| **Evidence** | `compose.dev.yml:160-161` and `compose.dev.yml:167-169`. |
| **Impact** | Developers don't know where to reach the Mini App locally. |
| **Canonical owner** | `DOCKER.md` |
| **Proposed fix** | Add rows: `Mini App API | http://localhost:8090` and `Mini App Frontend | http://localhost:8091`. |
| **Priority** | P2 |
| **Blocks quick orientation** | No |

---

### P2 — Runbooks index omits `redis-langfuse` container name in service map

| | |
|---|---|
| **Doc** | `docs/runbooks/README.md` (line 32) |
| **Claim** | Langfuse row lists `dev-langfuse-1`, `dev-langfuse-worker-1`, `dev-clickhouse-1`, `dev-minio-1`. |
| **Reality** | `compose.yml:513` defines `redis-langfuse` as a separate service with its own container (`dev-redis-langfuse-1`). It is distinct from app `redis`. |
| **Evidence** | `compose.yml:513-543` defines `redis-langfuse` service. `docs/runbooks/README.md:26` correctly warns that app Redis is distinct from Langfuse Redis, but the container map omits the name. |
| **Impact** | Operator may confuse `dev-redis-1` (app cache) with `dev-redis-langfuse-1` (Langfuse telemetry queue). |
| **Canonical owner** | `docs/runbooks/README.md` |
| **Proposed fix** | Add `dev-redis-langfuse-1` to the Langfuse row, or create a separate row for `redis-langfuse`. |
| **Priority** | P2 |
| **Blocks quick orientation** | No |

---

## Verified Correct (No Drift)

### Compose Profiles & Services
- `DOCKER.md` profile/service matrix matches `compose.yml` + `compose.dev.yml` exactly.
- Default unprofiled services: `postgres`, `redis`, `qdrant`, `bge-m3`, `user-base`, `docling`, `mini-app-api`, `mini-app-frontend` — confirmed by `docker compose config --services`.
- Profile-gated services: `bot` (`bot`,`full`), `litellm` (`bot`,`voice`,`full`), `ingestion` (`ingest`,`full`), voice stack (`voice`,`full`), ML stack (`ml`,`full`), obs stack (`obs`,`full`).

### Makefile Shortcuts
- All documented `make docker-*` targets exist and invoke the correct profiles (`docker-bot-up`, `docker-ingest-up`, `docker-voice-up`, `docker-ml-up`, `docker-full-up`, `docker-ps`, `docker-down`).
- `make local-up`, `make local-down`, `make local-ps` exist and use the documented `LOCAL_SERVICES` set.
- `make test-bot-health`, `make validate-traces-fast`, `make check`, `make docs-check` all exist and execute correctly.

### Service Ports (Host)
- Qdrant `6333`/`6334`, Redis `6379`, BGE-M3 `8000`, Docling `5001`, LiteLLM `4000`, Langfuse `3001`, Loki `3100`, RAG API `8080`, LiveKit `7880` — all correctly mapped in `compose.dev.yml`.

### Healthcheck Endpoints (Internal)
- `postgres`: `pg_isready -U postgres` ✅
- `redis`: `redis-cli -a "$REDIS_PASSWORD" ping | grep -q PONG` ✅
- `qdrant`: raw HTTP `GET /readyz` via `/dev/tcp` ✅
- `bge-m3`: `GET http://localhost:8000/health` ✅
- `user-base`: `GET http://localhost:8000/health` ✅
- `docling`: `GET http://localhost:5001/health` ✅
- `litellm`: `GET http://localhost:4000/health/liveliness` ✅
- `bot`: `pgrep -f 'telegram_bot.main'` ✅
- `mini-app-api`: `GET http://localhost:8090/health` ✅
- `mini-app-frontend`: `wget -qO- http://127.0.0.1/health` ✅
- `ingestion`: `pgrep -f 'src.ingestion.unified.cli'` ✅
- `langfuse`: `wget -q --spider http://127.0.0.1:3000/api/public/health` ✅
- `langfuse-worker`: `pgrep -f 'langfuse-worker'` ✅

### Required Environment Variables
- Bot path: `TELEGRAM_BOT_TOKEN`, `LITELLM_MASTER_KEY`, provider keys (`CEREBRAS_API_KEY`/`GROQ_API_KEY`/`OPENAI_API_KEY`) — correctly documented in `DOCKER.md` and `docs/LOCAL-DEVELOPMENT.md`.
- ML profile: `NEXTAUTH_SECRET`, `SALT`, `ENCRYPTION_KEY` — correctly documented.
- Alert delivery: `TELEGRAM_ALERTING_BOT_TOKEN`, `TELEGRAM_ALERTING_CHAT_ID` — correctly documented.
- Voice path: `LIVEKIT_API_KEY`/`LIVEKIT_API_SECRET`, `ELEVENLABS_API_KEY` — correctly documented.

### K3s Images
- `ghcr.io/yastman/rag-bot`, `rag-ingestion`, `rag-docling`, `rag-user-base`, `rag-bge-m3` — listed in `DOCKER.md` and confirmed in `Makefile:k3s-push-%`.

### Service READMEs
- `services/README.md`, `services/bge-m3-api/README.md`, `services/user-base/README.md`, `services/docling/README.md` all correctly list service names, ports, health endpoints, test files, and owner boundaries.
- Test files referenced in service READMEs exist on disk (`tests/unit/test_bge_m3_endpoints.py`, `tests/unit/test_bge_m3_rerank.py`, `tests/unit/test_docker_static_validation.py`, `tests/unit/test_userbase_endpoints.py`, `tests/unit/test_userbase_dockerfile_permissions.py`, `tests/unit/test_dockerfile_python_abi.py`, `tests/smoke/test_zoo_smoke.py`).

### Local Development Flow
- `docs/LOCAL-DEVELOPMENT.md` bootstrap, service start, validation, development gates, and minimal stack commands all match `Makefile` targets and Compose contracts.
- Python runtime note (3.13 in Docker vs 3.11+ native) is accurate.

### LiteLLM Routing
- `docs/runbooks/LITEllm_FAILURE.md` primary/fallback model table matches `docker/litellm/config.yaml` exactly (`gpt-4o-mini` → `cerebras/zai-glm-4.7`, fallbacks to `cerebras-oss`, `groq`, `openai`).

### Qdrant Troubleshooting
- Collection name `gdrive_documents_bge`, port `6333`, volume `qdrant_data` → `dev_qdrant_data`, memory limit `1G` — all match `compose.yml`.

### Redis Troubleshooting
- `test-redis-password` matches `tests/fixtures/compose.ci.env:REDIS_PASSWORD=test-redis-password`.
- `maxmemory-policy volatile-lfu` and `maxmemory-samples 10` match `compose.yml` and `compose.dev.yml`.

---

## Recommendations

1. **Fix P1 blockers first** — Alertmanager port, LiteLLM endpoint alignment, container-exec commands with missing tools, and PostgreSQL WAL recovery path/image mismatches directly break documented workflows.
2. **Standardize runbook front-matter** — Add `Last verified` and `Verification command` to `POSTGRESQL_WAL_RECOVERY.md` and `vps-gdrive-ingestion-recovery.md`.
3. **Standardize Compose invocation** — All runbooks should use the deterministic `COMPOSE_PROJECT_NAME=dev docker compose --env-file tests/fixtures/compose.ci.env -f compose.yml -f compose.dev.yml` prefix or explicitly note the `.env` requirement.
4. **Deduplicate Makefile targets** — Pick one observability target (`monitoring-up` or `docker-obs-up`) and alias the other.
5. **Complete the Service Endpoints table** — Add Mini App API (`8090`) and Frontend (`8091`) to `DOCKER.md`.

---

## Appendix A — Commands Run

```bash
# Keyword sweep
rg -n "services:|profiles:|container_name|ports:|healthcheck|LANGFUSE|LITELLM|REDIS|QDRANT|POSTGRES|bge-m3|user-base" compose.yml compose.dev.yml DOCKER.md docs/LOCAL-DEVELOPMENT.md docs/runbooks services

# Default service set
COMPOSE_DISABLE_ENV_FILE=1 docker compose --env-file tests/fixtures/compose.ci.env -f compose.yml -f compose.dev.yml --compatibility config --services

# Link check
make docs-check

# Git whitespace check
git diff --check

# Image tool probes
docker run --rm qdrant/qdrant:v1.17.1 sh -c "which curl || echo 'curl not found'"
grep -n "redis-cli\|curl\|wget" telegram_bot/Dockerfile
```

## Appendix B — Reserved Files

- `docs/audits/2026-05-08-runtime-runbooks-audit.md`

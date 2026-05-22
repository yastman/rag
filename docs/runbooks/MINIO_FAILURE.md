# Runbook: MinIO Storage Failure

> **Related docs:**
> - [Docker Services Reference](../../DOCKER.md) -- service definitions and resource limits
> - [Alerting Overview](../ALERTING.md) -- alert routing and notification channels
> - [Coverage Matrix](COVERAGE_MATRIX.md) -- alert-to-runbook mapping

> **Owner:** Infrastructure & Observability
> **Last verified:** 2026-05-12
> **Verification command:**
> ```bash
> COMPOSE_PROJECT_NAME=dev docker compose --env-file tests/fixtures/compose.ci.env -f compose.yml -f compose.dev.yml exec minio sh -c 'curl -sf http://localhost:9000/minio/health/live || exit 1'
> ```

Use this runbook when **MinIO service issues** affect Langfuse event and media
storage (container failures, disk exhaustion, data corruption, healing errors).
MinIO provides S3-compatible object storage exclusively for Langfuse v3 in this
stack.

## Symptoms

- Langfuse unable to persist event uploads or media attachments
- `MinioDown` alert firing (no logs from `dev-minio` container)
- `MinioDiskFull` alert firing (disk full or drive offline messages)
- `MinioCorruption` alert firing (corruption, AccessDenied, or signature mismatch)
- `MinioHealingFailed` alert firing (drive initialization or healing failures)
- `MinioError` alert firing (elevated error/exception rate in MinIO logs)
- Langfuse UI showing missing traces, media, or upload errors

## Service / Container Map

| Compose service | Typical container names | Notes |
|---|---|---|
| `minio` | `dev-minio-1` (Compose v2+), `dev_minio_1` (legacy) | S3-compatible storage for Langfuse event/media uploads |
| `langfuse-server` | `dev-langfuse-server-1` | Primary consumer of MinIO via `LANGFUSE_S3_EVENT_UPLOAD_ENDPOINT` |
| `langfuse-worker` | `dev-langfuse-worker-1` | Async worker that writes events to MinIO |

> MinIO is pinned to `minio/minio:RELEASE.2025-09-07T16-13-09Z` in `compose.yml`.
> The service stores data in the `minio_data` Docker volume at `/data`.
> Langfuse connects to MinIO at `http://minio:9000` using `MINIO_ROOT_USER` / `MINIO_ROOT_PASSWORD`.

## Fast-Path Diagnosis (read-only)

Run these commands before deciding whether the issue is a service failure or a
configuration problem.

### 1. Container health and reachability

```bash
# Check service status
COMPOSE_PROJECT_NAME=dev docker compose --env-file tests/fixtures/compose.ci.env -f compose.yml -f compose.dev.yml ps minio

# Test MinIO liveness from inside the container
COMPOSE_PROJECT_NAME=dev docker compose --env-file tests/fixtures/compose.ci.env -f compose.yml -f compose.dev.yml exec minio sh -c 'curl -sf http://localhost:9000/minio/health/live && echo OK'
```

Expected: `OK`.
If this fails, treat as **service failure** (container down, network partition,
or resource exhaustion).

### 2. Disk usage inspection

```bash
# Check volume disk usage from the container
COMPOSE_PROJECT_NAME=dev docker compose --env-file tests/fixtures/compose.ci.env -f compose.yml -f compose.dev.yml exec minio sh -c 'df -h /data'

# List bucket contents
COMPOSE_PROJECT_NAME=dev docker compose --env-file tests/fixtures/compose.ci.env -f compose.yml -f compose.dev.yml exec minio sh -c 'ls -la /data/langfuse/'
```

Look for:
- Filesystem usage approaching 100% (confirms `MinioDiskFull`)
- Missing or corrupted directories under `/data/langfuse/`

### 3. Logs

```bash
COMPOSE_PROJECT_NAME=dev docker compose --env-file tests/fixtures/compose.ci.env -f compose.yml -f compose.dev.yml logs minio --tail=200
```

Check for: disk full messages, corruption errors, healing failures, auth errors,
repeated exceptions.

### 4. Langfuse connectivity to MinIO

```bash
# Check Langfuse logs for S3/MinIO errors
COMPOSE_PROJECT_NAME=dev docker compose --env-file tests/fixtures/compose.ci.env -f compose.yml -f compose.dev.yml logs langfuse-server --tail=100 | grep -i "s3\|minio\|upload"
```

## Alert-Specific Resolution

> **Caution:** Commands below mutate state. Run only after fast-path diagnosis
> confirms the root cause.

---

### MinioDown

**Trigger:** No logs from `dev-minio` container for 5 minutes.

**Diagnosis:**
```bash
COMPOSE_PROJECT_NAME=dev docker compose --env-file tests/fixtures/compose.ci.env -f compose.yml -f compose.dev.yml ps minio
docker inspect dev-minio-1 --format '{{.State.Status}} {{.State.ExitCode}}'
```

**Resolution:**

```bash
# 1. Restart the MinIO container
COMPOSE_PROJECT_NAME=dev docker compose --env-file tests/fixtures/compose.ci.env -f compose.yml -f compose.dev.yml restart minio

# 2. Verify liveness after restart
COMPOSE_PROJECT_NAME=dev docker compose --env-file tests/fixtures/compose.ci.env -f compose.yml -f compose.dev.yml exec minio sh -c 'curl -sf http://localhost:9000/minio/health/live && echo OK'

# 3. Confirm Langfuse can reach MinIO
COMPOSE_PROJECT_NAME=dev docker compose --env-file tests/fixtures/compose.ci.env -f compose.yml -f compose.dev.yml logs langfuse-server --tail=20 | grep -i "s3\|minio"
```

If container keeps crashing, check OOM kills:
```bash
docker inspect dev-minio-1 --format '{{.State.OOMKilled}}'
```

If OOM-killed, increase the memory limit in `compose.yml` (currently 256M).

---

### MinioDiskFull

**Trigger:** MinIO logs contain `disk full`, `no space left`, or `drive offline` messages.

**Diagnosis:**
```bash
COMPOSE_PROJECT_NAME=dev docker compose --env-file tests/fixtures/compose.ci.env -f compose.yml -f compose.dev.yml exec minio sh -c 'df -h /data'
docker system df
```

**Resolution:**

```bash
# 1. Check what is consuming space
COMPOSE_PROJECT_NAME=dev docker compose --env-file tests/fixtures/compose.ci.env -f compose.yml -f compose.dev.yml exec minio sh -c 'du -sh /data/*'

# 2. Prune old or orphaned data (if safe -- verify with team first)
# Option A: Clean unused Docker resources on the host
docker system prune --volumes -f

# Option B: Remove old event data if retention policy allows
COMPOSE_PROJECT_NAME=dev docker compose --env-file tests/fixtures/compose.ci.env -f compose.yml -f compose.dev.yml exec minio sh -c 'find /data/langfuse/events -mtime +30 -delete'

# 3. Restart MinIO after freeing space
COMPOSE_PROJECT_NAME=dev docker compose --env-file tests/fixtures/compose.ci.env -f compose.yml -f compose.dev.yml restart minio
```

For persistent disk pressure, expand the underlying host volume or move the
Docker volume to a larger disk.

---

### MinioCorruption

**Trigger:** MinIO logs contain `corrupt`, `AccessDenied`, or `signature mismatch` messages.

**Diagnosis:**
```bash
# Check for corruption-related log entries
COMPOSE_PROJECT_NAME=dev docker compose --env-file tests/fixtures/compose.ci.env -f compose.yml -f compose.dev.yml logs minio --tail=300 | grep -iE "corrupt|AccessDenied|signature"
```

**Resolution:**

For **AccessDenied / signature mismatch** (auth issue):
```bash
# 1. Verify credentials match between .env and compose
grep MINIO_ROOT_PASSWORD .env
grep LANGFUSE_S3_EVENT_UPLOAD_SECRET_ACCESS_KEY .env

# 2. Restart both MinIO and Langfuse to pick up corrected env
COMPOSE_PROJECT_NAME=dev docker compose --env-file tests/fixtures/compose.ci.env -f compose.yml -f compose.dev.yml restart minio langfuse-server langfuse-worker
```

For **data corruption**:
```bash
# 1. Stop MinIO
COMPOSE_PROJECT_NAME=dev docker compose --env-file tests/fixtures/compose.ci.env -f compose.yml -f compose.dev.yml stop minio

# 2. Back up the volume before any destructive action
docker run --rm -v dev_minio_data:/data -v $(pwd):/backup alpine tar czf /backup/minio_data_backup.tar.gz /data

# 3. Restart MinIO (it will attempt self-healing on startup)
COMPOSE_PROJECT_NAME=dev docker compose --env-file tests/fixtures/compose.ci.env -f compose.yml -f compose.dev.yml up -d minio
```

If corruption is unrecoverable, recreate the volume (data loss):
```bash
COMPOSE_PROJECT_NAME=dev docker compose --env-file tests/fixtures/compose.ci.env -f compose.yml -f compose.dev.yml down -v minio
COMPOSE_PROJECT_NAME=dev docker compose --env-file tests/fixtures/compose.ci.env -f compose.yml -f compose.dev.yml up -d minio
```

---

### MinioHealingFailed

**Trigger:** MinIO logs contain `failed to initialize`, `unable to use drive`, or `healing.*failed` messages for 3+ minutes.

**Diagnosis:**
```bash
COMPOSE_PROJECT_NAME=dev docker compose --env-file tests/fixtures/compose.ci.env -f compose.yml -f compose.dev.yml logs minio --tail=300 | grep -iE "heal|initialize|unable to use"
```

**Resolution:**

```bash
# 1. Stop MinIO
COMPOSE_PROJECT_NAME=dev docker compose --env-file tests/fixtures/compose.ci.env -f compose.yml -f compose.dev.yml stop minio

# 2. Check for filesystem issues on the volume
docker run --rm -v dev_minio_data:/data alpine sh -c 'ls -la /data && df -h /data'

# 3. Remove lock files or temporary healing artifacts if present
docker run --rm -v dev_minio_data:/data alpine sh -c 'find /data -name "*.lock" -delete 2>/dev/null; find /data/.minio.sys -name "*.tmp" -delete 2>/dev/null'

# 4. Restart MinIO
COMPOSE_PROJECT_NAME=dev docker compose --env-file tests/fixtures/compose.ci.env -f compose.yml -f compose.dev.yml up -d minio

# 5. Monitor logs for successful initialization
COMPOSE_PROJECT_NAME=dev docker compose --env-file tests/fixtures/compose.ci.env -f compose.yml -f compose.dev.yml logs minio -f --tail=50
```

If healing continues to fail after cleanup, the volume may need to be recreated
(see MinioCorruption resolution above).

---

### MinioError

**Trigger:** More than 5 error/exception log lines within a 5-minute window, sustained for 5 minutes.

**Diagnosis:**
```bash
# Inspect recent errors
COMPOSE_PROJECT_NAME=dev docker compose --env-file tests/fixtures/compose.ci.env -f compose.yml -f compose.dev.yml logs minio --tail=300 | grep -iE "error|exception"

# Check container resource usage
docker stats dev-minio-1 --no-stream
```

**Resolution:**

1. Identify the error pattern (auth, disk, network, or application-level).
2. Follow the specific alert resolution above that matches the error class.
3. If errors are transient and self-resolving, monitor for 10 minutes before acting.
4. For repeated generic errors with no clear cause:

```bash
# Restart MinIO
COMPOSE_PROJECT_NAME=dev docker compose --env-file tests/fixtures/compose.ci.env -f compose.yml -f compose.dev.yml restart minio

# Verify health
COMPOSE_PROJECT_NAME=dev docker compose --env-file tests/fixtures/compose.ci.env -f compose.yml -f compose.dev.yml exec minio sh -c 'curl -sf http://localhost:9000/minio/health/live && echo OK'
```

## Escalation / Rollback

| Condition | Action |
|---|---|
| MinIO stays down after restart | Check host disk, memory, and Docker daemon health |
| Corruption unrecoverable | Recreate volume (Langfuse loses historical event/media data) |
| Repeated OOM kills | Increase memory limit in `compose.yml` beyond 256M |
| Langfuse still failing after MinIO recovery | Restart `langfuse-server` and `langfuse-worker` |
| Issue persists after all steps | Escalate to infrastructure team with full logs attached |

## Impact on Users

When MinIO is down, the system degrades as follows:

- **Langfuse event uploads fail** -- traces and observations may be lost or delayed
- **Media attachments unavailable** -- uploaded files in Langfuse UI will not render
- **RAG pipeline unaffected** -- MinIO is not in the bot query/response path
- **Bot remains operational** -- end users still get responses normally

MinIO failure is isolated to observability and tracing data persistence.

## Prevention

- Monitor disk usage on the Docker host and MinIO volume
- Set up alerting thresholds below 80% disk utilization
- Implement a retention policy for old Langfuse events
- Keep the MinIO image up to date for security and bug fixes
- Ensure `MINIO_ROOT_PASSWORD` is consistent across `.env`, `compose.yml`, and `compose.dev.yml`

## Source Paths

| Component | Path |
|---|---|
| MinIO service definition | [`compose.yml`](../../compose.yml) |
| Dev overrides (ports, passwords) | [`compose.dev.yml`](../../compose.dev.yml) |
| VPS overrides | [`compose.vps.yml`](../../compose.vps.yml) |
| Alert rules | [`docker/monitoring/rules/extended-services.yaml`](../../docker/monitoring/rules/extended-services.yaml) |
| CI env fixture | [`tests/fixtures/compose.ci.env`](../../tests/fixtures/compose.ci.env) |

## Logs and Artifacts

| Artifact | Location / command |
|---|---|
| Runtime logs | `docker compose logs minio --tail=200` |
| MinIO data volume | `minio_data` (inspect with `docker volume inspect dev_minio_data`) |
| Healthcheck status | `docker inspect dev-minio-1 --format '{{.State.Health.Status}}'` |
| MinIO console (dev) | `http://127.0.0.1:9091` (credentials: `minio` / `MINIO_ROOT_PASSWORD`) |

## See Also

- [Langfuse Tracing Gaps](LANGFUSE_TRACING_GAPS.md)
- [LiteLLM Failure](LITEllm_FAILURE.md)
- [Docker Services Reference](../../DOCKER.md)
- [Coverage Matrix](COVERAGE_MATRIX.md)

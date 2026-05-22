# Runbook: MinIO Failure

> **Related docs:**
> - [Docker Services Reference](../../DOCKER.md) -- compose service definitions and resource limits
> - [Alerting Configuration](../ALERTING.md) -- Prometheus/Loki alert rules overview

> **Owner:** Infrastructure & Observability
> **Last verified:** 2026-05-12
> **Verification command:**
> ```bash
> COMPOSE_PROJECT_NAME=dev docker compose --env-file tests/fixtures/compose.ci.env -f compose.yml -f compose.dev.yml exec minio sh -c 'curl -sf http://localhost:9000/minio/health/live'
> ```

Use this runbook when **MinIO alerts fire** or Langfuse reports S3 storage
errors. MinIO provides S3-compatible object storage for Langfuse v3 (event
uploads, media uploads). When MinIO is unavailable, Langfuse cannot persist
trace media or event batches.

## Alerts Covered

| Alert | Severity | Trigger |
|-------|----------|---------|
| `MinioDown` | critical | No logs from `dev-minio` for 5 minutes |
| `MinioDiskFull` | critical | Disk full, no space left, or drive offline messages |
| `MinioCorruption` | critical | Corruption, AccessDenied, or signature mismatch errors |
| `MinioHealingFailed` | warning | Drive initialization or healing failures |
| `MinioError` | warning | More than 5 error/exception log lines in 5 minutes |

## Symptoms

- Langfuse UI shows upload failures or missing media attachments
- `MinioDown` alert fires with no container logs visible
- `MinioDiskFull` alert fires when the host or volume runs out of space
- `MinioCorruption` alert fires on data integrity or authentication failures
- `MinioHealingFailed` alert fires when MinIO cannot initialize or repair drives
- `MinioError` alert fires on sustained error output in container logs
- Langfuse trace uploads fail with S3-related errors in Langfuse worker logs

## Service / Container Map

| Compose service | Typical container names | Notes |
|---|---|---|
| `minio` | `dev-minio-1` (Compose v2+), `dev_minio_1` (legacy) | S3-compatible storage for Langfuse event and media uploads |
| `langfuse-server` | `dev-langfuse-server-1` | Primary consumer of MinIO storage |
| `langfuse-worker` | `dev-langfuse-worker-1` | Background worker that writes to MinIO |

> MinIO is pinned to `minio/minio:RELEASE.2025-09-07T16-13-09Z` in compose.
> The data volume is `minio_data` mounted at `/data` inside the container.
> The `langfuse` bucket is auto-created on startup via the entrypoint command.

## Fast-Path Diagnosis (read-only)

Run these commands before deciding whether the issue is a service failure,
disk problem, or authentication error.

### 1. Container health and reachability

```bash
# Check service status
COMPOSE_PROJECT_NAME=dev docker compose --env-file tests/fixtures/compose.ci.env -f compose.yml -f compose.dev.yml ps minio

# Test MinIO health endpoint from inside the container
COMPOSE_PROJECT_NAME=dev docker compose --env-file tests/fixtures/compose.ci.env -f compose.yml -f compose.dev.yml exec minio sh -c 'curl -sf http://localhost:9000/minio/health/live && echo OK'
```

Expected: `OK`.
If this fails, treat as **service failure** (container down, startup crash, or
resource exhaustion).

### 2. Disk usage inspection

```bash
# Check disk usage inside MinIO data volume
COMPOSE_PROJECT_NAME=dev docker compose --env-file tests/fixtures/compose.ci.env -f compose.yml -f compose.dev.yml exec minio sh -c 'df -h /data'

# Check volume size on host
docker volume inspect dev_minio_data --format '{{ .Mountpoint }}' | xargs sudo du -sh
```

Look for:
- `/data` filesystem usage above 90% -- confirms disk pressure
- Filesystem at 100% -- confirms `MinioDiskFull` alert

### 3. Authentication check

```bash
# Verify credentials are set
COMPOSE_PROJECT_NAME=dev docker compose --env-file tests/fixtures/compose.ci.env -f compose.yml -f compose.dev.yml exec minio sh -c 'echo "User: $MINIO_ROOT_USER"'
```

If `MINIO_ROOT_USER` is empty or does not match what Langfuse expects
(`LANGFUSE_S3_EVENT_UPLOAD_ACCESS_KEY_ID`), this is an auth mismatch.

### 4. Logs

```bash
COMPOSE_PROJECT_NAME=dev docker compose --env-file tests/fixtures/compose.ci.env -f compose.yml -f compose.dev.yml logs minio --tail=200
```

Check for: disk full messages, corruption warnings, healing failures,
`AccessDenied` errors, startup crashes.

## Service Failure vs Configuration Bug

| Observation | Interpretation | Next step |
|---|---|---|
| Health endpoint fails, container not running | Service failure | Restart container |
| Health endpoint fails, container running but crash-looping | Startup failure | Check logs for init errors, disk issues |
| Health endpoint OK, Langfuse shows `AccessDenied` | Auth mismatch | Verify `MINIO_ROOT_PASSWORD` matches Langfuse env vars |
| Health endpoint OK, Langfuse shows `SignatureDoesNotMatch` | Auth mismatch | Credentials drifted between `.env` and running container |
| `disk full` or `no space left` in logs | Disk pressure | Free space or expand volume |
| `corrupt` or `healing.*failed` in logs | Data corruption | Check volume integrity, consider data reset |
| Sustained generic errors but service responds | Transient issues | Monitor; check upstream Langfuse request patterns |

## Remediation

> **Caution:** Commands below mutate state. Run only after fast-path diagnosis
> confirms the issue.

### MinioDown -- Container Not Running

```bash
# 1. Check container status
COMPOSE_PROJECT_NAME=dev docker compose --env-file tests/fixtures/compose.ci.env -f compose.yml -f compose.dev.yml ps minio

# 2. Restart MinIO
COMPOSE_PROJECT_NAME=dev docker compose --env-file tests/fixtures/compose.ci.env -f compose.yml -f compose.dev.yml up -d minio

# 3. Verify health
COMPOSE_PROJECT_NAME=dev docker compose --env-file tests/fixtures/compose.ci.env -f compose.yml -f compose.dev.yml exec minio sh -c 'curl -sf http://localhost:9000/minio/health/live && echo OK'
```

If the container keeps crash-looping, check resource limits (256M memory cap in
compose) and logs for OOM or startup failures.

### MinioDiskFull -- Storage Exhaustion

```bash
# 1. Confirm disk usage
COMPOSE_PROJECT_NAME=dev docker compose --env-file tests/fixtures/compose.ci.env -f compose.yml -f compose.dev.yml exec minio sh -c 'df -h /data'

# 2. List large objects in the data directory
COMPOSE_PROJECT_NAME=dev docker compose --env-file tests/fixtures/compose.ci.env -f compose.yml -f compose.dev.yml exec minio sh -c 'du -sh /data/* | sort -rh | head -10'

# 3. If safe, remove old/orphaned data (e.g., Langfuse event batches older than retention)
# WARNING: Only do this if you understand what data is stored
COMPOSE_PROJECT_NAME=dev docker compose --env-file tests/fixtures/compose.ci.env -f compose.yml -f compose.dev.yml exec minio sh -c 'find /data/langfuse -type f -mtime +30 | head -20'
```

For persistent disk pressure:
- Increase the volume size on the host
- Configure Langfuse lifecycle/retention policies to limit stored data
- Move to a larger disk or external S3 provider

### MinioCorruption -- Data Integrity or Auth Errors

**Authentication issues:**

```bash
# Verify the password in the running container matches .env
COMPOSE_PROJECT_NAME=dev docker compose --env-file tests/fixtures/compose.ci.env -f compose.yml -f compose.dev.yml exec minio sh -c 'echo "MINIO_ROOT_USER=$MINIO_ROOT_USER"'

# Compare with Langfuse env (should match LANGFUSE_S3_EVENT_UPLOAD_ACCESS_KEY_ID)
COMPOSE_PROJECT_NAME=dev docker compose --env-file tests/fixtures/compose.ci.env -f compose.yml -f compose.dev.yml exec langfuse-server sh -c 'echo "S3_KEY=$LANGFUSE_S3_EVENT_UPLOAD_ACCESS_KEY_ID"'
```

If credentials drifted, update `.env` and recreate both services:

```bash
COMPOSE_PROJECT_NAME=dev docker compose --env-file tests/fixtures/compose.ci.env -f compose.yml -f compose.dev.yml up -d minio langfuse-server langfuse-worker
```

**Data corruption:**

If MinIO reports actual data corruption (not auth):

```bash
# Stop the service
COMPOSE_PROJECT_NAME=dev docker compose --env-file tests/fixtures/compose.ci.env -f compose.yml -f compose.dev.yml stop minio

# Back up current data
docker run --rm -v dev_minio_data:/data -v /tmp:/backup alpine tar czf /backup/minio_data_backup.tar.gz /data

# Remove corrupted volume and recreate (DATA LOSS - last resort)
COMPOSE_PROJECT_NAME=dev docker compose --env-file tests/fixtures/compose.ci.env -f compose.yml -f compose.dev.yml down minio
docker volume rm dev_minio_data
COMPOSE_PROJECT_NAME=dev docker compose --env-file tests/fixtures/compose.ci.env -f compose.yml -f compose.dev.yml up -d minio
```

> Langfuse will recreate the bucket on next write. Historical media and event
> data will be lost -- this is acceptable for dev environments only.

### MinioHealingFailed -- Drive Init Failures

Healing failures usually indicate underlying volume or filesystem problems:

```bash
# 1. Check logs for the specific healing error
COMPOSE_PROJECT_NAME=dev docker compose --env-file tests/fixtures/compose.ci.env -f compose.yml -f compose.dev.yml logs minio --tail=50 | grep -i "heal\|init\|drive"

# 2. Restart to trigger re-initialization
COMPOSE_PROJECT_NAME=dev docker compose --env-file tests/fixtures/compose.ci.env -f compose.yml -f compose.dev.yml restart minio

# 3. If restart does not resolve, recreate with fresh volume
COMPOSE_PROJECT_NAME=dev docker compose --env-file tests/fixtures/compose.ci.env -f compose.yml -f compose.dev.yml down minio
docker volume rm dev_minio_data
COMPOSE_PROJECT_NAME=dev docker compose --env-file tests/fixtures/compose.ci.env -f compose.yml -f compose.dev.yml up -d minio
```

### MinioError -- Sustained Error Output

Usually transient. If sustained:

```bash
# 1. Review recent errors
COMPOSE_PROJECT_NAME=dev docker compose --env-file tests/fixtures/compose.ci.env -f compose.yml -f compose.dev.yml logs minio --tail=100 | grep -i "error\|exception"

# 2. Restart if errors are crash-related
COMPOSE_PROJECT_NAME=dev docker compose --env-file tests/fixtures/compose.ci.env -f compose.yml -f compose.dev.yml restart minio

# 3. Check memory usage (256M limit)
docker stats --no-stream --format "table {{.Name}}\t{{.MemUsage}}\t{{.MemPerc}}" | grep minio
```

If errors correlate with memory pressure, consider increasing the memory limit
in `compose.yml` (current: 256M).

## Impact on Users

MinIO is **not** in the direct user-facing request path. Its failure impacts:

- **Langfuse media uploads** -- trace attachments (screenshots, audio) will fail
  to persist. Traces themselves (stored in ClickHouse/Postgres) are unaffected.
- **Langfuse event batches** -- large event payloads offloaded to S3 will fail.
  Langfuse may queue and retry, or drop events depending on configuration.
- **No impact on bot responses** -- the Telegram bot, RAG pipeline, Redis cache,
  and Qdrant are entirely independent of MinIO.

## Prevention

- Monitor disk usage on the host volume backing `minio_data`
- Set up log-based alerting (already configured in `extended-services.yaml`)
- Keep MinIO image pinned and update only with tested releases
- For production, use an external S3 provider instead of self-hosted MinIO
- Review Langfuse retention settings to prevent unbounded storage growth

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
| MinIO console (dev) | `http://127.0.0.1:9091` (credentials: `minio` / `MINIO_ROOT_PASSWORD`) |
| Health endpoint | `http://localhost:9000/minio/health/live` (from inside container) |

## See Also

- [Langfuse Tracing Gaps](LANGFUSE_TRACING_GAPS.md)
- [Redis Cache Degradation](REDIS_CACHE_DEGRADATION.md)
- [Docker Services Reference](../../DOCKER.md)
- [Alert-to-Runbook Coverage Matrix](COVERAGE_MATRIX.md)

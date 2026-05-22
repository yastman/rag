# Runbook: MinIO Storage Failure

> **Related docs:**
> - [Langfuse Tracing Gaps](LANGFUSE_TRACING_GAPS.md) -- Langfuse depends on MinIO for event and media storage
> - [Docker Services Reference](../../DOCKER.md) -- full Compose service definitions and resource limits

> **Owner:** Platform & Observability
> **Last verified:** 2025-01-15
> **Verification command:**
> ```bash
> COMPOSE_PROJECT_NAME=dev docker compose --env-file tests/fixtures/compose.ci.env -f compose.yml -f compose.dev.yml exec minio sh -c 'curl -sf http://localhost:9000/minio/health/live'
> ```

Use this runbook when **MinIO S3-compatible storage** experiences service
failures, disk issues, data corruption, or healing problems. MinIO provides
object storage for the Langfuse observability stack (event uploads and media
storage). When MinIO is down, Langfuse cannot persist trace data or media
artifacts.

## Symptoms

- Langfuse UI shows missing traces or media attachments
- `langfuse-worker` logs report S3 upload failures
- MinIO healthcheck failing (`curl` to `/minio/health/live` returns non-200)
- Disk space alerts on the Docker host
- `AccessDenied` or `signature mismatch` errors in MinIO or Langfuse logs

## Service / Container Map

| Compose service | Typical container names | Notes |
|---|---|---|
| `minio` | `dev-minio-1` (Compose v2+), `dev_minio_1` (legacy) | S3-compatible storage for Langfuse events and media |
| `langfuse-worker` | `dev-langfuse-worker-1`, `dev_langfuse_worker_1` | Primary consumer of MinIO -- writes event and media objects |
| `langfuse` | `dev-langfuse-1`, `dev_langfuse_1` | Web UI reads media from MinIO via presigned URLs |

> MinIO is pinned to **RELEASE.2025-09-07T16-13-09Z** in compose.
> The `langfuse` bucket is auto-created on startup via the entrypoint command:
> `mkdir -p /data/langfuse && minio server --address ":9000" --console-address ":9001" /data`

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
If this fails, treat as **service failure** (container down, crash loop, or
entrypoint error).

### 2. Disk usage inspection

```bash
# Check volume usage from host
docker system df -v | grep minio

# Check disk usage inside the container
COMPOSE_PROJECT_NAME=dev docker compose --env-file tests/fixtures/compose.ci.env -f compose.yml -f compose.dev.yml exec minio sh -c 'df -h /data'
```

Look for:
- `/data` filesystem usage above 85% -- indicates disk pressure
- Volume size relative to `deploy.resources.limits.memory` (256M) in [`compose.yml`](../../compose.yml)

### 3. Bucket and object listing

```bash
# List bucket contents (top-level prefixes)
COMPOSE_PROJECT_NAME=dev docker compose --env-file tests/fixtures/compose.ci.env -f compose.yml -f compose.dev.yml exec minio sh -c 'ls -la /data/langfuse/'
```

Expected: `events/` and `media/` directories present.

### 4. Logs

```bash
COMPOSE_PROJECT_NAME=dev docker compose --env-file tests/fixtures/compose.ci.env -f compose.yml -f compose.dev.yml logs minio --tail=200
```

Check for: `disk full`, `drive offline`, `corrupt`, `AccessDenied`,
`signature mismatch`, `healing failed`, `unable to use drive`.

### 5. Downstream impact (Langfuse worker)

```bash
COMPOSE_PROJECT_NAME=dev docker compose --env-file tests/fixtures/compose.ci.env -f compose.yml -f compose.dev.yml logs langfuse-worker --tail=100 | grep -i "s3\|minio\|upload\|error"
```

Look for: repeated S3 upload errors, connection refused, or timeout messages.

## Remediation

> **Caution:** Commands below mutate state. Run only after fast-path diagnosis
> confirms the root cause.

### MinioDown -- Container not running

```bash
# 1. Check container status and exit code
COMPOSE_PROJECT_NAME=dev docker compose --env-file tests/fixtures/compose.ci.env -f compose.yml -f compose.dev.yml ps minio

# 2. If exited, check logs for crash reason
COMPOSE_PROJECT_NAME=dev docker compose --env-file tests/fixtures/compose.ci.env -f compose.yml -f compose.dev.yml logs minio --tail=50

# 3. Restart MinIO
COMPOSE_PROJECT_NAME=dev docker compose --env-file tests/fixtures/compose.ci.env -f compose.yml -f compose.dev.yml restart minio

# 4. Verify health after restart
COMPOSE_PROJECT_NAME=dev docker compose --env-file tests/fixtures/compose.ci.env -f compose.yml -f compose.dev.yml exec minio sh -c 'curl -sf http://localhost:9000/minio/health/live && echo OK'
```

If MinIO keeps crash-looping, check for volume corruption (see MinioCorruption
below) or entrypoint errors.

### MinioDiskFull -- Storage exhausted

```bash
# 1. Identify large objects
COMPOSE_PROJECT_NAME=dev docker compose --env-file tests/fixtures/compose.ci.env -f compose.yml -f compose.dev.yml exec minio sh -c 'du -sh /data/langfuse/events/ /data/langfuse/media/ 2>/dev/null'

# 2. Remove old event data (if safe -- events older than retention window)
COMPOSE_PROJECT_NAME=dev docker compose --env-file tests/fixtures/compose.ci.env -f compose.yml -f compose.dev.yml exec minio sh -c 'find /data/langfuse/events -type f -mtime +30 -delete'

# 3. Verify free space
COMPOSE_PROJECT_NAME=dev docker compose --env-file tests/fixtures/compose.ci.env -f compose.yml -f compose.dev.yml exec minio sh -c 'df -h /data'
```

For persistent disk pressure:
- Increase the Docker volume size on the host
- Add a lifecycle policy via `mc ilm` (MinIO Client) to auto-expire old objects
- Consider moving to a larger disk or external S3

### MinioCorruption -- Data integrity or auth errors

```bash
# 1. Verify credentials match between MinIO and Langfuse
COMPOSE_PROJECT_NAME=dev docker compose --env-file tests/fixtures/compose.ci.env -f compose.yml -f compose.dev.yml exec minio sh -c 'echo "MINIO_ROOT_USER=$MINIO_ROOT_USER"'

# 2. Check langfuse-worker S3 config (should use same credentials)
COMPOSE_PROJECT_NAME=dev docker compose --env-file tests/fixtures/compose.ci.env -f compose.yml -f compose.dev.yml exec langfuse-worker sh -c 'echo "S3_KEY=$LANGFUSE_S3_EVENT_UPLOAD_ACCESS_KEY_ID S3_ENDPOINT=$LANGFUSE_S3_EVENT_UPLOAD_ENDPOINT"'

# 3. If data is actually corrupt, recreate the bucket
COMPOSE_PROJECT_NAME=dev docker compose --env-file tests/fixtures/compose.ci.env -f compose.yml -f compose.dev.yml stop minio
docker volume rm dev_minio_data
COMPOSE_PROJECT_NAME=dev docker compose --env-file tests/fixtures/compose.ci.env -f compose.yml -f compose.dev.yml up -d minio
```

> **Warning:** Removing `minio_data` volume destroys all stored events and media.
> Only do this if data is unrecoverable and you accept losing historical Langfuse
> artifacts.

If the issue is `AccessDenied` or `signature mismatch`:
- Verify `MINIO_ROOT_PASSWORD` in `.env` matches the value used by `langfuse-worker`
  (env var `LANGFUSE_S3_EVENT_UPLOAD_SECRET_ACCESS_KEY`)
- After changing credentials, restart both `minio` and `langfuse-worker`

### MinioHealingFailed -- Drive initialization problems

```bash
# 1. Check for drive errors in logs
COMPOSE_PROJECT_NAME=dev docker compose --env-file tests/fixtures/compose.ci.env -f compose.yml -f compose.dev.yml logs minio --tail=100 | grep -i "heal\|drive\|initialize"

# 2. Verify volume mount integrity
docker volume inspect dev_minio_data

# 3. Restart with a clean state if healing cannot complete
COMPOSE_PROJECT_NAME=dev docker compose --env-file tests/fixtures/compose.ci.env -f compose.yml -f compose.dev.yml restart minio
```

If healing continues to fail after restart:
- Check host filesystem for I/O errors (`dmesg | grep -i "error\|i/o"`)
- Recreate the volume (see MinioCorruption section above)

### MinioError -- Generic errors in logs

```bash
# 1. Get recent error context
COMPOSE_PROJECT_NAME=dev docker compose --env-file tests/fixtures/compose.ci.env -f compose.yml -f compose.dev.yml logs minio --tail=200 | grep -i "error\|exception"

# 2. Check resource limits
COMPOSE_PROJECT_NAME=dev docker compose --env-file tests/fixtures/compose.ci.env -f compose.yml -f compose.dev.yml exec minio sh -c 'cat /sys/fs/cgroup/memory.max 2>/dev/null || cat /sys/fs/cgroup/memory/memory.limit_in_bytes 2>/dev/null'

# 3. Restart if errors are transient
COMPOSE_PROJECT_NAME=dev docker compose --env-file tests/fixtures/compose.ci.env -f compose.yml -f compose.dev.yml restart minio
```

If errors persist, check if the memory limit (256M) is sufficient for the
current workload and increase it in `compose.yml` or `compose.dev.yml`.

## Impact on Users

When MinIO is down, the system degrades as follows:

- **Langfuse event storage fails** -- new traces and spans cannot be persisted to S3; the worker queues them in Redis but eventually drops data
- **Langfuse media uploads fail** -- audio, images, and attachments linked to traces are lost
- **Langfuse UI shows gaps** -- historical traces missing media or event details
- **No direct impact on bot or RAG pipeline** -- MinIO only backs the observability stack; user-facing queries continue unaffected

## Prevention

- Monitor disk usage on the `minio_data` volume; alert at 80% capacity
- Set up object lifecycle rules to auto-expire events older than the retention window
- Keep `MINIO_ROOT_PASSWORD` in sync across `.env` and all consuming services
- Periodically verify MinIO health via the Docker healthcheck endpoint
- Review Langfuse worker logs weekly for intermittent S3 errors

## Source Paths

| Component | Path |
|---|---|
| MinIO service definition | [`compose.yml`](../../compose.yml) |
| Dev overrides | [`compose.dev.yml`](../../compose.dev.yml) |
| Alert rules | [`docker/monitoring/rules/extended-services.yaml`](../../docker/monitoring/rules/extended-services.yaml) |
| CI env fixture | [`tests/fixtures/compose.ci.env`](../../tests/fixtures/compose.ci.env) |
| Langfuse S3 config | `LANGFUSE_S3_*` env vars in [`compose.yml`](../../compose.yml) (langfuse-worker service) |

## Logs and Artifacts

| Artifact | Location / command |
|---|---|
| MinIO runtime logs | `docker compose logs minio --tail=200` |
| MinIO data volume | `minio_data` (inspect with `docker volume inspect dev_minio_data`) |
| MinIO console (dev) | `http://localhost:9001` (credentials: `minio` / `$MINIO_ROOT_PASSWORD`) |
| Langfuse worker S3 errors | `docker compose logs langfuse-worker --tail=100 \| grep -i s3` |

## See Also

- [Langfuse Tracing Gaps](LANGFUSE_TRACING_GAPS.md)
- [Redis Cache Degradation](REDIS_CACHE_DEGRADATION.md)
- [Docker Services Reference](../../DOCKER.md)
- [Local Development Guide](../LOCAL-DEVELOPMENT.md)

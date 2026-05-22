# Runbook: MinIO Storage Failure

> **Owner:** Langfuse storage / S3-compatible bucket on-call
> **Last verified:** 2026-05-22
> **Verification command:**
> ```bash
> curl -fsS http://localhost:9000/minio/health/ready
> ```

Use this runbook when MinIO alerts fire from `docker/monitoring/rules/extended-services.yaml`. MinIO backs Langfuse blob storage; its outages typically appear as Langfuse upload errors first.

## Covered Alerts

| Alert | Severity | Source |
|---|---|---|
| `MinioDown` | critical | [`extended-services.yaml`](../../docker/monitoring/rules/extended-services.yaml) |
| `MinioDiskFull` | critical | [`extended-services.yaml`](../../docker/monitoring/rules/extended-services.yaml) |
| `MinioCorruption` | critical | [`extended-services.yaml`](../../docker/monitoring/rules/extended-services.yaml) |
| `MinioHealingFailed` | warning | [`extended-services.yaml`](../../docker/monitoring/rules/extended-services.yaml) |
| `MinioError` | warning | [`extended-services.yaml`](../../docker/monitoring/rules/extended-services.yaml) |

## Service / Container Map

| Compose service | Typical container names |
|---|---|
| `minio` | `dev-minio-1`, `dev_minio_1` |

> Endpoints, ports, profiles: [`DOCKER.md`](../../DOCKER.md). Local dev: [`docs/LOCAL-DEVELOPMENT.md`](../LOCAL-DEVELOPMENT.md).

## Fast-Path Diagnosis (read-only)

### 1. Container state

```bash
COMPOSE_PROJECT_NAME=dev docker compose --env-file tests/fixtures/compose.ci.env -f compose.yml -f compose.dev.yml ps minio
docker inspect dev-minio-1 --format '
  Name={{.Name}}
  Status={{.State.Status}}
  OOMKilled={{.State.OOMKilled}}
  ExitCode={{.State.ExitCode}}
  Restarts={{.RestartCount}}
'
```

### 2. Health endpoints

```bash
# Liveness (host-side dev mapping)
curl -fsS http://localhost:9000/minio/health/live
# Readiness — must be 200 to accept writes
curl -fsS http://localhost:9000/minio/health/ready
```

### 3. Bounded log slice

```bash
COMPOSE_PROJECT_NAME=dev docker compose --env-file tests/fixtures/compose.ci.env -f compose.yml -f compose.dev.yml logs minio --tail=200
```

Pattern → alert mapping:

| Pattern (case-insensitive) | Alert |
|---|---|
| no logs for 5m | `MinioDown` |
| `disk full`, `no space left`, `drive offline` | `MinioDiskFull` |
| `corrupt`, `AccessDenied`, `signature mismatch` | `MinioCorruption` |
| `failed to initialize`, `unable to use drive`, `healing.*failed` | `MinioHealingFailed` |
| `error`, `exception` (rate based) | `MinioError` |

### 4. Disk usage

```bash
COMPOSE_PROJECT_NAME=dev docker compose --env-file tests/fixtures/compose.ci.env -f compose.yml -f compose.dev.yml exec minio df -h /data || true
docker volume inspect dev_minio_data || docker volume inspect dev-minio-data
```

### 5. Bucket reachability from Langfuse

```bash
COMPOSE_PROJECT_NAME=dev docker compose --env-file tests/fixtures/compose.ci.env -f compose.yml -f compose.dev.yml exec langfuse-worker wget -qO- http://minio:9000/minio/health/ready
```

If MinIO is healthy from the host but unreachable from inside the network, treat as a service-mesh / DNS issue.

## Service Failure vs App Bug

| Observation | Interpretation | Next step |
|---|---|---|
| `MinioDiskFull` with high object count | Service failure (capacity) | Free space / extend volume; rotate Langfuse blob retention |
| `MinioCorruption` with `AccessDenied` | Auth contract drift | Check Langfuse `S3_*` env vs MinIO root credentials (presence only) |
| `MinioCorruption` with `corrupt` keyword | Service failure (data) | Stop service, snapshot volume, run MinIO healing |
| `MinioHealingFailed` after host disk swap | Service failure | Verify drive mount UID/GID; restart MinIO once mounts are correct |
| `MinioError` with `slow downloads` | App bug / capacity | Check network throughput; consider node placement |
| `MinioDown` while host disk is fine | Service failure (process) | `docker compose up -d --force-recreate minio` and capture last 200 log lines first |

## Source Paths

| Component | Path |
|---|---|
| Compose definitions | [`compose.yml`](../../compose.yml), [`compose.dev.yml`](../../compose.dev.yml) |
| Alert rules | [`docker/monitoring/rules/extended-services.yaml`](../../docker/monitoring/rules/extended-services.yaml) |
| Langfuse storage env contract | env vars `LANGFUSE_S3_*` (see [`compose.dev.yml`](../../compose.dev.yml); never echo values) |
| Langfuse runbook for downstream effects | [`LANGFUSE_TRACING_GAPS.md`](LANGFUSE_TRACING_GAPS.md) |

## Logs and Artifacts

| Artifact | Location / command |
|---|---|
| Runtime logs | `docker compose logs minio --tail=200` |
| Volume metadata | `docker volume inspect dev_minio_data` |
| Object counts | MinIO `mc admin info` from a sidecar (do not run mutating commands) |
| Langfuse worker logs | `docker compose logs langfuse-worker --tail=200` |

## Remediation

> ⚠️ **Caution:** Mutating commands. Run only after fast-path diagnosis confirms the issue.

### `MinioDown`

1. Inspect exit reason and last 200 log lines.
2. Recreate only the MinIO container:
   ```bash
   COMPOSE_PROJECT_NAME=dev docker compose --env-file tests/fixtures/compose.ci.env -f compose.yml -f compose.dev.yml up -d --force-recreate minio
   ```

### `MinioDiskFull`

1. Capture object counts per bucket before deletion.
2. Trim Langfuse blob retention according to product policy; do not bulk-delete buckets blindly.
3. Extend the volume / move data to a larger disk if growth is organic.

### `MinioCorruption`

1. Halt writes if possible (set Langfuse `S3_*` to read-only mode or stop the worker).
2. Snapshot the MinIO data volume.
3. Run MinIO healing per the upstream MinIO runbook (`mc admin heal`).
4. Restore from snapshot if healing fails.

### `MinioHealingFailed`

1. Inspect mount permissions / disk SMART status.
2. Re-bind correct UID/GID, restart only after the underlying drive is verified.
3. Engage storage on-call before touching production data.

### `MinioError`

1. Look for repeated error classes in the last 50 lines.
2. Apply the matching fix (auth, throughput, network) before restart.

## Prevention

- Cap Langfuse blob retention in production (avoid unbounded growth).
- Keep MinIO data volume on a disk with ≥ 20% headroom.
- Pin MinIO image tags via Renovate; verify compatibility before bumping major versions.
- Watch `MinioError` rate as an early signal before `MinioDown` fires.

## See Also

- [`LANGFUSE_TRACING_GAPS.md`](LANGFUSE_TRACING_GAPS.md)
- [`POSTGRESQL_WAL_RECOVERY.md`](POSTGRESQL_WAL_RECOVERY.md)
- [`DOCKER.md`](../../DOCKER.md)

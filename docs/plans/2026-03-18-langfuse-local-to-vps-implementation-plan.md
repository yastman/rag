# Langfuse Local-To-VPS Migration Implementation Plan

> **For Codex:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Replace the VPS Langfuse transactional and object-storage state with the canonical local Langfuse state, keep a rollback path, realign the VPS app credentials, and leave a redacted execution report.

**Architecture:** Treat this as an ops migration runbook, not a feature branch refactor. Langfuse v3 in this repo stores transactional state in PostgreSQL, object/media payloads in MinIO, and analytics traces in ClickHouse; the migration must replace only PostgreSQL `langfuse` plus MinIO object data while keeping ClickHouse untouched. Use the existing Docker Compose topology and VPS connection contract already defined in the repo instead of inventing a parallel deployment flow.

**Tech Stack:** Docker Compose, PostgreSQL, MinIO, Langfuse v3, SSH, Bash, gzip, tar, Python 3.12

---

## Preflight

Run this plan from a dedicated worktree and an operator shell that already has SSH access to the VPS.

References to read before Task 1:

- `compose.yml:449-589`
- `compose.vps.yml:1-19`
- `scripts/deploy-vps.sh:24-118`
- `scripts/test_release_health_vps.sh:1-132`
- `.env.example:51-62`
- `.env.example:129-132`
- `docker/postgres/init/00-init-databases.sql:1-8`

Official Langfuse guidance already checked:

- Langfuse self-hosted docs: Postgres is the primary transactional database.
- Langfuse self-hosted docs: S3-compatible object storage persists uploaded events and media.
- Langfuse self-hosted docs: ClickHouse stores traces, observations, and scores, so it must not be replaced in this migration.

Suggested shell setup:

```bash
cd /home/user/projects/rag-fresh
export LOCAL_REPO=/home/user/projects/rag-fresh
export LOCAL_COMPOSE_FILE=compose.yml:compose.dev.yml
export VPS_HOST=95.111.252.29
export VPS_PORT=1654
export VPS_USER=admin
export VPS_KEY="$HOME/.ssh/vps_access_key"
export VPS_DIR=/opt/rag-fresh
export VPS_COMPOSE_FILE=compose.yml:compose.vps.yml
export MIGRATION_TS="$(date -u +%Y%m%dT%H%M%SZ)"
export ARTIFACT_DIR="$LOCAL_REPO/.artifacts/langfuse-migration/$MIGRATION_TS"
mkdir -p "$ARTIFACT_DIR"
```

Baseline commands:

```bash
COMPOSE_FILE="$LOCAL_COMPOSE_FILE" docker compose ps postgres minio redis-langfuse langfuse-worker langfuse
ssh -i "$VPS_KEY" -p "$VPS_PORT" "$VPS_USER@$VPS_HOST" \
  "cd $VPS_DIR && export COMPOSE_FILE=$VPS_COMPOSE_FILE && docker compose ps postgres minio redis-langfuse clickhouse langfuse-worker langfuse"
```

Expected: both local and VPS Langfuse stacks are reachable enough to enumerate services before any backup or restore begins.

## Task 1: Preflight Inventory And Redacted Report Skeleton

**Files:**
- Create: `docs/plans/2026-03-23-langfuse-local-to-vps-migration-report.md`
- Reference: `scripts/deploy-vps.sh:24-118`
- Reference: `scripts/test_release_health_vps.sh:1-132`
- Reference: `.env.example:51-62`

**Step 1: Create the redacted report skeleton**

Create the report file with these headings:

```markdown
# Langfuse Local-To-VPS Migration Report

- Timestamp (UTC):
- Operator:
- Local commit:
- VPS target:
- Local backup artifacts:
- VPS backup artifacts:
- Local keys rotated to VPS:
- Validation results:
- Rollback status:
- Notes:
```

**Step 2: Record repo and environment fingerprints without secrets**

Run:

```bash
git rev-parse HEAD
COMPOSE_FILE="$LOCAL_COMPOSE_FILE" docker compose ps --format json
ssh -i "$VPS_KEY" -p "$VPS_PORT" "$VPS_USER@$VPS_HOST" \
  "cd $VPS_DIR && export COMPOSE_FILE=$VPS_COMPOSE_FILE && docker compose ps --format json"
```

Expected: report captures commit SHA, container names, and service status only.

**Step 3: Snapshot the redacted env contract on the VPS**

Run:

```bash
ssh -i "$VPS_KEY" -p "$VPS_PORT" "$VPS_USER@$VPS_HOST" \
  "python3 - <<'PY'
from pathlib import Path
keys = {
    'POSTGRES_PASSWORD',
    'NEXTAUTH_SECRET',
    'SALT',
    'ENCRYPTION_KEY',
    'CLICKHOUSE_PASSWORD',
    'MINIO_ROOT_PASSWORD',
    'LANGFUSE_REDIS_PASSWORD',
    'LANGFUSE_PUBLIC_KEY',
    'LANGFUSE_SECRET_KEY',
    'LANGFUSE_HOST',
}
for line in Path('/opt/rag-fresh/.env').read_text().splitlines():
    if not line or line.lstrip().startswith('#') or '=' not in line:
        continue
    key, _, value = line.partition('=')
    if key in keys:
        print(f'{key}=[set]' if value else f'{key}=[missing]')
PY"
```

Expected: the report shows which required values are set before migration, without writing any secret material.

**Step 4: Verify rollback storage exists on both sides**

Run:

```bash
mkdir -p "$ARTIFACT_DIR"/{local,vps}
ssh -i "$VPS_KEY" -p "$VPS_PORT" "$VPS_USER@$VPS_HOST" "mkdir -p $VPS_DIR/backups/langfuse-migration/$MIGRATION_TS"
```

Expected: both local and VPS backup directories exist before any destructive step begins.

## Task 2: Backup Current VPS Langfuse PostgreSQL And MinIO State

**Files:**
- Reference: `compose.yml:473-589`
- Reference: `compose.vps.yml:1-19`
- Update: `docs/plans/2026-03-23-langfuse-local-to-vps-migration-report.md`

**Step 1: Create a compressed backup of the VPS `langfuse` PostgreSQL database**

Run:

```bash
ssh -i "$VPS_KEY" -p "$VPS_PORT" "$VPS_USER@$VPS_HOST" \
  "cd $VPS_DIR && export COMPOSE_FILE=$VPS_COMPOSE_FILE && \
   docker compose exec -T postgres pg_dump -U postgres langfuse | gzip > backups/langfuse-migration/$MIGRATION_TS/vps-langfuse.sql.gz"
```

Expected: `vps-langfuse.sql.gz` exists on the VPS and has non-zero size.

**Step 2: Capture the VPS MinIO data volume as a tarball**

Run:

```bash
ssh -i "$VPS_KEY" -p "$VPS_PORT" "$VPS_USER@$VPS_HOST" \
  "cd $VPS_DIR && export COMPOSE_FILE=$VPS_COMPOSE_FILE && \
   docker run --rm \
     --volumes-from \$(docker compose ps -q minio) \
     -v $VPS_DIR/backups/langfuse-migration/$MIGRATION_TS:/backup \
     alpine sh -lc 'cd /data && tar czf /backup/vps-minio-data.tar.gz .'"
```

Expected: `vps-minio-data.tar.gz` exists on the VPS and is the rollback artifact for object storage.

**Step 3: Pull a local copy of the VPS rollback artifacts**

Run:

```bash
scp -i "$VPS_KEY" -P "$VPS_PORT" \
  "$VPS_USER@$VPS_HOST:$VPS_DIR/backups/langfuse-migration/$MIGRATION_TS/vps-langfuse.sql.gz" \
  "$ARTIFACT_DIR/vps/"
scp -i "$VPS_KEY" -P "$VPS_PORT" \
  "$VPS_USER@$VPS_HOST:$VPS_DIR/backups/langfuse-migration/$MIGRATION_TS/vps-minio-data.tar.gz" \
  "$ARTIFACT_DIR/vps/"
```

Expected: rollback artifacts now exist in both locations.

**Step 4: Record artifact names and sizes in the report**

Run:

```bash
ls -lh "$ARTIFACT_DIR/vps"
ssh -i "$VPS_KEY" -p "$VPS_PORT" "$VPS_USER@$VPS_HOST" \
  "ls -lh $VPS_DIR/backups/langfuse-migration/$MIGRATION_TS"
```

Expected: report includes size and path for both VPS rollback artifacts.

## Task 3: Export Canonical Local Langfuse PostgreSQL And MinIO State

**Files:**
- Reference: `compose.dev.yml:72-108`
- Reference: `docker/postgres/init/00-init-databases.sql:1-8`
- Update: `docs/plans/2026-03-23-langfuse-local-to-vps-migration-report.md`

**Step 1: Export the local `langfuse` PostgreSQL database**

Run:

```bash
cd "$LOCAL_REPO"
COMPOSE_FILE="$LOCAL_COMPOSE_FILE" \
  docker compose exec -T postgres pg_dump -U postgres langfuse | gzip > "$ARTIFACT_DIR/local/local-langfuse.sql.gz"
```

Expected: `local-langfuse.sql.gz` exists and is non-zero.

**Step 2: Export the local MinIO volume as a tarball**

Run:

```bash
cd "$LOCAL_REPO"
COMPOSE_FILE="$LOCAL_COMPOSE_FILE" \
  docker run --rm \
    --volumes-from "$(docker compose ps -q minio)" \
    -v "$ARTIFACT_DIR/local:/backup" \
    alpine sh -lc 'cd /data && tar czf /backup/local-minio-data.tar.gz .'
```

Expected: `local-minio-data.tar.gz` exists and will become the source of truth for VPS object storage.

**Step 3: Record local credential contract without revealing values**

Run:

```bash
python3 - <<'PY'
from pathlib import Path
keys = ('LANGFUSE_PUBLIC_KEY', 'LANGFUSE_SECRET_KEY', 'LANGFUSE_HOST')
for line in Path('.env').read_text().splitlines():
    if '=' not in line:
        continue
    key, _, value = line.partition('=')
    if key in keys:
        print(f'{key}=[set]' if value else f'{key}=[missing]')
PY
```

Expected: report confirms the local canonical Langfuse key set that the VPS app env must match after restore.

**Step 4: Copy the canonical local artifacts to the VPS**

Run:

```bash
scp -i "$VPS_KEY" -P "$VPS_PORT" \
  "$ARTIFACT_DIR/local/local-langfuse.sql.gz" \
  "$VPS_USER@$VPS_HOST:$VPS_DIR/backups/langfuse-migration/$MIGRATION_TS/"
scp -i "$VPS_KEY" -P "$VPS_PORT" \
  "$ARTIFACT_DIR/local/local-minio-data.tar.gz" \
  "$VPS_USER@$VPS_HOST:$VPS_DIR/backups/langfuse-migration/$MIGRATION_TS/"
```

Expected: the VPS now has both canonical local restore artifacts staged.

## Task 4: Replace VPS PostgreSQL And MinIO State Without Touching ClickHouse

**Files:**
- Reference: `compose.yml:449-589`
- Update: `docs/plans/2026-03-23-langfuse-local-to-vps-migration-report.md`

**Step 1: Stop services that write traces or depend on Langfuse keys**

Run:

```bash
ssh -i "$VPS_KEY" -p "$VPS_PORT" "$VPS_USER@$VPS_HOST" \
  "cd $VPS_DIR && export COMPOSE_FILE=$VPS_COMPOSE_FILE && \
   docker compose stop bot litellm rag-api voice-agent mini-app-api ingestion langfuse langfuse-worker"
```

Expected: writers are paused before the state swap begins.

**Step 2: Restore the VPS PostgreSQL `langfuse` database from the local canonical dump**

Run:

```bash
ssh -i "$VPS_KEY" -p "$VPS_PORT" "$VPS_USER@$VPS_HOST" \
  "cd $VPS_DIR && export COMPOSE_FILE=$VPS_COMPOSE_FILE && \
   docker compose exec -T postgres psql -U postgres postgres -c \"SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = 'langfuse' AND pid <> pg_backend_pid();\" && \
   docker compose exec -T postgres dropdb -U postgres --if-exists langfuse && \
   docker compose exec -T postgres createdb -U postgres langfuse"
ssh -i "$VPS_KEY" -p "$VPS_PORT" "$VPS_USER@$VPS_HOST" \
  "cd $VPS_DIR && export COMPOSE_FILE=$VPS_COMPOSE_FILE && \
   gunzip -c backups/langfuse-migration/$MIGRATION_TS/local-langfuse.sql.gz | docker compose exec -T postgres psql -U postgres langfuse"
```

Expected: restore finishes without SQL errors and `langfuse` now contains the local canonical transactional state.

**Step 3: Restore the VPS MinIO data volume from the local canonical archive**

Run:

```bash
ssh -i "$VPS_KEY" -p "$VPS_PORT" "$VPS_USER@$VPS_HOST" \
  "cd $VPS_DIR && export COMPOSE_FILE=$VPS_COMPOSE_FILE && docker compose stop minio"
ssh -i "$VPS_KEY" -p "$VPS_PORT" "$VPS_USER@$VPS_HOST" \
  "cd $VPS_DIR && export COMPOSE_FILE=$VPS_COMPOSE_FILE && \
   docker run --rm --volumes-from \$(docker compose ps -q minio) alpine sh -lc 'rm -rf /data/*'"
ssh -i "$VPS_KEY" -p "$VPS_PORT" "$VPS_USER@$VPS_HOST" \
  "cd $VPS_DIR && export COMPOSE_FILE=$VPS_COMPOSE_FILE && \
   docker run --rm \
     --volumes-from \$(docker compose ps -q minio) \
     -v $VPS_DIR/backups/langfuse-migration/$MIGRATION_TS:/restore \
     alpine sh -lc 'cd /data && tar xzf /restore/local-minio-data.tar.gz'"
```

Expected: the VPS MinIO backing volume now matches the local canonical object store archive.

**Step 4: Restart only the Langfuse storage and app services**

Run:

```bash
ssh -i "$VPS_KEY" -p "$VPS_PORT" "$VPS_USER@$VPS_HOST" \
  "cd $VPS_DIR && export COMPOSE_FILE=$VPS_COMPOSE_FILE && \
   docker compose up -d postgres minio redis-langfuse clickhouse langfuse-worker langfuse"
```

Expected: Postgres, MinIO, Redis, ClickHouse, worker, and web return to healthy state. ClickHouse is restarted only as a dependency surface, not restored.

## Task 5: Realign VPS Bot Credentials And Validate End-To-End

**Files:**
- Reference: `.env.example:129-132`
- Reference: `scripts/test_release_health_vps.sh:1-132`
- Update: `docs/plans/2026-03-23-langfuse-local-to-vps-migration-report.md`

**Step 1: Update VPS `.env` so app credentials match the migrated local Langfuse instance**

Run:

```bash
python3 - <<'PY' > "$ARTIFACT_DIR/local/langfuse-app.env"
from pathlib import Path
wanted = {"LANGFUSE_PUBLIC_KEY", "LANGFUSE_SECRET_KEY", "LANGFUSE_HOST"}
for line in Path(".env").read_text().splitlines():
    if "=" not in line:
        continue
    key, _, value = line.partition("=")
    if key in wanted:
        print(f"{key}={value}")
PY

scp -i "$VPS_KEY" -P "$VPS_PORT" \
  "$ARTIFACT_DIR/local/langfuse-app.env" \
  "$VPS_USER@$VPS_HOST:$VPS_DIR/backups/langfuse-migration/$MIGRATION_TS/"

ssh -i "$VPS_KEY" -p "$VPS_PORT" "$VPS_USER@$VPS_HOST" \
  "python3 - <<'PY'
from pathlib import Path
env_path = Path('/opt/rag-fresh/.env')
incoming = Path('/opt/rag-fresh/backups/langfuse-migration/$MIGRATION_TS/langfuse-app.env')
updates = {}
for line in incoming.read_text().splitlines():
    if '=' in line:
        key, _, value = line.partition('=')
        updates[key] = value
lines = env_path.read_text().splitlines()
out = []
seen = set()
for line in lines:
    if '=' not in line or line.lstrip().startswith('#'):
        out.append(line)
        continue
    key, _, _ = line.partition('=')
    if key in updates:
        out.append(f'{key}={updates[key]}')
        seen.add(key)
    else:
        out.append(line)
for key, value in updates.items():
    if key not in seen:
        out.append(f'{key}={value}')
env_path.write_text('\\n'.join(out) + '\\n')
PY"
```

Expected: only the Langfuse app-facing keys are changed on the VPS; secrets are never committed to the repo.

**Step 2: Restart the app services that emit traces**

Run:

```bash
ssh -i "$VPS_KEY" -p "$VPS_PORT" "$VPS_USER@$VPS_HOST" \
  "cd $VPS_DIR && export COMPOSE_FILE=$VPS_COMPOSE_FILE && \
   docker compose up -d bot litellm rag-api voice-agent mini-app-api ingestion"
```

Expected: writer services come back with the new Langfuse key pair.

**Step 3: Run VPS release smoke and Langfuse health validation**

Run:

```bash
ssh -i "$VPS_KEY" -p "$VPS_PORT" "$VPS_USER@$VPS_HOST" \
  "cd $VPS_DIR && export COMPOSE_FILE=$VPS_COMPOSE_FILE && ./scripts/test_release_health_vps.sh"
ssh -i "$VPS_KEY" -p "$VPS_PORT" "$VPS_USER@$VPS_HOST" \
  "curl -fsS http://127.0.0.1:3001/api/public/health >/dev/null"
```

Expected: release smoke passes and the Langfuse public health endpoint returns success.

**Step 4: Verify the app containers see the Langfuse env contract**

Run:

```bash
ssh -i "$VPS_KEY" -p "$VPS_PORT" "$VPS_USER@$VPS_HOST" \
  "cd $VPS_DIR && export COMPOSE_FILE=$VPS_COMPOSE_FILE && \
   docker compose exec -T bot python - <<'PY'
import os
for key in ('LANGFUSE_PUBLIC_KEY', 'LANGFUSE_SECRET_KEY', 'LANGFUSE_HOST'):
    value = os.getenv(key, '')
    print(f'{key}=[set]' if value else f'{key}=[missing]')
PY"
```

Expected: bot runtime now points at the migrated Langfuse instance with a fully populated env contract.

## Task 6: Final Verification, Rollback Decision, And Issue Update

**Files:**
- Update: `docs/plans/2026-03-23-langfuse-local-to-vps-migration-report.md`

**Step 1: Record validation evidence in the redacted report**

Include:

- artifact paths and sizes
- `docker compose ps` snapshot after restore
- result of `./scripts/test_release_health_vps.sh`
- `curl` health status for Langfuse
- whether rollback artifacts were retained on both local and VPS storage

**Step 2: Keep rollback artifacts until manual sign-off**

Do not delete:

```text
$ARTIFACT_DIR/vps/vps-langfuse.sql.gz
$ARTIFACT_DIR/vps/vps-minio-data.tar.gz
$VPS_DIR/backups/langfuse-migration/$MIGRATION_TS/vps-langfuse.sql.gz
$VPS_DIR/backups/langfuse-migration/$MIGRATION_TS/vps-minio-data.tar.gz
```

Expected: rollback remains possible after the migration window.

**Step 3: Comment on `#1003` with redacted outcome**

Comment should include:

- migration timestamp
- PR or commit SHA for the plan/report
- smoke status
- rollback artifact retention status
- note that ClickHouse was not restored by design

**Step 4: Commit only the redacted report and plan artifact**

Run:

```bash
git add docs/plans/2026-03-18-langfuse-local-to-vps-implementation-plan.md docs/plans/2026-03-23-langfuse-local-to-vps-migration-report.md
git commit -m "docs: add langfuse local-to-vps migration runbook"
```

Expected: the repo records only the runbook/report, never secrets, SQL dumps, or MinIO archives.

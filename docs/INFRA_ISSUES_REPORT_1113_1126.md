# Infrastructure Issues Report: #1113–#1126

**Reviewed:** April 2026
**Reviewed by:** infra-researcher

---

## Summary Table

| # | Title | Severity | Complexity | Files to Change |
|---|-------|----------|------------|-----------------|
| 1113 | No backup strategy for Postgres, Qdrant, Langfuse | CRITICAL | HIGH | New: `scripts/backup-*.sh`, `k8s/base/backup/` |
| 1114 | `_DEFAULT_RERANK_TOP_K=3` too restrictive | LOW | LOW | *(has-PR, search issue — not infra)* |
| 1115 | Hardcoded postgres credentials in k8s DB URLs | HIGH | LOW | `k8s/base/bot/deployment.yaml`, `k8s/base/ingestion/deployment.yaml` |
| 1116 | k8s secrets .env.example missing 10+ variables | MEDIUM | LOW | `k8s/secrets/.env.example` |
| 1117 | Postgres: no memory limit, no CPU limit, no startupProbe | MEDIUM | LOW | `k8s/base/postgres/deployment.yaml`, `k8s/base/redis/deployment.yaml` |
| 1118 | No PodDisruptionBudgets for any stateful deployment | MEDIUM | LOW | `k8s/base/postgres/pdb.yaml`, `k8s/base/redis/pdb.yaml`, `k8s/base/qdrant/pdb.yaml`, `k8s/base/bge-m3/pdb.yaml` |
| 1119 | Promtail filters `dev-*` blind on VPS `vps-` prefix | MEDIUM | LOW | `docker/monitoring/promtail.yaml` |
| 1120 | k8s bge-m3 `OMP_NUM_THREADS=2` vs compose `=4` | LOW | LOW | `k8s/base/bge-m3/deployment.yaml` |
| 1121 | k8s ingestion hardcodes `/home/admin/drive-sync` hostPath | MEDIUM | MEDIUM | `k8s/base/ingestion/deployment.yaml` |
| 1122 | No Prometheus metrics endpoint — monitoring incomplete | MEDIUM | HIGH | `telegram_bot/`, `services/*/Dockerfile`, `k8s/base/` |
| 1123 | Monitoring stack absent from Kubernetes overlays | MEDIUM | HIGH | New: `k8s/overlays/monitoring/`, new base files |
| 1124 | LiveKit server API key mismatch | MEDIUM | LOW | `docker/livekit/livekit.yaml` or `compose.yml` |
| 1125 | Langfuse stack missing from all k8s overlays | HIGH | HIGH | New: `k8s/base/clickhouse/`, `k8s/base/minio/`, `k8s/base/redis-langfuse/`, `k8s/base/langfuse/`, `k8s/overlays/full/kustomization.yaml` |
| 1126 | Loki 7-day retention with no offsite backup | MEDIUM | MEDIUM | `docker/monitoring/loki.yaml` |

---

## Issue #1113 — No backup strategy for Postgres, Qdrant, Langfuse

**Severity:** CRITICAL
**Complexity:** HIGH
**Files touched:** New files (scripts + k8s manifests)

### Analysis

Verified: there are **zero backup scripts** anywhere in the repository. No cron jobs, no offsite replication. The k3s config enables etcd snapshots for cluster state only — application data volumes are unbacked.

### Verified Data at Risk

| Service | Data | Backup? |
|---------|------|---------|
| PostgreSQL | langfuse, CRM, realestate, cocoindex DBs | **NO** |
| Qdrant | All vector embeddings | **NO** |
| ClickHouse (Langfuse) | Analytics events | **NO** |
| MinIO (Langfuse) | Media uploads, event blobs | **NO** |
| Redis (app) | Session cache | **NO** |
| Redis (langfuse) | Job queues | **NO** |

### Proposed Fix Files

```
scripts/
  backup-postgres.sh       # pg_dump + WAL archiving to MinIO/S3
  backup-qdrant.sh        # qdrant snapshots to attached volume or S3
  backup-minio.sh         # mc mirror to external S3
  backup-clickhouse.sh    # clickhouse-backup tool

k8s/base/backup/
  cronjob-postgres.yaml
  cronjob-qdrant.yaml
  cronjob-minio.yaml
  cronjob-clickhouse.yaml
```

---

## Issue #1114 — `_DEFAULT_RERANK_TOP_K=3` too restrictive

**Severity:** LOW (search/retrieval)
**Complexity:** LOW
**Note:** Labeled `search`, `enhancement`, `optimization`, **has-PR** — this is not an infra issue despite being in the infra range. Likely a mis-sort.

### Files (if applicable)

To be determined by the search/retrieval team.

---

## Issue #1115 — Hardcoded postgres credentials in k8s DB URLs

**Severity:** HIGH
**Complexity:** LOW
**Files:** `k8s/base/bot/deployment.yaml`, `k8s/base/ingestion/deployment.yaml`

### Analysis

The issue description states credentials are hardcoded as `postgres:postgres`, but **actual code inspection shows they are NOT hardcoded**:

```yaml
# bot/deployment.yaml:169-170
- name: REALESTATE_DATABASE_URL
  value: "postgresql://postgres:$(POSTGRES_PASSWORD)@postgres:5432/realestate"

# ingestion/deployment.yaml:64-65
- name: INGESTION_DATABASE_URL
  value: postgresql://postgres:$(POSTGRES_PASSWORD)@postgres:5432/cocoindex
```

The `$(POSTGRES_PASSWORD)` is resolved from the `db-credentials` secret at runtime. However, the **username** `postgres` IS hardcoded and visible in YAML. The real issue here is:
1. The username is exposed in git history (not just the password)
2. This is inconsistent with best-practice secret management

### Actual Fix Needed

The username `postgres` should ideally also come from a secret (or at minimum be documented that it should be parameterized). The issue description may have been partially fixed already, or the reporter misidentified the problem.

### Files to Change

```
k8s/base/bot/deployment.yaml          # username still visible
k8s/base/ingestion/deployment.yaml   # username still visible
```

---

## Issue #1116 — k8s secrets .env.example missing 10+ variables

**Severity:** MEDIUM
**Complexity:** LOW
**Files:** `k8s/secrets/.env.example`

### Analysis

The `.env.example` currently has 12 variables. **Confirmed missing** (used in `compose.yml` but not in k8s secrets):

| Missing Variable | Used By |
|-----------------|---------|
| `ANTHROPIC_API_KEY` | litellm, bot |
| `CLICKHOUSE_PASSWORD` | langfuse, langfuse-worker |
| `MINIO_ROOT_PASSWORD` | langfuse-worker, langfuse |
| `LANGFUSE_REDIS_PASSWORD` | langfuse, langfuse-worker |
| `NEXTAUTH_SECRET` | langfuse |
| `SALT` | langfuse |
| `ENCRYPTION_KEY` | langfuse |
| `LIVEKIT_API_KEY` | livekit-sip, voice-agent |
| `LIVEKIT_API_SECRET` | livekit-server, livekit-sip, voice-agent |
| `ELEVENLABS_API_KEY` | voice-agent |
| `QDRANT_API_KEY` | (future use) |

### Files to Change

```
k8s/secrets/.env.example   # Add all 11 missing variables with comments
```

---

## Issue #1117 — Postgres: no memory limit, no CPU limit, no startupProbe

**Severity:** MEDIUM
**Complexity:** LOW
**Files:** `k8s/base/postgres/deployment.yaml`, `k8s/base/redis/deployment.yaml`

### Analysis

**Postgres (confirmed):**
- `resources.limits.memory: 512Mi` — **present** (already fixed since issue filed?)
- `resources.limits.cpu` — **missing** (no CPU limit)
- `startupProbe` — **missing** (pgvector extension loading can take 20-30s)

**Redis (confirmed):**
- `resources.limits.memory: 300Mi` — present
- `startupProbe` — **missing**

The postgres memory limit IS present in the current file (line 41), contradicting the issue description which says "NO memory limit". Either the issue was partially fixed or the description was inaccurate.

### Files to Change

```
k8s/base/postgres/deployment.yaml   # Add: cpu limit (1), startupProbe (pg_isready)
k8s/base/redis/deployment.yaml     # Add: startupProbe (redis-cli ping)
```

---

## Issue #1118 — No PodDisruptionBudgets for any stateful deployment

**Severity:** MEDIUM
**Complexity:** LOW
**Files:** `k8s/base/postgres/pdb.yaml`, `k8s/base/redis/pdb.yaml`, `k8s/base/qdrant/pdb.yaml`, `k8s/base/bge-m3/pdb.yaml`

### Analysis

Verified: no PDBs exist anywhere in `k8s/`. All stateful services run with 1 replica. During node drain, all pods can be terminated simultaneously with zero tolerance.

With `minAvailable: 1` and 1 replica, the PDB prevents all pods from being evicted at once — at most 0 pods can be down (since 1 must remain available).

### Files to Create

```
k8s/base/postgres/pdb.yaml   # minAvailable: 1, selector: app=postgres
k8s/base/redis/pdb.yaml      # minAvailable: 1, selector: app=redis
k8s/base/qdrant/pdb.yaml     # minAvailable: 1, selector: app=qdrant
k8s/base/bge-m3/pdb.yaml     # minAvailable: 1, selector: app=bge-m3
```

Also update `k8s/base/kustomization.yaml` to include the new PDB resources.

---

## Issue #1119 — Promtail filters `dev-*` blind on VPS `vps-` prefix

**Severity:** MEDIUM
**Complexity:** LOW
**Files:** `docker/monitoring/promtail.yaml`

### Analysis

**Confirmed** in `docker/monitoring/promtail.yaml`:
- Line 22-23: `filters: - name: name values: - dev-.*`
- Lines 37-38: `regex: '/dev-(.*)'` for job label extraction
- Lines 40-42: same regex for service label
- Lines 84-86: `static_labels: environment: development, stack: rag-dev`

On VPS, `COMPOSE_PROJECT_NAME=vps` so containers are named `vps-*` not `dev-*`. Promtail will discover **zero containers** on VPS.

Also confirmed: promtail is **not deployed on k3s at all** — only in Docker compose `obs` profile. Issue #1123 covers the k8s monitoring gap.

### Files to Change

```
docker/monitoring/promtail.yaml   # Parameterize prefix via env var, fix static labels
```

---

## Issue #1120 — k8s bge-m3 `OMP_NUM_THREADS=2` vs compose `=4`

**Severity:** LOW
**Complexity:** LOW
**Files:** `k8s/base/bge-m3/deployment.yaml`

### Analysis

**Confirmed:**
- `compose.yml:103-104` — `OMP_NUM_THREADS: ${OMP_NUM_THREADS:-4}`, `MKL_NUM_THREADS: ${OMP_NUM_THREADS:-4}`
- `k8s/base/bge-m3/deployment.yaml:31-34` — both set to `"2"`

This is a ~50% performance gap for embedding inference. Low severity (correctness unaffected) but impacts bot latency.

### Files to Change

```
k8s/base/bge-m3/deployment.yaml   # Change "2" → "4" for both vars
```

---

## Issue #1121 — k8s ingestion hardcodes `/home/admin/drive-sync` hostPath

**Severity:** MEDIUM
**Complexity:** MEDIUM
**Files:** `k8s/base/ingestion/deployment.yaml`

### Analysis

**Confirmed** at `k8s/base/ingestion/deployment.yaml:98-101`:
```yaml
volumes:
  - name: drive-sync
    hostPath:
      path: /home/admin/drive-sync
      type: Directory
```

This path only exists on the current VPS setup. Fresh k3s install will fail ingestion immediately. The issue also applies to `bge-m3` and `user-base` which also use hostPath volumes (but those paths like `/opt/k3s-data/hf-cache` are at least documented).

### Options

1. **Best:** Use a PVC instead of hostPath for portability
2. **Workaround:** Document the path requirement clearly
3. **Minimum:** Make the path configurable via a ConfigMap value

### Files to Change

```
k8s/base/ingestion/deployment.yaml   # Either PVC or ConfigMap parameterization
k8s/base/kustomization.yaml          # Add PVC resource if switching
```

---

## Issue #1122 — No Prometheus metrics endpoint — monitoring incomplete

**Severity:** MEDIUM
**Complexity:** HIGH
**Files:** Multiple — bot code, service Dockerfiles, k8s manifests

### Analysis

**Confirmed:**
1. No `/metrics` endpoint in bot code — `telegram_bot/` has no prometheus-client usage
2. No `/metrics` endpoint in litellm (litellm image has it built-in, but it's not exposed via k8s service)
3. No `prometheus-node-exporter` DaemonSet in k8s overlays
4. No Grafana dashboards
5. No Prometheus alerting rules for SLOs

The current "monitoring" is purely log-based (error keyword detection via Alertmanager).

### Files to Change

```
telegram_bot/src/                    # Add prometheus-client, expose /metrics endpoint
services/*/Dockerfile                # Add prometheus-client to each custom service
k8s/base/litellm/service.yaml        # Add port for metrics (4001)
k8s/base/postgres/                   # Could add postgres_exporter sidecar
k8s/base/qdrant/                     # Could add qdrant_exporter sidecar
New: k8s/base/node-exporter/         # DaemonSet for node metrics
New: k8s/base/prometheus/            # Deployment + ConfigMap for scraping rules
New: k8s/base/grafana/               # Deployment + ConfigMap for dashboards
```

---

## Issue #1123 — Monitoring stack absent from Kubernetes overlays

**Severity:** MEDIUM
**Complexity:** HIGH
**Files:** New `k8s/overlays/monitoring/` + base files

### Analysis

**Confirmed:** Docker compose has `obs` profile with loki, promtail, alertmanager. k8s overlays (`core`, `bot`, `ingest`, `full`) have **none** of these.

**What exists in Docker:**
- loki (log aggregation, port 3100)
- promtail (log scraping, Docker socket)
- alertmanager (alert routing to Telegram, port 9093)

**What is missing from k8s:**
- Loki deployment + service
- Promtail DaemonSet
- Alertmanager deployment + service
- Grafana deployment (optional but recommended)
- prometheus-node-exporter DaemonSet
- Prometheus deployment (optional if usingAlertmanager alone)

### Files to Create

```
k8s/overlays/monitoring/
  kustomization.yaml
  loki/
    deployment.yaml
    service.yaml
  promtail/
    daemonset.yaml
  alertmanager/
    deployment.yaml
    service.yaml
New base files:
  k8s/base/loki/
  k8s/base/promtail/
  k8s/base/alertmanager/
```

---

## Issue #1124 — LiveKit server API key mismatch

**Severity:** MEDIUM
**Complexity:** LOW
**Files:** `docker/livekit/livekit.yaml` or `compose.yml`

### Analysis

**Confirmed:**
- `docker/livekit/livekit.yaml:9` uses `${LIVEKIT_API_SECRET:-secret}` as default
- `compose.yml:736-743` — `livekit-server` has **no `environment:` section**, so `LIVEKIT_API_SECRET` is never passed

Result: the container always uses the hardcoded default `"secret"` even if `LIVEKIT_API_SECRET` is set in the environment.

`livekit-sip` and `voice-agent` both receive `LIVEKIT_API_KEY` and `LIVEKIT_API_SECRET` as env vars (lines 761-762, 803-804 of compose.yml), so they generate correct signatures. But the server thinks the key is `"secret"`.

### Files to Change

```
compose.yml                                 # Add environment: LIVEKIT_API_SECRET to livekit-server
docker/livekit/livekit.yaml                 # Or remove the default, require explicit env var
```

---

## Issue #1125 — Langfuse stack missing from all k8s overlays

**Severity:** HIGH
**Complexity:** HIGH
**Files:** New `k8s/base/clickhouse/`, `k8s/base/minio/`, `k8s/base/redis-langfuse/`, `k8s/base/langfuse/`, `k8s/overlays/full/kustomization.yaml`

### Analysis

**Confirmed:** `k8s/overlays/full/kustomization.yaml` only includes base resources (postgres, redis, qdrant, bge-m3, user-base, litellm, bot). The ML stack is completely absent from k8s.

**Langfuse stack in Docker (`compose.yml`):**
- `clickhouse` — clickhouse/clickhouse-server:26.3 (1536M limit)
- `minio` — minio/minio:RELEASE.2024-12-18 (256M)
- `redis-langfuse` — redis:8.6.2 (128M)
- `langfuse-worker` — langfuse/langfuse-worker:3.163.0 (512M)
- `langfuse` — langfuse/langfuse:3.163.0 (1024M)

This is a **large gap**: issue #1080 (langfuse connection failures) may be unfixable on k3s since langfuse itself isn't deployed there.

### Files to Create

```
k8s/base/clickhouse/
  deployment.yaml
  service.yaml
  pvc.yaml
k8s/base/minio/
  deployment.yaml
  service.yaml
  pvc.yaml
k8s/base/redis-langfuse/
  deployment.yaml
  service.yaml
  pvc.yaml
k8s/base/langfuse/
  deployment.yaml (web)
  deployment.yaml (worker)
  service.yaml
  configmap.yaml
k8s/overlays/full/kustomization.yaml   # Add langfuse stack resources
k8s/secrets/.env.example                 # Add all missing langfuse secrets (see #1116)
```

---

## Issue #1126 — Loki 7-day retention with no offsite backup

**Severity:** MEDIUM
**Complexity:** MEDIUM
**Files:** `docker/monitoring/loki.yaml`

### Analysis

**Confirmed** in `docker/monitoring/loki.yaml`:
- Line 56: `retention_period: 168h` (7 days)
- Line 50: `retention_enabled: true`
- All data stored locally in `loki_data` Docker volume

**Additional issue:** Loki binds to `127.0.0.1:3100` (line 7), meaning logs cannot be scraped by any external service for redundancy.

No backup or replication of Loki data exists. If the Docker volume is corrupted or the VPS disk fails, all historical log data is permanently lost.

### Files to Change

```
docker/monitoring/loki.yaml           # Configure S3/object storage for Loki (AWS S3, MinIO, GCS)
                                     # Or add replication_config for distributed deployment
```

### Also Consider

```
docker/monitoring/promtail.yaml      # Add remote_write target for offsite log shipping
```

---

## Cross-Cutting Observations

1. **No backup infrastructure at all** (#1113, #1126) — the most critical gap. Both are CRITICAL/MEDIUM with no code existing.
2. **Monitoring blindspot on k3s** (#1122, #1123) — the production platform (k3s) has no observability stack.
3. **Secrets management gaps** (#1115, #1116, #1124) — multiple inconsistent approaches to secrets across Docker and k8s.
4. **Inconsistent threading** (#1120) — a simple config sync that will improve bot latency by ~50%.
5. **Langfuse stack completely absent from k8s** (#1125) — a large engineering effort needed to port the full ML stack.
6. **Portability issues** (#1119, #1121) — hardcoded paths/prefixes that work on one environment but not another.

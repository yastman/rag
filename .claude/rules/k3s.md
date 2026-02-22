---
paths: "k8s/**, k3s-*"
---

# k3s Deployment

Single-node k3s on VPS (11 GB RAM, 55 GB disk). Migrating from Docker Compose.

## Architecture

```
WSL2 (dev) ──build──→ docker buildx bake ──save/import──→ VPS k3s
                                                          ├─ Namespace: rag
                                                          ├─ Kustomize base + overlays
                                                          └─ imagePullPolicy: Never
```

## Directory Structure

```
k8s/
├── base/                          # Base manifests
│   ├── kustomization.yaml         # 23 resources, labels
│   ├── namespace.yaml             # Namespace: rag
│   ├── configmaps/                # postgres-init, litellm-config
│   ├── postgres/                  # PVC + Deployment + Service
│   ├── redis/                     # Deployment + Service
│   ├── qdrant/                    # PVC + Deployment + Service
│   ├── docling/                   # PVC + Deployment + Service
│   ├── bge-m3/                    # Deployment + Service (hostPath)
│   ├── user-base/                 # Deployment + Service (hostPath)
│   ├── litellm/                   # Deployment + Service
│   ├── bot/                       # Deployment (5 init containers)
│   └── ingestion/                 # Deployment (replicas: 0)
├── overlays/
│   ├── core/                      # postgres, redis, qdrant (11 resources)
│   ├── bot/                       # core + ML + litellm + bot (19 resources)
│   ├── ingest/                    # core + docling + bge-m3 + ingestion (17 resources)
│   └── full/                      # Everything (23 resources)
├── secrets/
│   └── .env.example               # Template (gitignored .env)
├── images-prepull.txt             # Public images for k3s pre-pull
└── k3s-config.yaml                # Server config template
```

## Makefile Targets

| Target | Purpose |
|--------|---------|
| `make k3s-core` | Deploy core (postgres, redis, qdrant) |
| `make k3s-bot` | Deploy bot stack |
| `make k3s-ingest` | Deploy ingestion stack |
| `make k3s-full` | Deploy all services |
| `make k3s-status` | Pod status |
| `make k3s-logs SVC=bot` | Service logs |
| `make k3s-down` | Delete all resources |
| `make k3s-secrets` | Create k8s secrets from .env |
| `make k3s-push-%` | Transfer image: `make k3s-push-bot` |
| `make k3s-ingest-start` | Scale ingestion to 1 |
| `make k3s-ingest-stop` | Scale ingestion to 0 |

## Building Images

```bash
# Build all custom images
docker compose -f docker-compose.dev.yml build

# Build a single image
docker compose -f docker-compose.dev.yml build bot
```

| Service | Dockerfile |
|---------|-----------|
| bot | `telegram_bot/Dockerfile` |
| bge-m3 | `services/bge-m3-api/Dockerfile` |
| user-base | `services/user-base/Dockerfile` |
| docling | `services/docling/Dockerfile` |
| ingestion | `Dockerfile.ingestion` |
| llm-guard | `services/llm-guard-api/Dockerfile` |
| rag-api | `src/api/Dockerfile` |
| voice-agent | `src/voice/Dockerfile` |

## Image Transfer to VPS

```bash
# Single image
make k3s-push-bot    # docker save | ssh vps 'k3s ctr import'

# Manual (with progress)
docker save rag/bot:latest | pv | ssh vps 'sudo k3s ctr -n k8s.io images import -'
```

## k3s Server Config

**File:** `k8s/k3s-config.yaml` → copy to `/etc/rancher/k3s/config.yaml` before install.

| Setting | Value | Purpose |
|---------|-------|---------|
| secrets-encryption | true | Encrypt secrets at rest |
| eviction-hard | `memory<200Mi` | Protect from OOM |
| eviction-soft | `memory<500Mi` | Graceful eviction |
| container-log-max-size | 10Mi | Log rotation |
| image-gc-high-threshold | 85% | Disk cleanup |
| etcd-snapshot-schedule | `0 */6 * * *` | Backup every 6h |

## Pre-pull Manifest

**File:** `k8s/images-prepull.txt` → copy to `/var/lib/rancher/k3s/agent/images/rag-prepull.txt`

Public images (pgvector, redis, qdrant, litellm, busybox) are pre-pulled at k3s startup.

## Security

All deployments have:
- `seccompProfile: RuntimeDefault` (pod-level)
- `allowPrivilegeEscalation: false` (all containers + init containers)
- `capabilities.drop: ["ALL"]`
- `runAsNonRoot: true` (where applicable — not postgres)

## Resource Requirements (VPS)

| Service | Request | Limit | Notes |
|---------|---------|-------|-------|
| postgres | - | - | 512M via Docker |
| redis | 64Mi/25m | 300Mi | volatile-lfu |
| qdrant | 128Mi/50m | 1Gi | |
| docling | 256Mi/100m | 2Gi | HF models at startup |
| bge-m3 | 512Mi/100m | 4Gi | Largest service |
| user-base | 256Mi/100m | 2Gi | Shared HF cache |
| litellm | 128Mi/50m | 512Mi | |
| bot | 128Mi/50m | 512Mi | |
| ingestion | 128Mi/50m | 512Mi | replicas=0 by default |
| **k3s overhead** | ~1.6Gi | | Control plane |
| **Total** | | ~12.5Gi | VPS has 11Gi |

## LiteLLM ConfigMap Sync

k8s ConfigMap (`k8s/base/configmaps/litellm-config.yaml`) must stay in sync with Docker config (`docker/litellm/config.yaml`). Key params: `max_tokens`, `merge_reasoning_content_in_choices` (required for `gpt-oss-120b` reasoning model). Sync test: `tests/unit/test_litellm_config_sync.py`.

## Kustomize Notes

- Overlays core/bot/ingest use `--load-restrictor=LoadRestrictionsNone` (individual file refs)
- Full overlay references `../../base/` directory (no restriction needed)
- Labels use `labels:` with `includeSelectors: false` (not deprecated `commonLabels`)

## VPS Setup (Phase 1)

```bash
# 1. Install k3s
sudo mkdir -p /etc/rancher/k3s
sudo cp k8s/k3s-config.yaml /etc/rancher/k3s/config.yaml
curl -sfL https://get.k3s.io | sh -

# 2. Pre-pull public images
sudo cp k8s/images-prepull.txt /var/lib/rancher/k3s/agent/images/rag-prepull.txt

# 3. Build + transfer custom images (from WSL2)
docker buildx bake --load
for img in bot bge-m3 user-base docling ingestion; do
  make k3s-push-$img
done

# 4. Create secrets + deploy
make k3s-secrets
make k3s-bot
make k3s-status
```

## CRM Env Vars (bot deployment)

Added in #384/#390/#402: `KOMMO_LEAD_SCORE_FIELD_ID`, `KOMMO_LEAD_BAND_FIELD_ID`, `NURTURING_ENABLED`, `NURTURING_INTERVAL_MINUTES`, `FUNNEL_ROLLUP_CRON`. Add to `k8s/secrets/.env` before deploying.

## Troubleshooting

| Issue | Fix |
|-------|-----|
| Pod pending (no image) | `make k3s-push-<service>` |
| CrashLoopBackOff | `make k3s-logs SVC=<service>` |
| OOM killed | Check resource limits, increase VPS RAM |
| Kustomize load error | Use `--load-restrictor=LoadRestrictionsNone` |
| Init container stuck | Service dependency not ready, check target pod |

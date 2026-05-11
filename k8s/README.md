# K3s Deployment (Partial)

This directory contains Kubernetes manifests for a **partial** k3s deployment path. Docker Compose is the primary local and VPS runtime; k3s support is maintained for core services but does not yet have full parity with the Compose service set.

## Ownership

- Owns partial k3s manifests, overlays, secret templates, and single-node k3s config.
- Scoped agent rules and validation live in [`AGENTS.override.md`](./AGENTS.override.md).

## Honest Scope

- **What works**: Core databases, ML services, bot, and ingestion can run on a single-node k3s cluster.
- **What is missing**: Some optional profiles (observability, voice SIP, Mini App frontend) may not be fully represented or tested under k3s.
- **Image policy**: k3s uses versioned GitHub Container Registry images (`ghcr.io/yastman/rag-*`) instead of local `rag/*:latest` tags. See [`../DOCKER.md`](../DOCKER.md) for image names and the publish workflow.

## Boundaries

- Compose remains the primary local and VPS runtime; runtime truth belongs in [`../DOCKER.md`](../DOCKER.md).
- Keep base manifests reusable and put deployment-mode differences in overlays.
- Do not hardcode secrets or remove PVC-related resources without an explicit migration plan.

## Directory Layout

### `base/`

Reusable base manifests. These are environment-agnostic and should not contain hardcoded secrets.

- **`namespace.yaml`** — `rag` namespace.
- **`configmaps/`** — Postgres init SQL and LiteLLM config as ConfigMaps.
- **`postgres/`** — PVC, Deployment, Service.
- **`redis/`** — PVC, Deployment, Service.
- **`qdrant/`** — PVC, Deployment, Service.
- **`docling/`** — PVC, Deployment, Service.
- **`bge-m3/`** — Deployment, Service.
- **`user-base/`** — Deployment, Service.
- **`litellm/`** — Deployment, Service.
- **`bot/`** — Deployment.
- **`ingestion/`** — Deployment.
- **`kustomization.yaml`** — Aggregates all base resources.

### `overlays/`

Environment-specific Kustomize overlays. Each overlay layers additional resources or patches on top of `base/`.

| Overlay | Scope | Includes |
|---|---|---|
| `core/` | Databases only | Postgres, Redis, Qdrant |
| `bot/` | Bot runtime | Core + BGE-M3 + user-base + LiteLLM + bot |
| `ingest/` | Ingestion runtime | Core + Docling + BGE-M3 + ingestion |
| `full/` | Everything in `base/` | All base manifests |

Apply an overlay with:

```bash
kubectl apply -k k8s/overlays/core/ --load-restrictor=LoadRestrictionsNone
kubectl apply -k k8s/overlays/bot/ --load-restrictor=LoadRestrictionsNone
kubectl apply -k k8s/overlays/ingest/ --load-restrictor=LoadRestrictionsNone
kubectl apply -k k8s/overlays/full/
```

### `secrets/`

Secret template for the cluster.

- **`.env.example`** — Example secret values. Copy to `.env`, fill values, then run `make k3s-secrets` to create Kubernetes secrets (`api-keys` and `db-credentials`).

### `k3s-config.yaml`

Single-node k3s server configuration for VPS deployment (secrets encryption, log rotation, eviction thresholds, etcd snapshots). Install to `/etc/rancher/k3s/config.yaml` before running the k3s installer.

## Makefile Commands

```bash
# Deploy stacks
make k3s-core      # core databases
make k3s-bot       # bot stack
make k3s-ingest    # ingestion stack
make k3s-full      # everything

# Operational helpers
make k3s-status    # pod status
make k3s-logs SVC=bot
make k3s-down      # tear down
make k3s-secrets   # create secrets from k8s/secrets/.env
make k3s-ingest-start
make k3s-ingest-stop

# Build and push versioned images
make k3s-push-bot K3S_IMAGE_TAG=v2.14.0
make k3s-push-ingest K3S_IMAGE_TAG=v2.14.0
```

## Focused checks

Follow the scoped validation contract in [`AGENTS.override.md`](./AGENTS.override.md).
When a cluster is available, run static inspection:

```bash
make k3s-status
```

For deployment changes, validate secrets and the target overlay:

```bash
make k3s-secrets
make k3s-core      # or make k3s-bot / make k3s-ingest / make k3s-full
```

For Compose parity checks, use the existing primary-runtime checks:

```bash
make verify-compose-images
COMPOSE_FILE=compose.yml:compose.dev.yml docker compose --compatibility config --services
```

## See Also

- [`../DOCKER.md`](../DOCKER.md) — Primary Compose runtime guide and image publishing workflow.
- [`../docs/LOCAL-DEVELOPMENT.md`](../docs/LOCAL-DEVELOPMENT.md) — Local development setup.

# Docker Deep Audit (Runtime + Images + Logs + Optimization)

Date: 2026-02-06
Project: `/opt/rag-fresh`
Stack: `docker-compose.vps.yml` (`vps-*` containers)

## Scope

- Running containers, health, resources, security settings.
- Docker images, layer composition, cache/storage pressure.
- Container logs (24h), recurring errors, noise patterns.
- Compose/Dockerfile hardening and performance readiness.

## Executive Summary

- Containers running: 10/10 healthy.
- Main risks are **runtime stability under load**, **security hardening gaps**, and **storage/cache pressure**.
- Biggest technical debt is around ingestion path (`vps-ingestion`): timeout/error bursts + excessive INFO logging.

Findings:
- Critical: 2
- High: 7
- Medium: 7
- Low: 2

## Runtime Snapshot

- Running containers: `vps-bot`, `vps-user-base`, `vps-bm42`, `vps-docling`, `vps-bge-m3`, `vps-ingestion`, `vps-litellm`, `vps-redis`, `vps-qdrant`, `vps-postgres`.
- Memory limits configured for all services (`docker-compose.vps.yml`), but:
  - Sum of limits: `13,199,474,688` bytes (~12.30 GiB)
  - Host RAM: `12,542,074,880` bytes (~11.68 GiB)
  - Overcommit exists by configuration.
- CPU limits are not set (`NanoCpus=0` for all containers).
- PIDs limits are not set (`PidsLimit=null` for all containers).

Current peak utilization snapshot:
- `vps-ingestion`: `269.1MiB / 512MiB` (52.57%)
- `vps-bot`: `181.1MiB / 512MiB` (35.36%)
- `vps-user-base`: `300.6MiB / 2GiB` (14.68%)
- `vps-bge-m3`: `202.5MiB / 4GiB` (4.94%)

## Log Analysis (last 24h)

Per-container volume:
- `vps-ingestion`: 9430 lines, `err_like=1080`, `warn_like=1`
- `vps-litellm`: 2608 lines, `err_like=40`
- `vps-docling`: 2005 lines (mostly warnings/info)
- `vps-bge-m3`: 2123 lines (low severity)

Top recurring issues:

1. `vps-ingestion`:
- `timed out` (231)
- `ReadTimeout` (66)
- `Upsert failed` (34)
- `Mutation failed` (34)
- `VoyageService not initialized` (27)

2. `vps-litellm`:
- `No api key passed in` (6)
- OTEL export failures to `host='none'` (NameResolutionError / ConnectionError)

3. `vps-postgres`:
- `relation "cocoindex_setup_metadata" does not exist`
- `role "rag" does not exist`

## Image and Storage Analysis

- Image sizes:
  - `ghcr.io/berriai/litellm:v1.81.3.rc.3`: 4.77GB
  - `rag-fresh_ingestion:latest`: 3.75GB
  - `rag-fresh_docling:latest`: 3.54GB
  - `rag-fresh_bge-m3:latest`: 2.33GB
  - `rag-fresh_user-base:latest`: 1.92GB
- Build cache size: ~25.82GB (`docker system df -v`).
- Docker volumes:
  - `rag-fresh_hf_cache`: ~5.2GB
  - `rag-fresh_docling_cache`: ~530MB
  - `rag-fresh_qdrant_data`: ~382MB
  - `rag-fresh_postgres_data`: ~88MB
- Host storage pressure contributor:
  - `/var/lib/containerd`: ~55GB
  - `/var/lib/docker`: ~5.6GB

Layer hotspots:
- `rag-fresh_ingestion`: `/app/.venv` layer ~2.74GB.
- `rag-fresh_docling`: `/opt/venv` layer ~2.35GB.
- `rag-fresh_bge-m3`: site-packages layer ~1.65GB.
- `rag-fresh_user-base`: site-packages layer ~1.33GB.

## Findings

| ID | Severity | Area | Evidence | Impact | Recommendation |
|---|---|---|---|---|---|
| D-01 | Critical | Ingestion runtime reliability | `vps-ingestion` logs: timeout/upsert/mutation failures; `src/ingestion/unified/qdrant_writer.py:73` (`QdrantClient timeout=120`) | Ingestion failures and repeated retries degrade indexing consistency and throughput. | Add retry/backoff around Qdrant upserts, tune batch sizes/timeouts, and monitor DLQ/error rate. |
| D-02 | Critical | Resource policy stability | Sum memory limits > host RAM; no CPU quotas (`NanoCpus=0`) | Under burst load, host can enter contention/OOM scenario despite per-container limits. | Rebalance limits to <= host budget and add CPU limits for heavy services (`docling`, `bge-m3`, `ingestion`). |
| D-03 | High | Logging flood in ingestion | `src/ingestion/unified/targets/qdrant_hybrid_target.py:215-227`, `:260-279` many per-item INFO logs | High log volume, noisy diagnostics, increased I/O overhead, harder incident triage. | Downgrade per-file progress logs to DEBUG; keep batch summary at INFO. |
| D-04 | High | Container hardening baseline missing | Runtime: `ReadonlyRootfs=false`, `CapDrop=` empty, no `security_opt: no-new-privileges`, `PidsLimit=null` | Larger attack surface and weaker containment on compromise. | Apply hardening defaults in compose for all compatible services. |
| D-05 | High | Root runtime users | `vps-litellm` user `root`; `vps-qdrant` user `0:0` | Elevated blast radius in container escape/misconfig scenarios. | Run as non-root where supported; otherwise apply stricter FS/capability limits. |
| D-06 | High | Cache/storage pressure | Build cache ~25.82GB; large image set and duplicated tags (`rag-fresh_bm42` vs `rag-fresh-bm42`, etc.) | Fast disk growth, risk of future ENOSPC incidents. | Introduce scheduled cache pruning and image lifecycle policy after successful deploys. |
| D-07 | High | LiteLLM operational noise/errors | `docker/litellm/config.yaml:33-41` enables `langfuse_otel`; logs show OTEL endpoint resolves to `none` | Continuous noisy errors, potential hidden signal loss. | Fix `LANGFUSE_OTEL_HOST` or disable callback until endpoint is valid. |
| D-08 | High | Secrets in runtime env | Compose env carries API keys and DB creds (`docker-compose.vps.yml:190-194`, `:22`) | Credentials exposure through inspect/runtime access. | Move to secrets manager / Docker secrets; rotate existing keys. |
| D-09 | Medium | Runtime drift vs built artifacts | Running `vps-docling` uses older image ID while newer `rag-fresh_docling:latest` exists | Deploy state ambiguity and reproducibility risk. | Enforce immutable tags + explicit rollout after build (`build -> up -d --no-deps --force-recreate`). |
| D-10 | Medium | Healthcheck overhead | Many services use Python one-liners for healthchecks at 30s intervals | Extra interpreter startup overhead and noisy dependency on Python runtime. | Prefer lightweight HTTP probe binaries where practical; tune intervals for stable services. |
| D-11 | Medium | Redis tuning parity gap | `vps-redis` uses `volatile-lfu`, but `maxmemory-samples=5` | Eviction quality below expected plan target under pressure. | Set `--maxmemory-samples 10` in VPS compose and verify via preflight. |
| D-12 | Medium | Postgres log verbosity/usefulness | Frequent checkpoint logs + app-level missing relation/role errors | Log noise and possible app bootstrap drift. | Align DB init/migrations and reduce non-actionable log verbosity. |
| D-13 | Medium | Ingestion image footprint | `rag-fresh_ingestion` ~3.75GB; venv layer dominates | Slower deployments, larger attack surface, higher storage cost. | Trim dependencies, split optional extras, verify uv lock minimization. |
| D-14 | Medium | ML service base image consistency | Multiple services use `python:3.12-slim` + varying uv bootstrap patterns | Inconsistent rebuild behavior and cache fragmentation. | Standardize on one base strategy and pinned uv version across services. |
| D-15 | Medium | Compose prod profile still mounts source | `docker-compose.vps.yml:285-286` mounts `./src` and `./telegram_bot` into `vps-ingestion` | Runtime relies on host source tree; weaker immutability. | Remove code bind mounts in production profile, keep in dev-only profile. |
| D-16 | Low | Deprecation warnings in ML services | `TRANSFORMERS_CACHE` warning in `vps-docling`, `vps-bge-m3` logs | Operational noise; future compatibility risk. | Move to `HF_HOME` only where possible. |
| D-17 | Low | Legacy root `Dockerfile` | `Dockerfile` remains single-stage legacy (`pip install`, `COPY . .`) | Inconsistent standards if accidentally used for build/deploy. | Archive or migrate to modern multi-stage pattern. |
| D-18 | Medium | No container init process | `HostConfig.Init=false` for all | Potential zombie process accumulation in some workloads. | Enable `init: true` for long-running Python services. |

## Optimization Plan

### 0-24h (quick wins)

1. Reduce ingestion log spam:
- Move verbose per-mutation INFO logs to DEBUG in `src/ingestion/unified/targets/qdrant_hybrid_target.py`.

2. Stabilize ingestion timeouts:
- Increase Qdrant client timeout and add retry with bounded backoff around upsert in `src/ingestion/unified/qdrant_writer.py`.
- Add explicit error-rate metric alert for `Mutation failed`/`timed out`.

3. Fix LiteLLM telemetry noise:
- Correct/remove invalid OTEL host configuration in `docker/litellm/config.yaml` and env.

4. Storage hygiene:
- Prune unused build cache/images after confirming running stack (`docker system df` budget target).

### 1-7 days

1. Hardening baseline in compose:
- Add `cap_drop: ["ALL"]` (then whitelist minimal caps if needed).
- Add `security_opt: ["no-new-privileges:true"]`.
- Add `read_only: true` + explicit writable `tmpfs`/volumes per service.
- Add `pids_limit` and CPU limits for each service.

2. Secrets hygiene:
- Move API keys/passwords from plain env to secrets workflow; rotate active keys.

3. Deployment reproducibility:
- Immutable image tags and forced recreate rollout for changed services.

### 1-4 weeks

1. Image size reduction:
- Continue splitting heavy optional dependencies.
- Standardize base image and uv patterns across all service Dockerfiles.

2. Network segmentation:
- Separate internal DB/cache network from egress services where possible.

3. Production profile cleanup:
- Remove source bind-mounts from VPS profile for immutable runtime behavior.

## Recommended KPI Targets

- Ingestion errors (`timed out`): from current burst levels to `< 1 per 1000 ops`.
- `vps-ingestion` log volume: reduce by at least 70%.
- Docker build cache: from ~25.8GB to `< 8GB` steady-state.
- Runtime hardening coverage: 100% services with `no-new-privileges`, `cap_drop`, `pids_limit`.
- Memory budget: total configured limits <= 90% of host RAM (with safety margin).

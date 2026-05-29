# Documentation Index

Project documentation index for humans and agents. Use this page to understand the system, find subsystem docs, and search the doc tree quickly.

## New Contributors Start Here

1. **[ONBOARDING.md](ONBOARDING.md)** -- first-time setup: prerequisites, clone, env, services, validation.
2. **[LOCAL-DEVELOPMENT.md](LOCAL-DEVELOPMENT.md)** -- day-to-day workflow: commands, profiles, validation ladder.
3. **[DEVELOPER_GUIDE.md](DEVELOPER_GUIDE.md)** -- extending the platform: add graph nodes, tools, query types, ingestion sources.

## Task-Oriented Indexes

For fast orientation by goal rather than by subsystem, see [`indexes/`](indexes/):

- [`indexes/fast-search.md`](indexes/fast-search.md) — "I need to find docs about X"
- [`indexes/runtime-services.md`](indexes/runtime-services.md) — Docker, ingestion, mini app, bot, voice
- [`indexes/observability-and-storage.md`](indexes/observability-and-storage.md) — Langfuse, Qdrant, Redis, LiteLLM, Postgres
- [`indexes/local-runtime.md`](indexes/local-runtime.md) — local bot startup, Telegram E2E, Telethon sessions, polling locks
- [`indexes/engineering-workflows.md`](indexes/engineering-workflows.md) — testing, issue triage, SDK lookup, dependency updates, docs maintenance, swarm process docs

## Understand the Project Fast

- [`../README.md`](../README.md) — System overview, architecture diagram, quick start, and reviewer path.
- [`review/PROJECT_GUIDE.md`](review/PROJECT_GUIDE.md) — Folder map and subsystem ownership.
- [`LOCAL-DEVELOPMENT.md`](LOCAL-DEVELOPMENT.md) — Local setup, day-to-day workflow, and validation ladder.
- [`../DOCKER.md`](../DOCKER.md) — Docker Compose profiles, service map, ports, env, and runtime truth.
- [`runbooks/README.md`](runbooks/README.md) — Operational investigations: traces, cache, vector search, Compose/runtime, and service health.
- [`engineering/test-writing-guide.md`](engineering/test-writing-guide.md) — Test-writing rules and local-fast vs heavy-tier split.
- [`engineering/sdk-registry.md`](engineering/sdk-registry.md) — SDK/framework lookup order and canonical versions.
- [`engineering/issue-triage.md`](engineering/issue-triage.md) — Issue classification and routing playbook.
- [`../skills/superpowers/`](../skills/superpowers/) — Repo-local agent skills, Kiro Web steering, and issue-to-skill map.
- [`engineering/README.md`](engineering/README.md) — Engineering process index with active and historical notes.
- [`adr/`](adr/) — Architecture decision records.

## Architecture & Design

- [`PROJECT_STACK.md`](PROJECT_STACK.md) — System architecture and subsystem map.
- [`BOT_ARCHITECTURE.md`](BOT_ARCHITECTURE.md) — Bot layer architecture.
- [`BOT_INTERNAL_STRUCTURE.md`](BOT_INTERNAL_STRUCTURE.md) — Bot internal component structure.
- [`PIPELINE_OVERVIEW.md`](PIPELINE_OVERVIEW.md) — Ingestion, query, and voice runtime flows.
- [`observability/CROSS_SERVICE_TRACING.md`](observability/CROSS_SERVICE_TRACING.md) — Cross-service W3C TraceContext/Baggage propagation contract.
- [`observability/VOICE_TRACING_BASELINE.md`](observability/VOICE_TRACING_BASELINE.md) — Voice/LiveKit W3C TraceContext SDK baseline.
- [`PIPELINE_ROUTING.md`](PIPELINE_ROUTING.md) — Query routing and state machine design.
- [`CONTEXTUALIZED_EMBEDDINGS.md`](CONTEXTUALIZED_EMBEDDINGS.md) — Embedding strategy and contextualization.
- [`RAG_API.md`](RAG_API.md) — FastAPI RAG API contract.
- [`API_REFERENCE.md`](API_REFERENCE.md) — API reference.
- [`DEVELOPER_GUIDE.md`](DEVELOPER_GUIDE.md) — Guide for extending graph nodes, tools, query types, and ingestion sources.

## Operations & Runbooks

- [`../DOCKER.md`](../DOCKER.md) — Docker Compose profiles, service map, env requirements.
- [`LOCAL-DEVELOPMENT.md`](LOCAL-DEVELOPMENT.md) — Local setup and validation guide.
- [`ONBOARDING.md`](ONBOARDING.md) — New-contributor onboarding guide.
- [`services/README.md`](../services/README.md) — Local service containers (BGE-M3, Docling, user-base).
- [`docker/README.md`](../docker/README.md) — Helper runtime assets (configs, scripts, monitoring rules).
- [`k8s/README.md`](../k8s/README.md) — Partial k3s manifests, overlays, and deploy commands.
- [`INGESTION.md`](INGESTION.md) — Unified ingestion guide and troubleshooting.
- [`GDRIVE_INGESTION.md`](GDRIVE_INGESTION.md) — Google Drive sync runbook.
- [`QDRANT_STACK.md`](QDRANT_STACK.md) — Vector collections, schema, and operations.
- [`ALERTING.md`](ALERTING.md) — Loki/Alertmanager setup.
- [`TROUBLESHOOTING_CACHE.md`](TROUBLESHOOTING_CACHE.md) — Cache troubleshooting guide.
- [`runbooks/`](runbooks/) — Incident-specific runbooks.

## Quality & Evaluation

- [`RAG_QUALITY_SCORES.md`](RAG_QUALITY_SCORES.md) — Scoring taxonomy and trace expectations.
- [`security/no-patch-dependency-alerts.md`](security/no-patch-dependency-alerts.md) — Accepted risk assessment for open Dependabot alerts without upstream patches (ragas, diskcache).
- [`security/secret-scanning-remediation.md`](security/secret-scanning-remediation.md) — Manual remediation runbook for open GitHub secret scanning alerts before public release.

## Migration & SDK

- [`engineering/sdk-registry.md`](engineering/sdk-registry.md) — Canonical SDK/framework lookup order and keeper stack.
- [`indexes/docker-sdk-map.md`](indexes/docker-sdk-map.md) — Docker image and SDK ownership map.

## Engineering Notes

- [`ERROR_RESPONSES.md`](ERROR_RESPONSES.md) — Error response taxonomy.
- [`HITL.md`](HITL.md) — Human-in-the-loop design.
- [`HITL_CRM_FLOW.md`](HITL_CRM_FLOW.md) — CRM-specific HITL flow.
- [`CACHE_DEGRADATION.md`](CACHE_DEGRADATION.md) — Cache failure modes.
- [`CLIENT_PIPELINE.md`](CLIENT_PIPELINE.md) — Client pipeline details.

## Fast Doc Search

Search the doc tree from the repo root:

```bash
rg -n "Langfuse|LiteLLM|Redis|Qdrant|Compose|ingestion|voice|mini app|Telegram|RAG" docs README.md DOCKER.md AGENTS.md
find docs -maxdepth 3 -name README.md -o -path 'docs/runbooks/*.md'
```

## Where Docs Live

| Path | Purpose |
|---|---|
| `docs/runbooks/` | Operational troubleshooting and incident response |
| `docs/engineering/` | Engineering process, standards, and workflow guides |
| `docs/plans/` | Shared implementation plans and design specs |
| `docs/review/` and `docs/portfolio/` | Reviewer and portfolio entry points |
| Folder `README.md` files | Local subsystem indexes (e.g., `services/`, `k8s/`, `docker/`) |

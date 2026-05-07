# Documentation Index

Project documentation index for humans and agents. Use this page to understand the system, find subsystem docs, and search the doc tree quickly.

## Understand the Project Fast

- [`../README.md`](../README.md) — System overview, architecture diagram, quick start, and reviewer path.
- [`review/PROJECT_GUIDE.md`](review/PROJECT_GUIDE.md) — Folder map and subsystem ownership.
- [`LOCAL-DEVELOPMENT.md`](LOCAL-DEVELOPMENT.md) — Local setup, day-to-day workflow, and validation ladder.
- [`../DOCKER.md`](../DOCKER.md) — Docker Compose profiles, service map, ports, env, and runtime truth.
- [`runbooks/README.md`](runbooks/README.md) — Operational investigations: traces, cache, vector search, Compose/runtime, and service health.
- [`engineering/test-writing-guide.md`](engineering/test-writing-guide.md) — Test-writing rules and local-fast vs heavy-tier split.
- [`engineering/sdk-registry.md`](engineering/sdk-registry.md) — SDK/framework lookup order and canonical versions.
- [`engineering/issue-triage.md`](engineering/issue-triage.md) — Issue classification and routing playbook.
- [`adr/`](adr/) — Architecture decision records.
- [`audits/`](audits/) — Dated investigation artifacts and evidence.

## Architecture & Design

- [`PROJECT_STACK.md`](PROJECT_STACK.md) — System architecture and subsystem map.
- [`BOT_ARCHITECTURE.md`](BOT_ARCHITECTURE.md) — Bot layer architecture.
- [`BOT_INTERNAL_STRUCTURE.md`](BOT_INTERNAL_STRUCTURE.md) — Bot internal component structure.
- [`PIPELINE_OVERVIEW.md`](PIPELINE_OVERVIEW.md) — Ingestion, query, and voice runtime flows.
- [`PIPELINE_ROUTING.md`](PIPELINE_ROUTING.md) — Query routing and state machine design.
- [`CONTEXTUALIZED_EMBEDDINGS.md`](CONTEXTUALIZED_EMBEDDINGS.md) — Embedding strategy and contextualization.
- [`RAG_API.md`](RAG_API.md) — FastAPI RAG API contract.
- [`API_REFERENCE.md`](API_REFERENCE.md) — API reference.
- [`ADD_NEW_RAG_NODE.md`](ADD_NEW_RAG_NODE.md) — Guide for adding a new RAG graph node.

## Operations & Runbooks

- [`../DOCKER.md`](../DOCKER.md) — Docker Compose profiles, service map, env requirements.
- [`LOCAL-DEVELOPMENT.md`](LOCAL-DEVELOPMENT.md) — Local setup and validation guide.
- [`ONBOARDING.md`](ONBOARDING.md) — Onboarding guide.
- [`ONBOARDING_CHECKLIST.md`](ONBOARDING_CHECKLIST.md) — Onboarding checklist.
- [`services/README.md`](../services/README.md) — Local service containers (BGE-M3, Docling, user-base).
- [`docker/README.md`](../docker/README.md) — Helper runtime assets (configs, scripts, monitoring rules).
- [`k8s/README.md`](../k8s/README.md) — Partial k3s manifests, overlays, and deploy commands.
- [`INGESTION.md`](INGESTION.md) — Unified ingestion guide and troubleshooting.
- [`GDRIVE_INGESTION.md`](GDRIVE_INGESTION.md) — Google Drive sync runbook.
- [`QDRANT_STACK.md`](QDRANT_STACK.md) — Vector collections, schema, and operations.
- [`ALERTING.md`](ALERTING.md) — Loki/Alertmanager setup.
- [`INFRA_ISSUES_REPORT_1113_1126.md`](INFRA_ISSUES_REPORT_1113_1126.md) — Infrastructure issues report.
- [`TROUBLESHOOTING_CACHE.md`](TROUBLESHOOTING_CACHE.md) — Cache troubleshooting guide.
- [`runbooks/`](runbooks/) — Incident-specific runbooks.

## Quality & Evaluation

- [`RAG_QUALITY_SCORES.md`](RAG_QUALITY_SCORES.md) — Scoring taxonomy and trace expectations.
- [`DEVELOPER_GUIDE.md`](DEVELOPER_GUIDE.md) — Development conventions and test guidance.
- [`ADRS.md`](ADRS.md) — Architecture decision records.

## Migration & SDK

- [`SDK_MIGRATION_AUDIT_2026-03-13.md`](SDK_MIGRATION_AUDIT_2026-03-13.md) — Canonical SDK keeper stack.
- [`SDK_MIGRATION_ROADMAP_2026-03-13.md`](SDK_MIGRATION_ROADMAP_2026-03-13.md) — Post-audit execution order.
- [`SDK_CANONICAL_REMEDIATION_REPORT_2026-03-15.md`](SDK_CANONICAL_REMEDIATION_REPORT_2026-03-15.md) — SDK canonical remediation report.

## Engineering Notes

- [`ERROR_RESPONSES.md`](ERROR_RESPONSES.md) — Error response taxonomy.
- [`HITL.md`](HITL.md) — Human-in-the-loop design.
- [`HITL_CRM_FLOW.md`](HITL_CRM_FLOW.md) — CRM-specific HITL flow.
- [`CACHE_DEGRADATION.md`](CACHE_DEGRADATION.md) — Cache failure modes.
- [`CLIENT_PIPELINE.md`](CLIENT_PIPELINE.md) — Client pipeline details.

## Archive

- [`archive/`](archive/) — Historical documentation and retired CI workflows preserved for context.

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
| `docs/audits/` | Dated evidence and investigation artifacts; not entrypoints |
| `docs/plans/` and `docs/superpowers/plans/` | Implementation plans and design specs |
| `docs/review/` and `docs/portfolio/` | Reviewer and portfolio entry points |
| Folder `README.md` files | Local subsystem indexes (e.g., `services/`, `k8s/`, `docker/`) |

# Documentation Index

This is a concise map of the major documentation areas in this repository.

## Reviewer Entry Points

Start here if you are reviewing the project for hiring, portfolio, or collaboration:

- [`README.md`](../README.md) — Project overview, architecture diagram, quick start, and reviewer path.
- [`docs/portfolio/resume-case-study.md`](portfolio/resume-case-study.md) — Resume-ready case study with feature cards and honest limitations.
- [`docs/review/PROJECT_GUIDE.md`](review/PROJECT_GUIDE.md) — Folder map and subsystem ownership.
- [`docs/review/ACCESS_FOR_REVIEWERS.md`](review/ACCESS_FOR_REVIEWERS.md) — Safe commands and boundaries.
- [`docs/review/GITHUB_REPO_SETUP.md`](review/GITHUB_REPO_SETUP.md) — Repository metadata and hygiene checklist.

## Architecture & Design

- [`docs/PROJECT_STACK.md`](PROJECT_STACK.md) — System architecture and subsystem map.
- [`docs/BOT_ARCHITECTURE.md`](BOT_ARCHITECTURE.md) — Bot layer architecture.
- [`docs/BOT_INTERNAL_STRUCTURE.md`](BOT_INTERNAL_STRUCTURE.md) — Bot internal component structure.
- [`docs/PIPELINE_OVERVIEW.md`](PIPELINE_OVERVIEW.md) — Ingestion, query, and voice runtime flows.
- [`docs/ADD_NEW_RAG_NODE.md`](ADD_NEW_RAG_NODE.md) — Guide for adding a new RAG graph node.
- [`docs/PIPELINE_ROUTING.md`](PIPELINE_ROUTING.md) — Query routing and state machine design.
- [`docs/CONTEXTUALIZED_EMBEDDINGS.md`](CONTEXTUALIZED_EMBEDDINGS.md) — Embedding strategy and contextualization.
- [`docs/RAG_API.md`](RAG_API.md) — FastAPI RAG API contract.
- [`docs/API_REFERENCE.md`](API_REFERENCE.md) — API reference.

## Operations & Runbooks

- [`DOCKER.md`](../DOCKER.md) — Docker Compose profiles, service map, env requirements.
- [`docs/LOCAL-DEVELOPMENT.md`](LOCAL-DEVELOPMENT.md) — Local setup and validation guide.
- [`docs/ONBOARDING.md`](ONBOARDING.md) — Onboarding guide.
- [`docs/ONBOARDING_CHECKLIST.md`](ONBOARDING_CHECKLIST.md) — Onboarding checklist.
- [`services/README.md`](../services/README.md) — Local service containers (BGE-M3, Docling, user-base).
- [`docker/README.md`](../docker/README.md) — Helper runtime assets (configs, scripts, monitoring rules).
- [`k8s/README.md`](../k8s/README.md) — Partial k3s manifests, overlays, and deploy commands.
- [`docs/INGESTION.md`](INGESTION.md) — Unified ingestion guide and troubleshooting.
- [`docs/GDRIVE_INGESTION.md`](GDRIVE_INGESTION.md) — Google Drive sync runbook.
- [`docs/QDRANT_STACK.md`](QDRANT_STACK.md) — Vector collections, schema, and operations.
- [`docs/ALERTING.md`](ALERTING.md) — Loki/Alertmanager setup.
- [`docs/INFRA_ISSUES_REPORT_1113_1126.md`](INFRA_ISSUES_REPORT_1113_1126.md) — Infrastructure issues report.
- [`docs/TROUBLESHOOTING_CACHE.md`](TROUBLESHOOTING_CACHE.md) — Cache troubleshooting guide.
- [`docs/runbooks/`](runbooks/) — Incident-specific runbooks.

## Quality & Evaluation

- [`docs/RAG_QUALITY_SCORES.md`](RAG_QUALITY_SCORES.md) — Scoring taxonomy and trace expectations.
- [`docs/DEVELOPER_GUIDE.md`](DEVELOPER_GUIDE.md) — Development conventions and test guidance.
- [`docs/ADRS.md`](ADRS.md) — Architecture decision records.

## Migration & SDK

- [`docs/SDK_MIGRATION_AUDIT_2026-03-13.md`](SDK_MIGRATION_AUDIT_2026-03-13.md) — Canonical SDK keeper stack.
- [`docs/SDK_MIGRATION_ROADMAP_2026-03-13.md`](SDK_MIGRATION_ROADMAP_2026-03-13.md) — Post-audit execution order.
- [`docs/SDK_CANONICAL_REMEDIATION_REPORT_2026-03-15.md`](SDK_CANONICAL_REMEDIATION_REPORT_2026-03-15.md) — SDK canonical remediation report.

## Engineering Notes

- [`docs/ERROR_RESPONSES.md`](ERROR_RESPONSES.md) — Error response taxonomy.
- [`docs/HITL.md`](HITL.md) — Human-in-the-loop design.
- [`docs/HITL_CRM_FLOW.md`](HITL_CRM_FLOW.md) — CRM-specific HITL flow.
- [`docs/CACHE_DEGRADATION.md`](CACHE_DEGRADATION.md) — Cache failure modes.
- [`docs/CLIENT_PIPELINE.md`](CLIENT_PIPELINE.md) — Client pipeline details.

## Archive

- [`docs/archive/`](archive/) — Historical documentation and retired CI workflows that are preserved for context but are not active runtime or CI configuration.

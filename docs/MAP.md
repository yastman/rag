# docs/ File Map

Canonical map of every file under `docs/`. Status values:

- **active** — current, referenced, and maintained
- **delete-candidate** — stale, completed, or references removed features as active
- **archived** — already under `docs/archive/`; scheduled for deletion in this audit

Generated: 2026-06-20 (issue #2938)

---

## Root docs/

| Path | Status | Reason |
|---|---|---|
| `docs/ADRS.md` | delete-candidate | One-liner legacy pointer; `docs/adr/README.md` is canonical |
| `docs/BOT_ARCHITECTURE.md` | active | Referenced from AGENTS.md area; current bot architecture |
| `docs/BOT_INTERNAL_STRUCTURE.md` | active | Covers active `handle_query()` / `start()` methods; `handle_voice()` row is stale but file is useful |
| `docs/CACHE_DEGRADATION.md` | active | Operational cache runbook |
| `docs/CLIENT_PIPELINE.md` | active | Describes client pipeline flow |
| `docs/CONTEXTUALIZED_EMBEDDINGS.md` | active | Embedding approach docs |
| `docs/DEVELOPER_GUIDE.md` | active | Local dev guidance |
| `docs/ERROR_RESPONSES.md` | active | Error handling reference |
| `docs/GDRIVE_INGESTION.md` | active | GDrive ingestion setup |
| `docs/HITL.md` | active | Human-in-the-loop confirmation flow |
| `docs/INGESTION.md` | active | Referenced from README.md |
| `docs/LOCAL-DEVELOPMENT.md` | active | Referenced from README.md and AGENTS.md |
| `docs/MAP.md` | active | This file |
| `docs/ONBOARDING.md` | active | Onboarding guide |
| `docs/PIPELINE_OVERVIEW.md` | active | Referenced from README.md |
| `docs/PIPELINE_ROUTING.md` | active | Pipeline routing logic |
| `docs/PROJECT_STACK.md` | active | Project tech stack summary |
| `docs/QDRANT_STACK.md` | active | Referenced from README.md |
| `docs/RAG_QUALITY_SCORES.md` | active | Quality scoring docs |
| `docs/README.md` | active | Documentation index, referenced from AGENTS.md |
| `docs/TROUBLESHOOTING_CACHE.md` | active | Cache troubleshooting |
| `docs/governance.md` | active | Governance rules |

---

## docs/adr/

| Path | Status | Reason |
|---|---|---|
| `docs/adr/README.md` | active | Canonical ADR index |
| `docs/adr/0001-colbert-reranking.md` | active | Active architectural decision |
| `docs/adr/0002-bge-m3-embeddings.md` | active | Active architectural decision |
| `docs/adr/0004-redisvl-semantic-cache.md` | active | Active architectural decision |
| `docs/adr/0005-hybrid-search-rrf.md` | active | Active architectural decision |
| `docs/adr/0007-hyde-custom-justified.md` | active | Active architectural decision |
| `docs/adr/0008-instructor-create-partial-deferred.md` | active | Active architectural decision |
| `docs/adr/0009-langgraph-send-fanout-scoping.md` | active | Active architectural decision |
| `docs/adr/0011-docker-compose-primary-runtime.md` | active | Active, Docker Compose is still primary runtime |
| `docs/adr/0012-langgraph-orchestration.md` | active | Active, LangGraph orchestration still used |
| `docs/adr/0013-cocoindex-docling-ingestion.md` | active | Active ingestion pipeline |
| `docs/adr/0014-properties-csv-as-source-of-truth.md` | active | Active domain decision |
| `docs/adr/0015-sdk-native-baseline.md` | active | Active engineering policy |
| `docs/adr/0016-otel-metrics-vs-prometheus.md` | active | OTel metrics policy still applies |
| `docs/adr/0018-w3c-baggage-vs-propagate-attributes.md` | active | Active tracing decision |
| `docs/adr/0019-core-text-path-procedural-runtime.md` | active | Core procedural runtime ADR |
| `docs/adr/0020-orchestration-monolith.md` | active | Active monolith orchestration decision |

---

## docs/archive/ (entire directory — delete-candidate)

| Path | Status | Reason |
|---|---|---|
| `docs/archive/README.md` | delete-candidate | Archive index, deleting whole archive |
| `docs/archive/API_REFERENCE.md` | delete-candidate | FastAPI RAG API removed #2791 |
| `docs/archive/RAG_API.md` | delete-candidate | FastAPI RAG API removed #2791 |
| `docs/archive/adr/0003-langgraph-voice-text-split.md` | delete-candidate | Voice path removed #2791 |
| `docs/archive/adr/0010-voice-path-create-agent-migration-plan.md` | delete-candidate | Voice path removed #2791 |
| `docs/archive/adr/0017-otel-trace-sampling-roadmap.md` | delete-candidate | OTel sampling deferred/removed #2844 |
| `docs/archive/observability/MINIAPP_BROWSER_TRACING_DECISION.md` | delete-candidate | Mini App removed #2791 |
| `docs/archive/observability/VOICE_TRACING_BASELINE.md` | delete-candidate | Voice path removed #2791 |
| `docs/archive/observability/bugsink-setup.md` | delete-candidate | Bugsink not active |
| `docs/archive/review/kfp-kubernetes-dependency-audit-2450.md` | delete-candidate | Completed closed audit |
| `docs/archive/review/observability-ui-optional-deps-2431.md` | delete-candidate | Completed closed audit |
| `docs/archive/runbooks/LANGFUSE_TRACING_GAPS.md` | delete-candidate | Langfuse removed #2844 |
| `docs/archive/runbooks/MINIO_FAILURE.md` | delete-candidate | MinIO is Langfuse dep, Langfuse removed #2844 |

---

## docs/architecture/

| Path | Status | Reason |
|---|---|---|
| `docs/architecture/STRUCTURE.md` | active | Canonical directory ownership map, referenced from README.md |

---

## docs/assets/

| Path | Status | Reason |
|---|---|---|
| `docs/assets/readme/README.md` | active | Asset index |
| `docs/assets/readme/conversational-ai-platform-hero.svg` | active | Used in README.md hero image |

---

## docs/audit/

| Path | Status | Reason |
|---|---|---|
| `docs/audit/public-exports-audit-2715.md` | delete-candidate | Closed 2026-06 audit |
| `docs/audit/2026-06-17-layer-boundary-audit-2712.md` | delete-candidate | Closed 2026-06 audit |

---

## docs/audits/

| Path | Status | Reason |
|---|---|---|
| `docs/audits/2026-06-11-test-suite-monolith-trim-audit.md` | delete-candidate | Closed 2026-06 audit |
| `docs/audits/2026-06-11-open-pr-review.md` | delete-candidate | Closed 2026-06 audit |
| `docs/audits/2026-06-11-issue-optimization-recheck.md` | delete-candidate | Closed 2026-06 audit |
| `docs/audits/2026-06-17-endpoint-inventory-2632.md` | active | Recent ARCH-18 audit, useful reference |
| `docs/audits/2026-06-17-config-env-drift-audit-2716.md` | active | Recent config drift audit, useful reference |

---

## docs/demo/

| Path | Status | Reason |
|---|---|---|
| `docs/demo/5-minute-demo.md` | active | Referenced from README.md quick-start |

---

## docs/designs/

| Path | Status | Reason |
|---|---|---|
| `docs/designs/README.md` | delete-candidate | Index for stale design docs |
| `docs/designs/adr-2846-layering.md` | delete-candidate | Completed design, superseded by ADR-0019/0020 |
| `docs/designs/adr-2855-module-collapse.md` | delete-candidate | Completed design |
| `docs/designs/epic-2836-ingest-decouple.md` | delete-candidate | Completed epic |
| `docs/designs/epic-2843-surfaces-strip.md` | delete-candidate | Completed epic |
| `docs/designs/lean-core-test-guardrail-audit.md` | delete-candidate | Completed audit |
| `docs/designs/monolith-core-audit-implementation-plan.md` | delete-candidate | Completed implementation plan |
| `docs/designs/monolith-core-issue-backlog.md` | delete-candidate | Completed backlog |
| `docs/designs/monolith-core-optional-surfaces-status.md` | delete-candidate | Completed status doc |
| `docs/designs/monolith-core-plan.md` | delete-candidate | Completed plan |
| `docs/designs/monolith-core-shim-cleanup-checklist.md` | delete-candidate | Completed checklist |
| `docs/designs/oversized-module-inventory.md` | delete-candidate | Completed inventory |
| `docs/designs/swarm-pipeline.md` | delete-candidate | Completed internal tooling doc |
| `docs/designs/unified-assistant-entrypoint-contract.md` | delete-candidate | Completed design, contract now in code |
| `docs/designs/product-simplification-e2e-plan.md` | active | Referenced from AGENTS.md as source of truth |
| `docs/designs/product-simplification-stage-0-decisions.md` | active | Referenced from AGENTS.md as source of truth |
| `docs/designs/product-simplification-weekly-acceptance-2026-06-04.md` | active | Active weekly acceptance criteria |
| `docs/designs/yaroslav-simplification-workflow.md` | active | Referenced from AGENTS.md as source of truth |

---

## docs/documents/

| Path | Status | Reason |
|---|---|---|
| `docs/documents/README.md` | active | Corpus documents directory readme |

---

## docs/engineering/

| Path | Status | Reason |
|---|---|---|
| `docs/engineering/README.md` | active | Active index, sections verified |
| `docs/engineering/2026-05-27-runtime-docs-1193-closeout.md` | active | Historical closeout note, useful context |
| `docs/engineering/agent-workflow-modes.md` | active | Active workflow guidance |
| `docs/engineering/bot-inert-paths-inventory-2026-05.md` | active | Recent inert-paths inventory |
| `docs/engineering/bug-classes.md` | active | Active engineering reference |
| `docs/engineering/code-reuse-audit-2714.md` | active | Recent audit, useful reference |
| `docs/engineering/codex-web-prompt.md` | active | Referenced from AGENTS.md |
| `docs/engineering/dockerfile-inventory.md` | active | Active Dockerfile inventory |
| `docs/engineering/docs-maintenance.md` | active | Active docs maintenance rules |
| `docs/engineering/gh-pr-review.md` | active | Referenced from AGENTS.md |
| `docs/engineering/issue-triage.md` | active | Referenced from AGENTS.md |
| `docs/engineering/litellm-sdk-router.md` | active | Active SDK reference |
| `docs/engineering/mcp-tools.md` | active | Active MCP tools guide |
| `docs/engineering/orchestrator-finish-protocol.md` | active | Referenced from AGENTS.md |
| `docs/engineering/orchestrator-playbook.md` | active | Referenced from AGENTS.md |
| `docs/engineering/repo-hygiene-runbook.md` | active | Referenced from AGENTS.md |
| `docs/engineering/script-native-migration-matrix.md` | active | Active migration tracking |
| `docs/engineering/sdk-registry.md` | active | Referenced from AGENTS.md |
| `docs/engineering/skill-maintenance-guardrails.md` | active | Active skill guardrails |
| `docs/engineering/test-writing-guide.md` | active | Referenced from AGENTS.md |
| `docs/engineering/dependency-audits/2710-dependency-hygiene-audit.md` | active | Recent (2026-06-17), still actionable |
| `docs/engineering/dependency-audits/boto-google-cloud-deps.md` | delete-candidate | Completed audit; guardrail in contract test |
| `docs/engineering/dependency-audits/dead-code-cleanup-2458.md` | delete-candidate | Completed audit; issues resolved |

---

## docs/indexes/

| Path | Status | Reason |
|---|---|---|
| `docs/indexes/README.md` | active | Index of indexes |
| `docs/indexes/core-product-path.md` | active | Active product path index |
| `docs/indexes/docker-sdk-map.md` | active | Useful index despite some stale rows (mini-app, minio) |
| `docs/indexes/engineering-workflows.md` | active | Active engineering workflow index |
| `docs/indexes/fast-search.md` | active | Active search shortcuts |
| `docs/indexes/local-runtime.md` | active | Active local runtime index |
| `docs/indexes/observability-and-storage.md` | active | Active observability/storage index |
| `docs/indexes/runtime-services.md` | active | Active runtime services index |

---

## docs/observability/

| Path | Status | Reason |
|---|---|---|
| `docs/observability/CROSS_SERVICE_TRACING.md` | active | Cross-service tracing reference |
| `docs/observability/TRACE_COVERAGE_AUDIT_2168.md` | delete-candidate | Completed trace coverage audit |

---

## docs/plans/

| Path | Status | Reason |
|---|---|---|
| `docs/plans/open-issues-roadmap-2026-06-10.md` | delete-candidate | Completed coordination plan from 2026-06-10 |
| `docs/plans/2026-06-11-parallel-agent-issue-pr-plan.md` | delete-candidate | Completed parallel-agent plan from 2026-06-11 |

---

## docs/portfolio/

| Path | Status | Reason |
|---|---|---|
| `docs/portfolio/README.md` | active | Portfolio section index |
| `docs/portfolio/resume-case-study.md` | active | Referenced from README.md |

---

## docs/review/

| Path | Status | Reason |
|---|---|---|
| `docs/review/README.md` | active | Review section index |
| `docs/review/ACCESS_FOR_REVIEWERS.md` | active | Referenced from README.md |
| `docs/review/GITHUB_REPO_SETUP.md` | active | Referenced from README.md |
| `docs/review/PROJECT_GUIDE.md` | active | Referenced from README.md |
| `docs/review/stale-pr-audit-2026-06-18.md` | delete-candidate | Closed stale-PR audit |

---

## docs/runbooks/

| Path | Status | Reason |
|---|---|---|
| `docs/runbooks/README.md` | active | Referenced from AGENTS.md |
| `docs/runbooks/COMPOSE_SOURCE_CLEANUP.md` | active | Active operational runbook |
| `docs/runbooks/DOCLING_FAILURE.md` | active | Active service runbook |
| `docs/runbooks/EMBEDDING_SERVICE_FAILURE.md` | active | Active service runbook |
| `docs/runbooks/GIT_PR_ISSUE_NATIVE.md` | active | Active git workflow runbook |
| `docs/runbooks/LITEllm_FAILURE.md` | active | Active LLM runbook, verified in-use |
| `docs/runbooks/POSTGRESQL_WAL_RECOVERY.md` | active | Active DB recovery runbook |
| `docs/runbooks/QDRANT_TROUBLESHOOTING.md` | active | Active Qdrant runbook |
| `docs/runbooks/REDIS_CACHE_DEGRADATION.md` | active | Active Redis runbook |
| `docs/runbooks/SELF_HOSTED_RUNNER.md` | active | Active CI runner runbook |
| `docs/runbooks/TELEGRAM_BOT_FAILURE.md` | active | Active bot failure runbook |
| `docs/runbooks/vps-gdrive-ingestion-recovery.md` | active | Active VPS ingestion runbook |

---

## docs/security/

| Path | Status | Reason |
|---|---|---|
| `docs/security/filter-repo-patterns.txt` | active | Active security config |
| `docs/security/history-rewrite-manual-gate.md` | active | Active security gate doc |
| `docs/security/no-patch-dependency-alerts.md` | active | Active dependency alert policy |
| `docs/security/public-release-secret-scan.md` | active | Active secret scan procedure |
| `docs/security/secret-scanning-remediation.md` | active | Active remediation guide |
| `docs/security/secret-scanning-runbook.md` | active | Active security runbook |
| `docs/security/trufflehog-exclude-paths.txt` | active | Active trufflehog config |
| `docs/security/verification-commands.sh` | active | Active security verification script |

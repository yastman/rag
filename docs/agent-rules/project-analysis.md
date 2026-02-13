# Project Analysis (Documentation Snapshot)

## Scope And Sources
This analysis summarizes repository structure and operating conventions from:
- `CLAUDE.md`
- `.claude/rules/*.md`
- `.claude/rules/features/*.md`
- `README.md`
- `docs/PROJECT_STACK.md`, `docs/PIPELINE_OVERVIEW.md`, `docs/LOCAL-DEVELOPMENT.md`
- `Makefile` targets currently available in repo

Snapshot date: 2026-02-13.

Primary reference policy: `CLAUDE.md` and the file paths listed in that document are treated as canonical sources for project guidance.

## High-Level Assessment
- The project has clear subsystem boundaries (bot, ingestion, retrieval, infra, docs), but instructions were previously fragmented across `CLAUDE.md` and `.claude/rules/*` without Codex-native AGENTS chain.
- Runtime workflows are mature (compose profiles, k3s overlays, observability, ingestion CLI), but contributor guidance was distributed and at risk of drift.
- Existing docs include deep historical plans/reports; canonical operational docs are present but need explicit “source of truth” positioning.

## Subsystem Analysis

### 1. Bot Runtime (`telegram_bot/`)
- Strong modular split: graph orchestration, services, integrations.
- Key risk: accidental coupling between graph-node state contracts and service return types.
- Recommendation: enforce graph path tests for routing-sensitive changes.

### 2. Unified Ingestion (`src/ingestion/unified/`)
- Includes flow, state manager, manifest identity, and Qdrant writer.
- Key risk: hidden breakage when changing identity/hash or sync semantics.
- Recommendation: require preflight/status checks and controlled ingestion run for behavioral changes.

### 3. Retrieval And Quality (`src/retrieval/`, `src/evaluation/`)
- Multiple retrieval variants and reranking paths imply performance/quality trade-offs.
- Key risk: quality regression without explicit re-evaluation.
- Recommendation: tie retrieval changes to graph path + eval commands.

### 4. Infrastructure (`docker-compose*.yml`, `k8s/`)
- Dual deployment model (local compose and VPS k3s) is well-defined.
- Key risk: drift between base/overlays and secret handling mistakes.
- Recommendation: keep overlays environment-specific and secrets external.

### 5. Documentation (`docs/`)
- Rich documentation corpus; includes operational docs and large archive/plans set.
- Key risk: contradictory duplicate instructions.
- Recommendation: codify canonical docs and route deep agent rules through `docs/agent-rules/*` references.

## Documentation Gaps Closed By This Update
- Added root `AGENTS.md` for global Codex execution constraints.
- Added scoped overrides for bot, ingestion, k8s, and docs.
- Added runbook layer in `docs/agent-rules/` for architecture, workflow, testing, and infra.

## Maintenance Policy
- Keep AGENTS files concise and conflict-free.
- Put long procedures in `docs/agent-rules/*` or existing canonical docs.
- Validate command references against `Makefile` and runnable CLIs.
- Update this analysis when major architecture or deployment model changes.

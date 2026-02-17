# AGENTS.md

## Purpose
- Define repository-wide instructions for Codex.
- Keep rules concise, deterministic, and conflict-free.
- Keep deep procedures in `docs/agent-rules/*.md` runbooks.

## Scope Resolution
- Instruction precedence follows Codex scope rules:
  1. Root `AGENTS.md`
  2. Nearest `AGENTS.override.md`
  3. Deeper nested overrides
- Directory-specific guidance belongs only in scoped overrides.

## Workflow
- Before non-trivial edits, read:
  - `README.md`
  - nearest `AGENTS*.md`
  - relevant `docs/agent-rules/*.md`
- For behavior changes, add or update tests in the nearest `tests/` scope.
- Run pytest in parallel mode (`-n auto --dist=worksteal`) unless explicitly told otherwise.

## Required Verification
- Minimum gate before completion:
  - `make check`
  - `PYTEST_ADDOPTS='-n auto --dist=worksteal' make test-unit`
- For infra/integration/runtime-sensitive changes, run targeted checks from:
  - `docs/agent-rules/testing-and-validation.md`

## Safety
- Do not run destructive git commands (`git reset --hard`, `git checkout --`, force-push) unless explicitly requested.
- Do not commit `.env` secrets.
- Prefer minimal, focused diffs.
- Keep all AGENTS files concise (target <= 200 lines).

## Project Map
- `telegram_bot/` - LangGraph bot pipeline and integrations.
- `src/api/` - FastAPI RAG endpoint.
- `src/voice/` - LiveKit/SIP voice integration.
- `src/ingestion/unified/` - unified ingestion runtime.
- `src/retrieval/` - search engines and retrieval logic.
- `src/evaluation/` - retrieval/RAG evaluation tooling.
- `k8s/` - k3s manifests and overlays.
- `docs/` - operational docs and plans.

## Canonical References
- `README.md`
- `docs/PROJECT_STACK.md`
- `docs/PIPELINE_OVERVIEW.md`
- `docs/LOCAL-DEVELOPMENT.md`
- `docs/QDRANT_STACK.md`
- `docs/INGESTION.md`
- `docs/ALERTING.md`
- `docs/agent-rules/workflow.md`
- `docs/agent-rules/testing-and-validation.md`
- `docs/agent-rules/infra-and-deploy.md`
- `docs/agent-rules/architecture-map.md`
- `docs/agent-rules/project-analysis.md`
- `docs/agent-rules/skills-authoring.md`

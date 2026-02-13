# AGENTS.md

## Purpose
- Provide repository-wide rules for Codex work in this project.
- Keep instructions compact and deterministic.
- Put deep procedures in `docs/agent-rules/*.md` and existing runbooks.
- Treat `CLAUDE.md` as the canonical documentation index for project workflows and references.

## Workflow
- Read `README.md` and `CLAUDE.md` before non-trivial edits.
- For behavior changes, add or update tests in the nearest `tests/` scope.
- Before completion, run at least:
  - `make check`
  - `make test-unit`
- For infra or integration changes, also run targeted commands from `docs/agent-rules/testing-and-validation.md`.

## Safety
- Do not use destructive git commands (`git reset --hard`, `git checkout --`, force-push) unless explicitly requested.
- Do not edit `.env` secrets in commits.
- Prefer minimal diffs over broad rewrites.
- Keep all AGENTS files concise (target <= 200 lines).

## Project Map
- `telegram_bot/` - main LangGraph-based Telegram bot pipeline and service integrations.
- `src/api/` - FastAPI wrapper for RAG query endpoint.
- `src/voice/` - LiveKit/SIP voice bot integration.
- `src/ingestion/unified/` - CocoIndex-based unified ingestion pipeline.
- `src/retrieval/` - search engine variants and retrieval logic.
- `src/evaluation/` - RAG/search evaluation tooling.
- `k8s/` - k3s manifests and overlays.
- `docs/` - project docs, plans, and archived materials.

## Canonical Commands
- Setup: `uv sync`
- Lint + types: `make check`
- All tests: `make test`
- Fast unit tests: `make test-unit`
- Graph path tests: `uv run pytest tests/integration/test_graph_paths.py -v`
- Core services: `make docker-up`
- Core + bot: `make docker-bot-up`
- Full stack: `make docker-full-up`
- Unified ingestion run/watch/status:
  - `make ingest-unified`
  - `make ingest-unified-watch`
  - `make ingest-unified-status`
- Trace validation: `make validate-traces-fast`
- RAG eval: `make eval-rag`

## Environment Baseline
- Python: 3.12+
- Package manager: `uv`
- Main runtime services: Qdrant, Redis, LiteLLM, Langfuse, Docling, BGE-M3
- Reference env template: `.env.example`

## Instruction Scope
- Use local `AGENTS.override.md` when present; deeper files take precedence.
- Keep directory-specific differences out of this root file.

## References
- `CLAUDE.md`
- `.claude/rules/build.md`
- `.claude/rules/docker.md`
- `.claude/rules/k3s.md`
- `.claude/rules/observability.md`
- `.claude/rules/services.md`
- `.claude/rules/testing.md`
- `.claude/rules/skills.md`
- `.claude/rules/features/search-retrieval.md`
- `.claude/rules/features/query-processing.md`
- `.claude/rules/features/evaluation.md`
- `.claude/rules/features/caching.md`
- `.claude/rules/features/embeddings.md`
- `.claude/rules/features/llm-integration.md`
- `.claude/rules/features/ingestion.md`
- `.claude/rules/features/telegram-bot.md`
- `.claude/rules/features/voice-bot.md`
- `.claude/rules/features/user-personalization.md`
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

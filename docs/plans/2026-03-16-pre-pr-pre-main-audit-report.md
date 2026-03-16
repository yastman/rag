# Pre-PR / Pre-Main Audit Report

- Branch: `audit/pre-main-audit-cont2-2026-03-16`
- Base: `origin/dev`
- Date: `2026-03-16`
- Worktree: `/home/user/projects/rag-fresh-wt-pre-main-audit-cont2`

## Baseline
- `git status --short`:
  dirty (targeted audit + autofix changes only)
- `git log --oneline -5`:
  - `0bd17a9b Merge pull request #979 from yastman/audit/pre-pr-pre-main-2026-03-16`
  - `00bca5c8 fix: report handler errors to langfuse spans`
  - `b14cd118 fix: auto-resolve typing blockers and harden state manager sql`
  - `7560b513 fix: harden parser cache hash usage`
  - `ffea39f7 docs: record audit inventory findings`

## Blockers Before PR
- [x] Candidate path: `README.md`, `docs/LOCAL-DEVELOPMENT.md`
  Reason: command paths (`make docker-*`, `make local-*`, `uv run`) required validation against real targets.
  Result: validated against `Makefile`; referenced targets exist and remain current.

- [x] Candidate path: `telegram_bot/middlewares/error_handler.py`
  Reason: compatibility wrappers and registration helpers could be stale.
  Result: active runtime and test coverage confirmed (`setup_error_handler` is used in `telegram_bot/bot.py`; wrapper surface is still referenced by tests/contracts).

- [x] Candidate path: `telegram_bot/services/llm.py`
  Reason: file is marked deprecated and overlaps with `generate_response.py`.
  Result: still imported by multiple unit/integration tests and guardrails paths; keep for compatibility in this PR.

- [x] Static-analysis blocker:
  Tool: `mypy`
  Result: `uv run mypy src/ telegram_bot/ --ignore-missing-imports --no-error-summary` now passes (notes only).

- [x] Static-analysis blocker review:
  Tool: `bandit`
  Result: no medium/high severity findings; only low-severity warnings remain (B105/B311/B112), moved to non-blocking cleanup.

## Cleanup If Time Permits
- [x] Candidate path: top-level `uv.lock`
  Reason: previously flagged by lockfile inventory.
  Result: intentional tracked dependency lockfile, kept.

- [x] Candidate path: `src/evaluation/`
  Reason: TODO/legacy markers needed runtime relevance check.
  Result: deferred as non-blocking cleanup (no regression signal in current verification scope).

- [x] Candidate path: `src/ingestion/chunker.py`, `src/ingestion/gdrive_indexer.py`, `src/ingestion/gdrive_flow.py`
  Reason: deprecated markers.
  Result: deferred; not touched in this PR to avoid scope creep.

- [x] Static-analysis cleanup:
  Tool: `vulture`
  Result: unchanged non-blocking list dominated by dialog callback parameter patterns and optional helper imports.

## Research-Needed Via Context7 / Official Docs
- Context7 (`/aiogram/aiogram/v3.25.0`): dispatcher/router-level global error handling with `ExceptionTypeFilter` remains canonical; current `setup_error_handler` registration strategy is valid.
- Context7 + official Hugging Face docs: `HF_HOME`/Hub cache paths are canonical for model cache storage; containerized model services require writable cache directories/volumes on cold start.

## Command Log
- Validation/audit:
  - `uv run ruff check src/ telegram_bot/`
  - `uv run ruff format --check src/ telegram_bot/`
  - `uv run mypy src/ telegram_bot/ --ignore-missing-imports --no-error-summary`
  - `uv run bandit -r src/ telegram_bot/ -c pyproject.toml`
  - `uv run vulture src/ telegram_bot/ --min-confidence 80`
- Test verification:
  - `uv run pytest tests/unit -q` → `5360 passed, 20 skipped`
  - `uv run pytest tests/integration -q` → `97 passed, 41 skipped`
  - `uv run pytest tests/contract -q` → `354 passed`
  - `uv run pytest tests/smoke -q` → `48 passed, 14 skipped`
  - `uv run pytest tests/e2e -q` → `9 skipped`
- Docker/compose verification:
  - `docker compose -f compose.yml -f compose.vps.yml build user-base`
  - `docker compose -f compose.yml -f compose.vps.yml up -d --force-recreate postgres redis qdrant user-base bge-m3 litellm bot`
  - `docker compose ... ps` + `docker inspect` + `docker logs`

## Files Changed During Audit
- `compose.yml`
- `docs/plans/2026-03-16-pre-pr-pre-main-audit-report.md`
- `services/user-base/Dockerfile`
- `src/contextualization/claude.py`
- `telegram_bot/bot.py`
- `tests/contract/test_error_contract.py`
- `tests/contract/test_span_coverage_contract.py`
- `tests/integration/test_bot_hybrid_search.py`
- `tests/integration/test_infrastructure.py`
- `tests/integration/test_service_chain_agent_tools.py`
- `tests/observability/trace_contract.yaml`
- `tests/smoke/test_mini_app_api.py`
- `tests/unit/test_bot_handlers.py`
- `tests/unit/test_collection_verify.py`
- `tests/unit/test_compose_config.py`
- `tests/unit/test_userbase_dockerfile_permissions.py`

## Final PR Decision
- Ready: yes
- Not ready because:
  - Non-blocking static cleanup remains in `bandit` low-severity and `vulture` unused-parameter findings.

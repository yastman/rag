# Pre-PR / Pre-Main Audit Report

- Branch: `audit/pre-pr-pre-main-2026-03-16`
- Base: `origin/dev`
- Date: `2026-03-16`
- Worktree: `/home/user/projects/rag-fresh-pre-pr-audit`

## Baseline
- `git status`:
  clean
- `git log --oneline -5`:
  - `f2f0eb49 Merge pull request #973 from yastman/feat/sdk-canonical-remediation`
  - `30649266 Merge remote-tracking branch 'origin/dev' into feat/sdk-canonical-remediation`
  - `dd26418b fix: restore prompt label and kommo shim compatibility`
  - `73255d63 feat: complete sdk canonical remediation plan phases 0-8`
  - `0c00a618 Merge pull request #971 from yastman/feat/952-858-855-857-901-956`

## Blockers Before PR
- [ ] Candidate path: `README.md`, `docs/LOCAL-DEVELOPMENT.md`
  Reason: operator-facing commands mix `make docker-*`, `make local-*`, and `uv run` paths; these need validation against actual runtime/deploy flow before PR.
  Keep / remove / refactor: validate; refactor docs if commands are stale or misleading.

- [ ] Candidate path: `telegram_bot/middlewares/error_handler.py`
  Reason: compatibility-only middleware wrapper and legacy registration helper remain in runtime surface.
  Keep / remove / refactor: verify active imports/tests; remove if compatibility surface is dead.

- [ ] Candidate path: `telegram_bot/services/llm.py`
  Reason: file self-identifies as deprecated and may still preserve a runtime compatibility surface that overlaps with `generate_response.py`.
  Keep / remove / refactor: confirm active call sites; remove or fence off if deprecated path is no longer needed.

- [ ] Static-analysis blocker:
  Tool: `mypy`
  File: multiple (`telegram_bot/middlewares/fsm_cancel.py`, `telegram_bot/middlewares/error_handler.py`, `telegram_bot/services/apartments_service.py`, `telegram_bot/services/apartment_llm_extractor.py`, `telegram_bot/dialogs/handoff.py`, `telegram_bot/services/apartment_extraction_pipeline.py`, `src/ingestion/cocoindex_flow.py`, `telegram_bot/bot.py`, others)
  Root cause: repo-wide typing drift across aiogram middleware signatures, Langfuse API usage, Qdrant filter typing, OpenAI/Instructor message types, dialog payload narrowing, and apartment extraction models.
  Fix strategy: split by subsystem; start with narrow middleware/typing fixes instead of mixing unrelated services in one patch.

- [ ] Static-analysis blocker:
  Tool: `bandit`
  File: `src/ingestion/unified/state_manager.py`
  Root cause: repeated `B608` SQL-construction findings around dynamic table-name interpolation need review for safe composition or explicit justification.
  Fix strategy: review table-name provenance and replace ad-hoc f-strings with validated composition or targeted suppressions only if proven safe.

## Cleanup If Time Permits
- [ ] Candidate path: top-level `uv.lock`
  Reason: matched `*.lock` inventory command but is the repository dependency lockfile, not disposable garbage.

- [ ] Candidate path: `src/evaluation/`
  Reason: multiple TODO/temporary/legacy references suggest cleanup debt, but not obviously PR-blocking without import/runtime evidence.

- [ ] Candidate path: `src/ingestion/chunker.py`, `src/ingestion/gdrive_indexer.py`, `src/ingestion/gdrive_flow.py`
  Reason: deprecated entry points are documented inline; verify whether they are still intentionally preserved.

- [ ] Static-analysis cleanup:
  Tool: `vulture`
  File: multiple `telegram_bot/dialogs/*`, `telegram_bot/agents/rag_tool.py`
  Reason deferred: current output is dominated by unused callback/widget parameters common in dialog handlers; these need manual triage to avoid false-positive deletions.

## Research-Needed Via Context7 / Official Docs

## Command Log
- `git status --short`: clean baseline in dedicated worktree.
- `find ... -name '*.lock'`: matched `uv.lock` only; kept as intentional tracked lockfile.
- `rg -n "deprecated|legacy|TODO|FIXME|temporary|workaround|compat shim" ...`: surfaced compatibility wrappers, deprecated service surfaces, and evaluation/ingestion cleanup candidates.
- `rg -n "make docker-|make local-|docker compose|uv run" README.md docs/LOCAL-DEVELOPMENT.md`: surfaced multiple operator-facing command paths for later validation.
- `uv run ruff check src/ telegram_bot/`: passed cleanly.
- `uv run ruff format --check src/ telegram_bot/`: passed cleanly.
- `uv run mypy src/ telegram_bot/ --ignore-missing-imports --no-error-summary`: failed with multiple blocker classes across middleware, apartment services, dialogs, ingestion, and bot runtime typing.
- `uv run bandit -r src/ telegram_bot/ -c pyproject.toml`: failed with one high-severity cache-hash issue plus multiple `state_manager.py` SQL-construction findings.
- `uv run vulture src/ telegram_bot/ --min-confidence 80`: surfaced many likely-false-positive unused dialog callback parameters; triaged as cleanup until validated.

## Files Changed During Audit
- `docs/plans/2026-03-16-pre-pr-pre-main-audit-report.md`

## Final PR Decision
- Ready:
- Not ready because:

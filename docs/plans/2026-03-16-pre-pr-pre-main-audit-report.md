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

## Cleanup If Time Permits
- [ ] Candidate path: top-level `uv.lock`
  Reason: matched `*.lock` inventory command but is the repository dependency lockfile, not disposable garbage.

- [ ] Candidate path: `src/evaluation/`
  Reason: multiple TODO/temporary/legacy references suggest cleanup debt, but not obviously PR-blocking without import/runtime evidence.

- [ ] Candidate path: `src/ingestion/chunker.py`, `src/ingestion/gdrive_indexer.py`, `src/ingestion/gdrive_flow.py`
  Reason: deprecated entry points are documented inline; verify whether they are still intentionally preserved.

## Research-Needed Via Context7 / Official Docs

## Command Log
- `git status --short`: clean baseline in dedicated worktree.
- `find ... -name '*.lock'`: matched `uv.lock` only; kept as intentional tracked lockfile.
- `rg -n "deprecated|legacy|TODO|FIXME|temporary|workaround|compat shim" ...`: surfaced compatibility wrappers, deprecated service surfaces, and evaluation/ingestion cleanup candidates.
- `rg -n "make docker-|make local-|docker compose|uv run" README.md docs/LOCAL-DEVELOPMENT.md`: surfaced multiple operator-facing command paths for later validation.

## Files Changed During Audit
- `docs/plans/2026-03-16-pre-pr-pre-main-audit-report.md`

## Final PR Decision
- Ready:
- Not ready because:

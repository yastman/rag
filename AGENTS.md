# AGENTS.md — OMP runbook for rag-fresh

Operational routing only. Product/runtime facts live in `README.md`; read it only when needed.

## Bootstrap

1. Project identity: `rag-fresh`; canonical checkout:
   `C:\Dev\projects-wsl-migrated-2026-07-13\rag-fresh`.
2. Current checkout/worktree: `git rev-parse --show-toplevel`.
3. Classify the request and take only its route below. Do not preload docs, roadmap, cards, or code.

Main dynamically selects matching live skills for itself and delegated agents when this materially
reduces risk, context, or execution cost; explicit user choices take precedence. Pass skill names
with owned target/base, never their contents, and read each once per session. Skills never expand
ownership or mutation permissions.


## Local quality contract

- `make dev-setup` installs both commit and push hooks. Commit hooks run fast file checks; push
  hooks run static/security checks and the cross-platform core pytest gate.
- Core changes: run `make test-core` first.
- Adapter or service changes: run `make test-core`, then `make test`.
- Contract changes: run `make test-contract`.
- Delivery gate: run `make candidate-check` (`check-frozen`, `test`, and `test-contract`).
- Use `make test-full` only for a manual pre-merge full-suite check.
- Run focused tests before the broader gate when the changed path has a narrower command.
- GitHub runs no pytest. Its advisory guard independently checks Gitleaks, Ruff lint/format, and
  actionlint only; it does not replace a passing local gate. Linux portability and release checks
  remain local through WSL or a container. If a second developer or merge bot joins, move pytest,
  mypy, and Bandit into required CI.

## Routes

| Request | Route |
| --- | --- |
| `выполни фазу <exact-id>` | Use the solo phase flow below. |
| `выполни карточку <exact-id>` | Fetch `memory_cards(action="get", id=CARD_ID, compact=false)`, take its `phase_id`, then use the solo phase flow. |
| Partial phase ID/name | Resolve once through the bounded CodeIndexer route, then use the solo phase flow. |
| Code question/change | CodeGraph first; CodeIndexer only when semantic/history/diff context helps. |
| Bug/test failure | Check CodeIndexer `solutions`, then diagnose before changing code. |
| External API/library docs | Use Context7; delegate to `librarian` when research can run independently. |
| Review | Fix the exact target and Git base; exclude unrelated dirty-checkout changes. The owning writer or reviewer inspects the complete target diff. Main verifies target/base, changed-file scope, integration state, refs, checks, and evidence, and may inspect the raw diff whenever risk or uncertainty warrants it. |
| Actual merge/rebase conflict | Resolve from Git's authoritative conflict state. |

## Scoped guidance

Before editing one of these areas, read its nearest scoped override:

- When delegating to `reviewer`, omit `effort`; never pass `effort: "hi"`, so its `@slow` selector controls the reasoning level.

- [`telegram_bot/AGENTS.override.md`](telegram_bot/AGENTS.override.md)
- [`src/ingestion/unified/AGENTS.override.md`](src/ingestion/unified/AGENTS.override.md)
- [`scripts/AGENTS.override.md`](scripts/AGENTS.override.md)
- [`services/AGENTS.override.md`](services/AGENTS.override.md)
- [`services/bge-m3-api/AGENTS.override.md`](services/bge-m3-api/AGENTS.override.md)


## MCP/tool responsibilities

- **CodeIndexer** (`project="rag-fresh"`): phase/card lifecycle, semantic/symbol/exact search,
  solutions, reports, cross-session memory, and semantic diff review. Never call `projects(list)`
  for this known project. If CodeIndexer is unavailable, do not emulate or mutate roadmap/card
  lifecycle; report the missing capability.
- **CodeGraph**: use MCP when exposed, otherwise `codegraph explore`; current source,
  callers/callees, flows, edit targets, affected tests, and blast radius. Set `projectPath` to the
  current worktree root for MCP. Start capped (`maxFiles=3-4`); make narrower follow-ups only for a
  concrete gap, new symbol, or reported staleness. On `worktreeMismatch` or staleness, read only
  affected files; never trust another branch's source.
- **Context7**: versioned external library/API documentation only; use official primary
  documentation when unavailable, and never use either for repository state.
- **Git**: authoritative files, diff, commits, branches, and worktrees.
- **GitHub**: PR, CI, merge, and remote delivery evidence; never roadmap state.

Default CodeIndexer code query: `search_code(mode="cascade", compact=true)`, then refine. Before
review, record the exact target and base. Use `review_diff` when exposed; otherwise diff-aware
`search_code(..., since=<base>)`. Git is authoritative: target WIP = that worktree's `git diff` plus
`git diff --cached`; committed target = `git diff <target-base>...<target-head>`. Confirm findings
against that exact diff and inspect index freshness, truncation, ambiguity, confidence, provenance,
and truth boundaries; dynamic CodeGraph edges remain confidence-scored evidence.

## Orchestration

The live task schema and OMP routing are authoritative for roles, models, isolation options, and
delegation depth. Never duplicate or invent runtime configuration here.

Main owns intent, scope, cross-slice contracts, lifecycle, integration decisions, and final
acceptance. Treat its context as a scarce integration resource: keep bulk exploration, files, raw
logs, docs, and working diffs with their owning agents; return decision-grade, retrievable evidence.

Children receive context files and runtime-forwarded rules, but not conversation history or informal
parent discoveries. Give each task self-contained decisions, constraints, ownership, and acceptance.
Agents may delegate within live depth policy; reuse an addressable agent when continuity beats fresh context.

When exposed and useful for high-volume or machine-consumed results, prefer compact `outputSchema`
covering decision/blocker, artifacts, verification, risks, and evidence; use prose when validation
adds more fragility than value. Use `reviewer` only when risk or uncertainty warrants it. Children
never push, PR, merge, clean worktrees, mutate CodeIndexer, or commit without Main authorization.

Choose write isolation from the live task schema and persistent-worktree needs; use one worktree per
concurrent writer, not per card. Agent completion is not integration: verify apply state, target
refs, errors, checks, and retained artifacts; handle them only when automatic integration failed.

## Solo phase flow

1. Fetch phase and cards in parallel:
   `roadmap(action="show", phase_id=ID)` and
   `memory_cards(action="get", phase_id=ID, compact=true)`. Skip project discovery, briefing,
   roadmap list/next, and full-card preload. Before executing or reviewing a selected card, fetch
   `memory_cards(action="get", id=CARD_ID, compact=false)`; never expand unrelated cards.
2. Main validates dependencies/acceptance, then `git fetch origin`.
3. Resume or create the persistent `phase/<phase-id>` worktree. Inspect
   `git worktree list --porcelain` and `git show-ref --verify refs/heads/phase/<phase-id>`: resume a
   verified linked worktree, attach one for an existing branch, or create both from fresh
   `origin/dev` only when absent. The canonical checkout may contain user WIP and need not be clean.
   A new phase-worktree must be clean; preserve and inspect a resumed dirty phase-worktree, and never
   reset, clean, stash, remove, or recreate it automatically.
4. Make one initial capped CodeGraph query for the card's symbols/files/flow/blast radius. Repeat
   only for a concrete missing or new symbol, ambiguity, truncation, or reported staleness. Use
   CodeIndexer search only for missing semantic/history context.
5. Implement the smallest coherent change, run focused tests and `git diff --check`, and have the
   assigned writer inspect the complete target diff. Fix and repeat until required checks pass.
6. Main chooses review, PR, and delivery topology from risk, collaboration, and repository policy.
   After all cards, combine their committed outputs, require a clean tracked state, `git fetch
   origin`, merge fresh `origin/dev` without rebasing, and record candidate and tested-origin SHAs.
7. Run `make test-full` once on that candidate. Immediately
   before integration fetch again; if `origin/dev` moved, repeat merge, commit, SHA recording, and
   gate. PR is optional; push or merge the exact candidate into `dev` without rewriting history.
8. After external integration, `git fetch origin` and prove the candidate is an ancestor of
   `origin/dev`. Only then mark cards and phase DONE and remove clean persistent worktrees.

Use CodeIndexer `solutions` as diagnostic evidence. Fix candidate or integration regressions before
delivery; record reproducible unrelated bugs as deduplicated cards. Main decides whether discovered
issues block the current phase.

Partial ID: `roadmap(action="list", project="rag-fresh", id_substring=fragment)`; paginate only while
`has_more=true`, then exact flow. Name: compact roadmap list, paginate only while `has_more=true`,
disambiguate locally. If a phase command has no ID or name, ask for one; use
`briefing(project="rag-fresh")` only for an explicit “what should I work on next?” request.

Failed/stale local gates, review, push, integration, or ancestry leave work unfinished and
worktrees recoverable. A missing PR or native pre-PR status is not evidence of failure: full local
gate evidence and ancestry in `origin/dev` are authoritative.

# AGENTS.md — OMP runbook for rag-fresh

Operational routing only. Product/runtime facts live in `README.md`; read it only when needed.

## Bootstrap

1. Project: `rag-fresh`; resolve the current checkout with `git rev-parse --show-toplevel`.
2. Classify the request and take only its route below. Do not preload unrelated context.


## Local quality contract

- `make dev-setup` installs commit and push hooks; run the narrowest focused test first.
- Core changes: run `make test-core` first.
- Adapter or service changes: run `make test-core`, then `make test`.
- Contract changes: run `make test-contract`.
- Delivery gate: run `make candidate-check` (`check-frozen`, `test`, and `test-contract`).
- Use `make test-full` only for a manual pre-merge full-suite check.
- GitHub runs no pytest; its checks are advisory. Local gates are authoritative.

## Routes

| Request | Route |
| --- | --- |
| `выполни фазу <exact-id>` | Use the solo phase flow below. |
| `выполни карточку <exact-id>` | Fetch `memory_cards(action="get", id=CARD_ID, compact=false)`, take its `phase_id`, then use the solo phase flow. |
| Standalone mutating issue | Use one branch and worktree; do not duplicate one already represented by a card. |
| Partial phase ID/name | Resolve once through the bounded CodeIndexer route, then use the solo phase flow. |
| Code question/change | CodeGraph first; CodeIndexer only when semantic/history/diff context helps. |
| Bug/test failure | Check CodeIndexer `solutions`, then diagnose before changing code. |
| External API/library docs | Use Context7; delegate to `librarian` when research can run independently. |
| Review | Review the exact target against its Git base; exclude unrelated WIP. |
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

- **CodeIndexer** (`project="rag-fresh"`): phase/card lifecycle and semantic/history context. If it
  is unavailable, do not emulate lifecycle mutations.
- **CodeGraph**: current source, flows, edit targets, tests, and blast radius; query once and refine
  only for a concrete gap. On mismatch or staleness, trust the current worktree files.
- **Context7**: versioned external API documentation only.
- **Git**: authoritative files, diff, commits, branches, and worktrees.
- **GitHub**: PR, CI, merge, and remote delivery evidence; never roadmap state.

Before review, record the target and base. Review WIP with `git diff` plus `git diff --cached`, or
committed work with `git diff <base>...<head>`.

## Orchestration

Main owns scope, lifecycle, integration, and acceptance. Give each child explicit ownership and
acceptance. Children never push, merge, clean worktrees, or mutate CodeIndexer; assigned writers may
commit owned files when Main authorizes it. Each assignment names the target worktree and expected
HEAD; the writer verifies its Git root, HEAD, and tracked state before work.

## Solo phase flow

1. Fetch the phase, compact card list, and the selected card in full.
2. Main validates dependencies/acceptance, then `git fetch origin`.
3. Resume the verified `phase/<phase-id>` worktree or create a clean one from `origin/dev`; preserve
   unknown dirty state.
4. Inspect `git worktree list --porcelain` to confirm current state. For each card, resume or
   create `card/<card-id>-<slug>` and its linked worktree from the current phase head, maintaining
   one worktree per mutating card. Never mix cards or reuse a dirty one.
5. Query CodeGraph once; refine only for a concrete gap.
6. Implement and test the card, inspect its complete diff, commit all intended changes, push the
   card branch, and merge it into the phase branch with `--no-ff`. Use a labelled WIP commit before
   interruption or handoff. Mark it DONE only after the merge.
7. After all cards, merge fresh `origin/dev` into the clean phase branch, run `make test-full`, and
   push the exact tested candidate to `dev` without rewriting history.
8. Fetch `origin` and prove the candidate is in `origin/dev`; then remove clean worktrees and delete
   the delivered card and phase branches locally and remotely.

Use CodeIndexer `solutions` for diagnosis. Resolve partial IDs with bounded roadmap search; ask when
no ID or name is supplied. Failed gates or ancestry leave the work unfinished and recoverable.

# Working in rag-fresh

Use the smallest context and change that can prove the requested outcome.
User instructions take precedence over repository workflow defaults.

## Start and locate

1. Resolve the checkout with `git rev-parse --show-toplevel`; inspect HEAD and
   `git status --short`. Preserve unrelated changes.
2. Identify the outcome, affected area, and existing GitHub issue when supplied.
3. Use the using-codeindex-codegraph skill before source search. Check indexed root/revision
   against this checkout; current Git/files win on mismatch. Do not refresh indexes implicitly.
4. Read the nearest scoped instructions below. Load other documents only for a concrete gap.

## Fact owners

| Need | Read |
| --- | --- |
| Product goal, accepted scope, terms | [PROJECT.md](PROJECT.md) |
| Setup and entry points | [README.md](README.md) |
| Module ownership, flows, import boundaries | [Structure](docs/architecture/STRUCTURE.md) |
| Environment and Windows/WSL setup | [Local Development](docs/LOCAL-DEVELOPMENT.md) |
| Test commands and lane coverage | [Tests](tests/README.md) |
| Deployment and recovery | [DOCKER.md](DOCKER.md), [runbooks](docs/runbooks/README.md) |
| Other maintained documentation | [Documentation hub](docs/README.md) |

GitHub Issues own work state, priority, dependencies, and acceptance. PRs own review/delivery
evidence. CodeGraph/CodeIndexer provide search, callers, tests, and semantic/history context;
they are not a second required task tracker. Existing card/phase IDs are lookup references,
not a requirement to create phase branches, duplicate cards, or synchronize two lifecycles.

Keep one owner per durable fact and link to it. Update that owner when a change makes it false.
Keep progress, investigation logs, and test-run evidence in the issue/PR. Proposed designs
remain proposals until an accepted, bounded change implements them.

## Work routes

- **Code:** get source/flow and affected tests from CodeGraph; use CodeIndexer
  (`project="rag-fresh"`) for a named context gap. Do not repeat a whole-repo scan.
- **Failure:** check CodeIndexer `solutions`, reproduce, then change the responsible layer.
  Separate baseline failures, environment faults, and regressions.
- **Library/API:** verify the installed version and use Context7 or official versioned docs.
- **Docs/rules:** use doc-gardening; use writing-for-agents for instruction changes.
  Record documentation/rule impact and preserve authority and gates explicitly.
- **Review:** record target and base; inspect `git diff` and `git diff --cached` for WIP,
  or `git diff <base>...<head>` for commits. Exclude unrelated work.

## Change and deliver

- Use one branch and one worktree per mutating task. Check
  `git worktree list --porcelain` before creating or resuming isolation.
- Default standalone branches to `codex/<short-purpose>` from fresh `origin/dev`.
  Resume the existing task branch when present; never reuse unknown dirty state.
- Follow the user's delegation preference and exposed runtime roles. If delegating, assign
  non-overlapping ownership and an expected HEAD. Main owns integration and acceptance;
  children do not push, merge, clean worktrees, or mutate task state.
- Commit/push/merge within the user's authorization. Review the complete diff, run required
  checks, and deliver the tested candidate without rewriting shared history.
- Fetch and prove the delivered commit is in `origin/dev` before reporting delivery.
  Close issues only when acceptance is met; clean only task-owned clean worktrees/merged branches.
- Diagnose failed gates or a moved remote before delivery. Do not weaken a check to make
  the current change pass. Report unresolved blockers with the exact command and evidence.

## Local quality contract

`make dev-setup` installs commit and push hooks. Start with a focused test.

| Change | Required scope checks |
| --- | --- |
| Core/runtime | `make test-core` first |
| Adapter or service | `make test-core`, then `make test`, plus scoped checks |
| Test contracts | `make test-contract` |
| Docs/instructions | Links/paths, affected tests, changed rule review, `git diff --check` |

The delivery gate is `make candidate-check`: frozen environment, lint/types, formatting,
deterministic tests, and contracts. `make test-full` is the manual major-candidate/full-suite
gate. GitHub runs the approved deterministic Candidate Gate plus static/security checks.
The full local gate remains required; hosted coverage is narrower. Follow
[branch protection](docs/runbooks/BRANCH-PROTECTION.md) and never bypass required checks.
The setup and test guides own platform commands and prerequisites.

## Scoped instructions

- [telegram_bot/AGENTS.override.md](telegram_bot/AGENTS.override.md)
- [src/ingestion/unified/AGENTS.override.md](src/ingestion/unified/AGENTS.override.md)
- [scripts/AGENTS.override.md](scripts/AGENTS.override.md)
- [services/AGENTS.override.md](services/AGENTS.override.md)
- [services/bge-m3-api/AGENTS.override.md](services/bge-m3-api/AGENTS.override.md)

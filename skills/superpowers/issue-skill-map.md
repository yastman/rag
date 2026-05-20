***REMOVED*** Issue Skill Map

Current mapping for the audited issue batch. Use this when deciding what to
send to Kiro Web or another agent.

***REMOVED******REMOVED*** Universal Rule

Every implementation issue starts with:

- `using-git-worktrees`
- `verification-before-completion`

Add `test-driven-development` for behavior changes, bug fixes, refactors, and
features. Add `writing-plans` when work is multi-step, architecture-heavy, or
cross-module. Add `subagent-driven-development` only when slices are independent
and file ownership can be reserved.

***REMOVED******REMOVED*** Kiro Web Handoff

For Kiro Web, comment on the issue with `/kiro` or add the `kiro` label only
after the issue has:

- a clear outcome;
- acceptance criteria;
- the required skills from this map;
- expected verification commands;
- safety notes.

Kiro will also read `.kiro/steering/agent-workflow.md`, which points back to
this folder.

***REMOVED******REMOVED*** Per-Issue Map

| Issue | Type | Required skills | Notes |
|---|---|---|---|
| ***REMOVED***1727 | dev tooling / hooks | `using-git-worktrees`, `writing-plans`, `verification-before-completion` | Add tests/checks for hook behavior where possible; no `devex` label exists, use existing infra/tech-debt taxonomy. |
| ***REMOVED***22 | bot refactor | `using-git-worktrees`, `writing-plans`, `test-driven-development`, `verification-before-completion` | APScheduler loop refactor; protect bot startup/shutdown behavior with tests. |
| ***REMOVED***1652 | research / design | `writing-plans`, `verification-before-completion` | Research first; no implementation until LangChain-native HyDE replacement is confirmed. |
| ***REMOVED***1650 | retrieval refactor | `using-git-worktrees`, `test-driven-development`, `verification-before-completion` | Batch request behavior must be covered with focused retrieval/client tests. |
| ***REMOVED***1649 | eval refactor | `using-git-worktrees`, `test-driven-development`, `verification-before-completion` | Structured output change needs regression tests for generated evaluation queries. |
| ***REMOVED***1648 | observability enhancement | `using-git-worktrees`, `writing-plans`, `test-driven-development`, `verification-before-completion` | Cross-cutting metrics/exporter work needs plan and focused observability checks. |
| ***REMOVED***1647 | retrieval architecture refactor | `using-git-worktrees`, `writing-plans`, `test-driven-development`, `verification-before-completion` | Architecture-heavy Qdrant/RRF path; plan before edits. |
| ***REMOVED***1643 | retrieval bug | `using-git-worktrees`, `test-driven-development`, `verification-before-completion` | Reproduce batch item failure isolation with a failing test first. |
| ***REMOVED***1637 | test bug | `using-git-worktrees`, `test-driven-development`, `verification-before-completion` | Test fixture leak; failing test or focused regression required. |
| ***REMOVED***1636 | test design / needs triage | `writing-plans`, `verification-before-completion` | Decide restore helper vs rewrite tests vs quarantine before implementation. |
| ***REMOVED***1635 | test infra | `using-git-worktrees`, `test-driven-development`, `verification-before-completion` | Validate advertised test target behavior. |
| ***REMOVED***1634 | test coverage | `using-git-worktrees`, `test-driven-development`, `verification-before-completion` | Add behavioral assertion for Redis eviction pressure. |
| ***REMOVED***1633 | test infra | `using-git-worktrees`, `test-driven-development`, `verification-before-completion` | Cover REDIS_URL unset behavior and target semantics. |
| ***REMOVED***1632 | test cleanup | `using-git-worktrees`, `verification-before-completion` | Remove stale health check; TDD optional if no behavior code changes. |
| ***REMOVED***1631 | retrieval tests | `using-git-worktrees`, `test-driven-development`, `verification-before-completion` | Prevent passing with empty Qdrant data. |
| ***REMOVED***1630 | cache/e2e bug | `using-git-worktrees`, `test-driven-development`, `verification-before-completion` | Reproduce skipped regression after live stack preflight. |
| ***REMOVED***1629 | ingestion e2e bug | `using-git-worktrees`, `test-driven-development`, `verification-before-completion` | Tighten assertions so error/no-op results fail. |
| ***REMOVED***1628 | bot test coverage | `using-git-worktrees`, `test-driven-development`, `verification-before-completion` | Exercise `PropertyBot.start` through BGE warmup path. |
| ***REMOVED***1627 | CRM live test safety | `using-git-worktrees`, `writing-plans`, `test-driven-development`, `verification-before-completion` | Requires explicit live-write gate and serial cleanup; no real CRM writes without approval. |
| ***REMOVED***1626 | CRM test bug | `using-git-worktrees`, `test-driven-development`, `verification-before-completion` | Add failing assertion for wrong non-empty CRM output. |
| ***REMOVED***1625 | eval test coverage | `using-git-worktrees`, `writing-plans`, `test-driven-development`, `verification-before-completion` | Move validation from local copies to runtime code. |

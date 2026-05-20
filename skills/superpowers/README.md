***REMOVED*** Superpowers Agent Skills

Repo-local operating guide for agentic issue execution. Use this folder when a
GitHub issue is handed to Kiro Web, Codex, or another autonomous coding agent.

***REMOVED******REMOVED*** Kiro Web Entry Points

Kiro Web can start from `app.kiro.dev`, from a GitHub issue comment containing
`/kiro`, or from a GitHub issue labeled `kiro`. Kiro reads persistent workspace
guidance from `.kiro/steering/` and also supports `AGENTS.md`.

When sending an issue to Kiro, include:

- the issue number and outcome;
- acceptance criteria;
- the skill list from [`issue-skill-map.md`](issue-skill-map.md);
- verification commands expected before PR;
- any safety gates such as no production, secrets, SSH, cloud, or live CRM
  writes unless explicitly approved.

***REMOVED******REMOVED*** Core Skills

- [`using-git-worktrees.md`](using-git-worktrees.md) - isolate each issue in a
  dedicated worktree/branch and verify a clean baseline.
- [`test-driven-development.md`](test-driven-development.md) - for features,
  bug fixes, refactors, and behavior changes: RED, GREEN, REFACTOR.
- [`writing-plans.md`](writing-plans.md) - for multi-step work: write a
  task-by-task plan before code changes.
- [`verification-before-completion.md`](verification-before-completion.md) -
  no completion, PR, or close claim without fresh verification evidence.
- [`subagent-driven-development.md`](subagent-driven-development.md) - for
  independent slices that can be delegated safely.
- [`executing-plans.md`](executing-plans.md) - for executing an approved plan
  step by step in one session.

***REMOVED******REMOVED*** Issue Routing

Use [`issue-skill-map.md`](issue-skill-map.md) as the current queue map. It
maps each audited issue to the minimum skill set an agent should load before
implementation.

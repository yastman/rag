# Shared: Forbidden files & safety gates

> Single source of truth for worker write-boundaries. Referenced by the swarm
> phase skills instead of being restated in each (#2305 P2).

## Never modify by default

```text
.kiro/skills/**
.kiro/agents/**
.env
.env.*
*.pem
*.key
```

Exception: a task explicitly about agent/skill infrastructure may edit
`.kiro/skills/**` or `.kiro/agents/**` when the prompt names it.

## Worktree & git boundaries

- Work only inside the assigned worktree and reserved files.
- Do not switch branches, rebase, merge, push, stash, clean, delete branches,
  create extra worktrees, or edit outside reserved files unless the prompt
  explicitly assigns that operation.
- Do not push. Do not create or update PRs unless the prompt explicitly assigns
  that operation.

## Access & secrets

- Do not access production, secrets, SSH, cloud credentials, live CRM writes, or
  real customer data unless explicitly authorized.
- Redact secrets from reports, logs, docs, and prompts; cite local artifact
  paths instead of pasting secret-bearing evidence.

## Review gate (P0 / security / destructive)

P0, security (auth/secrets/CSP/RBAC/signing/injection/XSS/SSRF/path-traversal/
deserialization), and destructive operations (delete data, drop tables,
in-place migrations, force-push, mass rewrite, runtime dependency-pin changes)
require a separate human or sub-agent review **before** final acceptance.

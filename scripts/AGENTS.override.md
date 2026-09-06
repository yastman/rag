# Operator scripts

Applies to scripts/**; extends [root AGENTS](../AGENTS.md).

- Keep reruns idempotent and side effects explicit.
- Bash scripts start with #!/usr/bin/env bash and set -euo pipefail.
- Prefer a typed Python entrypoint when a script has nontrivial parsing/control flow.
- Do not import Telegram runtime modules into out-of-process operator tools.
- Destructive operations require an explicit confirmation option or dry-run route.
- Credentials and environment-specific paths come from arguments/environment.

## Checks

Use `bash -n scripts/<file>.sh` and shellcheck for changed shell scripts.
Python changes require `make check` and focused script tests. CI/maintenance changes
also need the affected tooling contracts. Root delivery gates remain in force.

Read [script guide](README.md), [local setup](../docs/LOCAL-DEVELOPMENT.md), and
[runbooks](../docs/runbooks/README.md) for the relevant operation.

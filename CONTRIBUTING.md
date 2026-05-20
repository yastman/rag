# Contributing

Thanks for improving this project. Keep changes focused, verifiable, and safe
for local review.

## Ground Rules

- Work from a branch and keep each change scoped to one problem.
- Prefer local/test environments. Do not use production, VPS, SSH, cloud
  credentials, secrets, or real CRM write paths unless the task explicitly
  requires it.
- Redact secrets from issues, logs, screenshots, and reports.
- Update the canonical documentation when commands, ports, env vars, runtime
  behavior, API routes, or owner boundaries change.

## Local Setup

Read these first:

- [README.md](README.md) for the project overview and reviewer path.
- [docs/LOCAL-DEVELOPMENT.md](docs/LOCAL-DEVELOPMENT.md) for local setup.
- [DOCKER.md](DOCKER.md) for Compose profiles, services, ports, and env.
- [docs/engineering/test-writing-guide.md](docs/engineering/test-writing-guide.md)
  for test-writing rules.

## Checks

For documentation-only changes:

```bash
git diff --check
make docs-links
```

For code or runtime changes, run the focused checks for the touched area and at
least:

```bash
make test-unit
```

Use `make local-pr-ready` before opening a larger PR.

## Pull Requests

- Explain the user-visible change and the verification commands you ran.
- Link related issues or notes when available.
- Call out skipped checks with a short reason.
- Do not include local agent, swarm, prompt, or session artifacts.

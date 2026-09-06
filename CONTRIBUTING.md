# Contributing

[PROJECT.md](PROJECT.md) defines scope. [AGENTS.md](AGENTS.md) owns repository workflow,
task tracking, and delivery rules for both automated and manual contributions.

1. Use the existing GitHub issue when available; define the concrete outcome and boundaries.
2. Work on a focused branch from dev, preserving unrelated work.
3. Implement and update the document that owns any changed fact.
4. Run focused checks, then the required local `make candidate-check` delivery gate.
5. Open a PR against dev and wait for required hosted checks before merging.

Use [Local Development](docs/LOCAL-DEVELOPMENT.md) for setup and
[Tests](tests/README.md) for exact lane commands. `make dev-setup` installs hooks;
`make test-full` is the manual major-candidate gate. WSL or a Linux container supplies
the POSIX environment for Make/release verification.

GitHub runs approved deterministic candidate and static/security checks. Those checks
complement the full local gate; they do not replace it. See
[branch protection](docs/runbooks/BRANCH-PROTECTION.md).

## Changes and evidence

Explain the problem, resulting behavior, and actual validation in the PR. Include extra
detail only for a relevant risk or contract change. Keep temporary evidence and acceptance
progress with the issue/PR; keep raw history in Git.

Do not commit credentials, private datasets, local recordings, caches, or generated logs.
Use test fixtures for local checks. Production, CRM, and messaging writes need explicit
authorization for the operation; a code change alone does not authorize live side effects.

See [security policy](SECURITY.md) for security reports and
[code of conduct](CODE_OF_CONDUCT.md) for participation.

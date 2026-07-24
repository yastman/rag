# Contributing

Thank you for your interest in contributing.

## Getting Started

- Read [`README.md`](README.md) for project overview.
- See [`docs/LOCAL-DEVELOPMENT.md`](docs/LOCAL-DEVELOPMENT.md) for setup and the day-to-day development workflow.

## Development Workflow

1. Create a branch from `dev` for your changes.
2. Make focused changes with clear commit messages.
3. Run the local verification ladder before pushing:

```bash
make dev-setup        # first setup: dependencies, commit/push hooks, services
make check            # commit-level lint + type checking
make pre-push         # manual push gate: lint + format-check + core tests
make test-core        # scope gate for core/runtime changes
make test             # scope gate for adapter/service changes
make test-contract    # scope gate for contract changes
make candidate-check  # authoritative local delivery gate
make test-full        # major-candidate gate; manual and local only
```

GitHub runs no pytest. On Windows, run the direct `uv run --no-sync pytest ...` commands
documented in [`tests/README.md`](tests/README.md); use WSL or a container for Linux portability
and release verification.

4. Open a pull request against `dev`.

## What Not to Commit

- `.env` or any file containing real credentials
- generated artifacts, logs, or local session data
- Real datasets, personal recordings, or client exports
- Production deploy scripts or VPS/SSH keys

## Code of Conduct

This project and everyone participating in it is governed by our [Code of Conduct](CODE_OF_CONDUCT.md). By participating, you are expected to uphold this code.

## Safe Boundaries

- Do not run production or CRM write flows without maintainer approval.
- Use fake/demo credentials for local development and testing.
- Treat Telegram, Kommo, LiveKit, and cloud credentials as external secrets.

## Questions

- For general questions, open a public discussion or issue.
- For security concerns, see [`SECURITY.md`](SECURITY.md).

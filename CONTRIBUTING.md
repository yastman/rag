# Contributing

Thank you for your interest in contributing.

## Getting Started

- Read [`README.md`](README.md) for project overview.
- Follow [`docs/LOCAL-DEVELOPMENT.md`](docs/LOCAL-DEVELOPMENT.md) for setup instructions.

## Development Workflow

1. Create a branch from `dev` for your changes.
2. Make focused changes with clear commit messages.
3. Run the local verification ladder before pushing:

```bash
make check
uv run pytest tests/unit -q
docker compose --env-file tests/fixtures/compose.ci.env -f compose.yml -f compose.dev.yml config >/tmp/rag-compose.yml
```

4. Open a pull request against `dev`.

## What Not to Commit

- `.env` or any file containing real credentials
- `.swarm/`, `.signals/`, logs, or local session artifacts
- Real datasets, personal recordings, or client exports
- Production deploy scripts or VPS/SSH keys

## Code of Conduct

This project and everyone participating in it is governed by our [Code of Conduct](CODE_OF_CONDUCT.md). By participating, you are expected to uphold this code.

## Safe Boundaries

- Do not run production or CRM write flows without maintainer approval.
- Use fake/demo credentials for local development and testing.
- Treat Telegram, Kommo, Langfuse, LiveKit, and cloud credentials as external secrets.

## Questions

- For general questions, open a public discussion or issue.
- For security concerns, see [`SECURITY.md`](SECURITY.md).

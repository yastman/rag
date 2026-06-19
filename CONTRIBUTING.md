# Contributing

Thank you for your interest in contributing.

## Getting Started

- Read [`README.md`](README.md) for project overview.
- Follow [`docs/ONBOARDING.md`](docs/ONBOARDING.md) for the full onboarding guide.
- See [`docs/LOCAL-DEVELOPMENT.md`](docs/LOCAL-DEVELOPMENT.md) for day-to-day development workflow.

## Development Workflow

1. Create a branch from `dev` for your changes.
2. Make focused changes with clear commit messages.
3. Run the local verification ladder before pushing:

```bash
make pre-push          # lint + format-check
make check             # alias: lint + type-check
uv run pytest tests/unit -q
docker compose --env-file tests/fixtures/compose.ci.env -f compose.yml -f compose.dev.yml config --quiet
```

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
- Treat Telegram, Kommo, Langfuse, LiveKit, and cloud credentials as external secrets.

## Questions

- For general questions, open a public discussion or issue.
- For security concerns, see [`SECURITY.md`](SECURITY.md).

## License headers

The project uses the MIT license.  We do **not** require every source file to carry a
license header.  SPDX headers are optional; contributors may add

```text
SPDX-License-Identifier: MIT
```

to new files if they prefer, but the absence of a header does not change the
license.  See the root `LICENSE` file for the canonical license text.  Documenting
this decision here ensures reviewers know that missing headers are not a defect.

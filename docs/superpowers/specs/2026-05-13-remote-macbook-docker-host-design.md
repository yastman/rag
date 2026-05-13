# Remote MacBook Docker Host Design

Date: 2026-05-13

## Goal

Make the MacBook the canonical development Docker host for `rag-fresh`, including
the Telegram bot container, while keeping code editing and fast host-side checks
on the Windows/WSL workstation.

The target outcome is simple operational ownership:

- WSL owns source editing, git, Codex, `uv`, linting, type checks, and fast unit
  tests.
- MacBook owns Colima, Docker, Compose, containers, images, volumes, networks,
  Docker bind mounts, and the runtime `.env`.
- Docker Desktop on Windows/WSL is not required for normal development.
- The VPS is not part of this development workflow.

## Context

The Windows/WSL workstation becomes memory constrained when Docker Desktop and
the Compose stack run alongside normal development tools. The MacBook is
reachable on the LAN over SSH as `macbook-docker` and has Homebrew-managed
Colima/Docker tooling.

Canonical Docker service, profile, port, and environment truth remains in
[`../../../DOCKER.md`](../../../DOCKER.md). Local workflow truth remains in
[`../../LOCAL-DEVELOPMENT.md`](../../LOCAL-DEVELOPMENT.md). The remote MacBook
workflow belongs in [`../../runbooks/remote-macbook-docker.md`](../../runbooks/remote-macbook-docker.md)
and should link back to `DOCKER.md` instead of duplicating large service tables.

## Decision

Use the MacBook as the only dev Docker runtime:

- Compose commands run over SSH on `macbook-docker`.
- Compose runs from `/Users/aroslav/Documents/rag-fresh` on the MacBook because
  build contexts and bind mounts resolve on the Docker host.
- The active development stack includes the bot container when the user wants the
  Docker runtime path, not a native WSL bot.
- The WSL `make bot` command is not redefined by this work; it can remain a
  native helper. The remote Docker bot path uses explicit remote targets.
- The remote repo is synchronized through git by default. One-off file sync is
  allowed only as an explicit operator action.
- The workstation can still run tests against MacBook service endpoints when a
  test does not need Docker-local networks, volumes, or `docker exec`.

## Architecture

```text
Windows / WSL workstation
  - source editing
  - git and branch work
  - Codex / IDE
  - uv environment
  - lint, type checks, fast unit tests
  - make remote-* operator commands

SSH
  - host: macbook-docker
  - user: aroslav
  - key: ~/.ssh/macbook_remote_docker_ed25519

MacBook Air M1
  - Colima profile sized for the dev stack
  - Docker engine and Compose plugin
  - /Users/aroslav/Documents/rag-fresh repo checkout
  - .env for runtime secrets
  - Compose containers, images, volumes, and networks
```

## Runtime Modes

### Primary Mode: Remote Docker Stack With Bot

Use this when validating the production-like local runtime:

```bash
make remote-active-up
make remote-bot-logs
make remote-docker-ps
make remote-service-health
```

`remote-active-up` should start the current active development service set on the
MacBook and include the `bot` container. It should not start unrelated full-stack
services unless they are needed for the task.

### Full Stack Mode

Use this for explicit full-profile validation:

```bash
make remote-full-up
make remote-docker-ps
make remote-service-health
```

This mode is heavier and should not be the default always-on MacBook workload.

### Native Bot Mode

The existing `make bot` command can remain available for local native bot
debugging from WSL. It is not the main path for this design. Documentation should
make clear that the MacBook Docker workflow uses `remote-*` targets when the bot
must run in Docker.

## Environment Handling

The user approved full `.env` transfer to the MacBook for this migration.

Implementation rules:

- Copy the WSL repo-root `.env` to `/Users/aroslav/Documents/rag-fresh/.env` only
  as an explicit migration step.
- Do not print `.env` values in logs, docs, or chat.
- After transfer, validate required variables by name only.
- Use the repo's existing safe fallback,
  `tests/fixtures/compose.ci.env`, for config rendering and non-secret checks
  when `.env` is absent.
- Keep `.env.local` out of the automatic path unless a future design explicitly
  adds it.

Required bot-path variables are owned by `DOCKER.md`. The remote runbook may list
only the high-level validation behavior and should point to `DOCKER.md` for the
canonical variable list.

## Code Synchronization

The MacBook checkout is a normal git checkout:

```text
/Users/aroslav/Documents/rag-fresh
```

Preferred loop:

1. Work in WSL.
2. Commit/push or otherwise make the branch available.
3. Fetch/pull the target branch on the MacBook.
4. Build/start Compose on the MacBook.

This avoids hidden drift between the editable workstation tree and the Docker
host's build context. If uncommitted experiments need remote validation, add an
explicit sync target later with clear secret exclusions.

## Developer Commands

Remote targets should be thin wrappers over SSH:

```text
make remote-docker-status
make remote-compose-config
make remote-docker-ps
make remote-active-up
make remote-bot-up
make remote-bot-restart
make remote-bot-logs
make remote-full-up
make remote-local-down
make remote-service-health
make remote-env-sync
make remote-env-check
```

Command contracts:

- `remote-docker-status` checks SSH, Colima, Docker server, and buildx.
- `remote-compose-config` renders Compose with the same files as local dev:
  `compose.yml:compose.dev.yml`.
- `remote-active-up` starts the active dev service set, including `bot`.
- `remote-bot-up` starts or refreshes the bot container and its required profile.
- `remote-bot-restart` recreates the bot container after code/config changes.
- `remote-bot-logs` shows recent bot logs without printing secrets.
- `remote-env-sync` copies `.env` to the MacBook as the approved migration step.
- `remote-env-check` reports missing required variable names only.

All SSH commands should export `/opt/homebrew/bin:/usr/local/bin:$PATH` because
non-interactive macOS SSH sessions have a minimal path.

## Service Endpoints

When containers run on the MacBook, WSL `localhost` is not the Docker host.

Endpoint checks should use one of two patterns:

- Over SSH on the MacBook, use `127.0.0.1`.
- From WSL to MacBook-exposed ports, use `192.168.31.168`.

The remote runbook should explain the host substitution rule and link to
`DOCKER.md` for the service table.

## Test Strategy

### Stay On WSL

Run fast checks locally when they do not need Docker:

```bash
make lint
make type-check
make test-unit
```

### Run From WSL Against MacBook Services

Use this when tests only need HTTP/TCP service endpoints:

```bash
QDRANT_URL=http://192.168.31.168:6333 \
LITELLM_BASE_URL=http://192.168.31.168:4000 \
make test-bot-health
```

Any such command must avoid assuming WSL `localhost` is the Docker host.

### Run On The MacBook Over SSH

Run tests on the MacBook when they depend on Docker-local behavior:

- Compose service names or Docker networks;
- `docker exec`;
- local Docker volumes;
- bind mounts;
- container-local `localhost`;
- full bot-in-Docker startup checks;
- ingestion or model workflows tied to container filesystem state.

Example shape:

```bash
ssh macbook-docker 'cd ~/Documents/rag-fresh && export PATH=/opt/homebrew/bin:/usr/local/bin:$PATH; make test-smoke'
```

## Resource Policy

The MacBook Air M1 8GB needs a Colima profile large enough for BGE-M3 warmup.
Known working baseline:

```bash
colima start --cpu 4 --memory 7
```

The default active stack should mirror the services needed for current dev work
and avoid unrelated full-profile services. Full-profile validation is explicit.

`BGE_M3_MEMORY_LIMIT` should be overridable for remote Compose and default to a
MacBook-safe value such as `6G`.

## Failure Handling

- SSH unreachable: fail before changing runtime state.
- Colima stopped: report status and the start command.
- Docker buildx missing: report buildx wiring because BuildKit-only Dockerfile
  syntax is required.
- Remote repo stale: show branch and last commit before build/start operations.
- `.env` absent or incomplete: report missing variable names only.
- Bot container restart loop: inspect bot logs and container restart count.
- Health checks disagree with `docker compose ps`: do not call the stack healthy.

## Documentation Updates

Implementation should update:

- `DOCKER.md` only for canonical Docker command/env/profile facts.
- `docs/LOCAL-DEVELOPMENT.md` for the day-to-day MacBook Docker workflow.
- `docs/runbooks/remote-macbook-docker.md` for operational commands,
  troubleshooting, env transfer, and test split.
- `docs/indexes/` only if task-oriented lookup for remote Docker changes.

Avoid duplicating full service tables outside `DOCKER.md`.

## Rollout

1. Normalize docs and Makefile assumptions around
   `/Users/aroslav/Documents/rag-fresh`.
2. Verify read-only remote access: SSH, Colima, Docker server, buildx, git state,
   and Compose config render.
3. Transfer `.env` to the MacBook and validate required variable names.
4. Start the active remote Docker stack including the bot container.
5. Inspect `docker compose ps`, bot logs, and targeted service health.
6. Run WSL-host checks against MacBook endpoints where appropriate.
7. Run Docker-local checks over SSH on the MacBook.
8. Update project docs with the final working commands and any verified caveats.

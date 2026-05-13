# Remote MacBook Docker Host

> Run the full `rag-fresh` Docker stack on a remote MacBook while editing code in WSL.
>
> Canonical Docker service truth lives in [`../../DOCKER.md`](../../DOCKER.md).
> Local development workflow lives in [`../LOCAL-DEVELOPMENT.md`](../LOCAL-DEVELOPMENT.md).

## Architecture

- **WSL/workstation**: source editing, git, fast host-side checks (lint, type-check, unit tests).
- **MacBook**: Colima, Docker, Compose, all containers, volumes, images, networks, the remote repo checkout, and runtime `.env`.

The MacBook is the canonical dev Docker host for this machine. Do not use Docker Desktop on WSL/Windows for the dev stack.

## Stable Constants

| Constant | Value |
|---|---|
| SSH host | `macbook-docker` |
| Remote repo | `/Users/aroslav/Documents/rag-fresh` |
| Homebrew PATH | `/opt/homebrew/bin:/usr/local/bin:$PATH` |
| Compose files | `compose.yml:compose.dev.yml` |
| Docker host LAN IP | `192.168.31.168` |
| BGE-M3 memory default | `6G` (`BGE_M3_MEMORY_LIMIT=6G`) |

## Day-to-Day Workflow

Code in WSL, make changes available via git, fetch/pull on the MacBook repo, then run remote Make targets from WSL.

### Read-Only Diagnostics

```bash
# Remote hostname, git branch, Colima status, Docker/buildx versions
make remote-docker-status

# Render Compose services without printing secrets
make remote-compose-config

# Show Compose container names, status, and ports
make remote-docker-ps
```

### Environment Sync and Validation

```bash
# Copy WSL repo-root .env to the MacBook
make remote-env-sync

# Verify remote .env exists and required variables are present
make remote-env-check
```

`remote-env-check` reports missing variable **names only**; it never prints values.

Required variables (bot path):
- `TELEGRAM_BOT_TOKEN`
- `LITELLM_MASTER_KEY`
- At least one provider key: `CEREBRAS_API_KEY`, `GROQ_API_KEY`, or `OPENAI_API_KEY`

Required variables (ML profile, if Langfuse services are started):
- `NEXTAUTH_SECRET`
- `SALT`
- `ENCRYPTION_KEY`

### Start the Active Stack

```bash
# Start the development service set + bot container
make remote-active-up
```

The active set includes: `mini-app-frontend`, `mini-app-api`, `bge-m3`, `litellm`, `redis`, `langfuse`, `langfuse-worker`, `postgres`, `redis-langfuse`, `qdrant`, `rag-api`, `minio`, `clickhouse`, `user-base`, `bot`.

This enables profiles: `bot`, `ml`, and `voice` (if `rag-api` is included).

`make remote-full-up` is available as an explicit full-profile command, but `remote-active-up` is the default daily command.

### Bot Container Workflow

```bash
# Start the Compose bot container and required profile
make remote-bot-up

# Recreate the bot container after code/config changes
make remote-bot-restart

# Show recent bot logs without secret values
make remote-bot-logs
```

**Important**: `make bot` (native WSL helper) remains separate from the Docker bot. `make bot` runs the bot natively on WSL; `make remote-bot-up` runs it inside a Docker container on the MacBook. Only one process can poll a given Telegram bot token at a time.

### Service Health

```bash
# Check endpoints over SSH on the MacBook
make remote-service-health
```

Checks include:
- Qdrant readyz
- BGE-M3 health
- LiteLLM readiness
- Docling health (if started)
- Langfuse web or API health (if started)
- Bot container status and restart count

Optional services may report soft failures when they are not part of the selected stack. Required active-stack services are hard failures.

## `localhost` vs `192.168.31.168`

| Context | Address |
|---|---|
| MacBook service health over SSH | `127.0.0.1` (localhost on the MacBook) |
| WSL tests that call exposed ports | `192.168.31.168` (MacBook LAN IP, not WSL `localhost`) |
| Docker exec / container-name tests | Run over SSH in the MacBook repo |

## Test Boundary

| Test Type | Where to Run |
|---|---|
| Unit / lint / type-check / non-Docker integration | WSL (fast, no Docker needed) |
| Service-dependent WSL tests | Point to MacBook endpoints (`192.168.31.168`) |
| Docker exec, local volumes, Compose networks, container names | Over SSH on MacBook |

Example WSL test pointing at MacBook:

```bash
QDRANT_URL=http://192.168.31.168:6333 \
LITELLM_BASE_URL=http://192.168.31.168:4000 \
make test-bot-health
```

Example Docker-local test over SSH:

```bash
ssh macbook-docker 'cd ~/Documents/rag-fresh && export PATH=/opt/homebrew/bin:/usr/local/bin:$PATH; make test-smoke'
```

## Troubleshooting

### SSH Reachability / MacBook Asleep

- Ensure the MacBook is awake and on the same network.
- Verify `ssh macbook-docker` works from WSL.
- Check `~/.ssh/config` for the `macbook-docker` host entry.

### Colima Not Running

```bash
ssh macbook-docker 'colima status'
# If stopped:
ssh macbook-docker 'colima start --cpu 4 --memory 7'
```

### Buildx / BuildKit Issues

- Check `make remote-docker-status` for buildx version.
- If buildx fails, try: `ssh macbook-docker 'docker buildx create --use'`

### Stale Remote Repo / Branch

```bash
ssh macbook-docker 'cd ~/Documents/rag-fresh && git fetch && git status'
```

Ensure the MacBook repo is on the correct branch and up to date before starting services.

### `.env` Missing or Provider Key Group Missing

- Run `make remote-env-sync` to copy `.env` from WSL.
- Run `make remote-env-check` to see which variable names are missing.
- Never commit `.env` or print values in logs.

### Bot Restart Loops

```bash
make remote-bot-logs
```

Look for:
- Missing `TELEGRAM_BOT_TOKEN` or provider keys
- Redis auth mismatch
- Qdrant collection not found
- LiteLLM proxy not ready

### Health Mismatch Between Compose ps and Endpoints

- `make remote-docker-ps` may show `Up` while the endpoint is not yet ready.
- `make remote-service-health` checks actual endpoint responses.
- Some services (BGE-M3, Docling) have long warm-up times on first start.

### Fallback Fixture Token

The fallback fixture token in `tests/fixtures/compose.ci.env` is **intentionally invalid** for real bot runtime. It is safe for Compose rendering and local checks, but the bot container will fail to start unless `TELEGRAM_BOT_TOKEN` is set in the real `.env`.

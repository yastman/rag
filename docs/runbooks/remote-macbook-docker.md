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
| Homebrew PATH | `/opt/homebrew/bin:/usr/local/bin` |
| Compose files | `compose.yml:compose.dev.yml` |
| Docker host LAN IP | `192.168.31.168` |
| BGE-M3 memory default | `6G` (`BGE_M3_MEMORY_LIMIT=6G`) |

## Shell Alias

The `macbook` function (in `~/.zshrc`) adds Docker/Homebrew to PATH automatically:

```bash
macbook                     # interactive session with docker in PATH
macbook docker ps           # remote command with docker in PATH
```

No need to manually prefix `PATH=/opt/homebrew/bin:/usr/local/bin:$PATH` for interactive use. The Make targets already handle this internally for non-interactive SSH sessions.

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

For a leaner 8GB MacBook baseline, use:

```bash
make remote-local-down
make remote-bot-up
```

This keeps the runtime to `bot`, `litellm`, `redis`, `postgres`, `qdrant`, `user-base`, and `bge-m3`.

Start only the local-service subset without the bot:

```bash
make remote-local-up
```

Stop the remote stack:

```bash
make remote-local-down
```

Show recent compose logs:

```bash
make remote-local-logs
```

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
| WSL tests against default Compose ports | Run over SSH on the MacBook; default dev ports bind to MacBook `127.0.0.1` |
| WSL tests after intentionally publishing ports on the LAN | `192.168.31.168` (MacBook LAN IP, not WSL `localhost`) |
| Docker exec / container-name tests | Run over SSH in the MacBook repo |

If a compose override exposes ports on the MacBook LAN interface:

```bash
curl -fsS http://192.168.31.168:6333/readyz
curl -fsS http://192.168.31.168:4000/health/readiness
```

## Langfuse CLI

Langfuse traces, observations, and scores live in ClickHouse on the MacBook.
Use the `langfuse-cli` npm package (installed globally on the MacBook) to
inspect them from the terminal.

Works from WSL over SSH because the Langfuse Web UI port is bound to
`127.0.0.1:3001` on the MacBook (not exposed to LAN).

Default dev credentials: `pk-lf-dev` / `sk-lf-dev`.

```bash
# Quick: list recent traces
ssh macbook-docker 'LANGFUSE_BASE_URL=http://localhost:3001 \
  LANGFUSE_PUBLIC_KEY=pk-lf-dev \
  LANGFUSE_SECRET_KEY=sk-lf-dev \
  langfuse api traces list --limit 10'

# List observations, scores, prompts
ssh macbook-docker 'LANGFUSE_BASE_URL=http://localhost:3001 \
  LANGFUSE_PUBLIC_KEY=pk-lf-dev \
  LANGFUSE_SECRET_KEY=sk-lf-dev \
  langfuse api observations list --limit 10'

# Discover available resources and actions
ssh macbook-docker 'LANGFUSE_BASE_URL=http://localhost:3001 \
  LANGFUSE_PUBLIC_KEY=pk-lf-dev \
  LANGFUSE_SECRET_KEY=sk-lf-dev \
  langfuse api __schema'
ssh macbook-docker 'LANGFUSE_BASE_URL=http://localhost:3001 \
  LANGFUSE_PUBLIC_KEY=pk-lf-dev \
  LANGFUSE_SECRET_KEY=sk-lf-dev \
  langfuse api traces --help'
```

### Web UI

Forward the Langfuse Web UI port to the workstation:

```bash
ssh -L 3001:127.0.0.1:3001 macbook-docker
```

Then open <http://localhost:3001> in a browser.

## Test Boundary

| Test Type | Where to Run |
|---|---|
| Unit / lint / type-check / non-Docker integration | WSL (fast, no Docker needed) |
| Service-dependent tests against default Compose ports | Over SSH on MacBook |
| Docker exec, local volumes, Compose networks, container names | Over SSH on MacBook |

Run fast tests locally on the workstation:

```bash
make test-unit
make test
make lint
make type-check
```

Run service-dependent checks locally only after pointing service URLs at the
MacBook:

```bash
QDRANT_URL=http://192.168.31.168:6333 \
LITELLM_BASE_URL=http://192.168.31.168:4000 \
make test-bot-health
```

Example service-dependent test over SSH:

```bash
ssh macbook-docker 'cd /Users/aroslav/Documents/rag-fresh && export PATH=/opt/homebrew/bin:/usr/local/bin:$PATH; make test-bot-health'
```

Example Docker-local test over SSH:

```bash
ssh macbook-docker 'cd /Users/aroslav/Documents/rag-fresh && export PATH=/opt/homebrew/bin:/usr/local/bin:$PATH; make test-smoke'
```

## Environment

The remote Compose command uses `.env` on the MacBook when present and otherwise
falls back to `tests/fixtures/compose.ci.env`, matching the local Makefile
fallback model.

Remote Make targets set `BGE_M3_MEMORY_LIMIT=6G` by default. On an 8GB MacBook,
Colima can run near 7G, but giving Docker more memory is not a substitute for
keeping the active Compose profile small. macOS, the Colima VM, Docker daemon,
filesystem cache, and short encode spikes still need headroom. If the full stack
is required, run it temporarily and shut it down afterward.

The BGE model cache is the named Docker volume `dev_hf_cache`; keeping this
volume avoids repeated model downloads. Do not remove volumes during routine
cleanup unless you intentionally want to redownload models and rebuild local
state.

Do not print `.env` contents in logs or chat. It is safe to report missing
variable names.

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
ssh macbook-docker 'cd /Users/aroslav/Documents/rag-fresh && git fetch && git status'
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

### MacBook Memory Pressure

- Use `make remote-local-down && make remote-bot-up`, then check `docker stats --no-stream`.
- Do not leave `remote-full-up`, `remote-active-up`, `docker-ml-up`, `monitoring-up`,
  or voice services running as the default idle stack on an 8GB MacBook.

### Docker / Compose Issues

- Docker command is missing: the `macbook` shell function already handles PATH;
  if using raw `ssh macbook-docker`, prefix with `PATH=/opt/homebrew/bin:/usr/local/bin:$PATH`.
- Compose sees stale code: sync files to `/Users/aroslav/Documents/rag-fresh` on the
  MacBook before rebuilding or starting containers (e.g., `rsync` changed files).
- LiteLLM OOM / crash-loop: see [LITEllm_FAILURE.md](LITEllm_FAILURE.md). The
  dev memory override is in `compose.dev.yml` (1G for litellm).
- A workstation health check fails on `localhost`: retry with `192.168.31.168`.
  Note: most dev ports are bound to `127.0.0.1` (host-local), not exposed to LAN.

### Fallback Fixture Token

The fallback fixture token in `tests/fixtures/compose.ci.env` is **intentionally invalid** for real bot runtime. It is safe for Compose rendering and local checks, but the bot container will fail to start unless `TELEGRAM_BOT_TOKEN` is set in the real `.env`.

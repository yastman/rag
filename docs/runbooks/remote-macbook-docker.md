# Remote MacBook Docker

Use this runbook when the primary Windows/WSL workstation should stay free of
Docker runtime load and the MacBook should run the containers.

Canonical Docker service/profile/port truth stays in [`../../DOCKER.md`](../../DOCKER.md).
This page only describes the remote-host workflow.

## Model

- Primary workstation: code, git, Codex/IDE, `uv`, linting, fast tests.
- MacBook: Colima, Docker engine, Compose containers, images, volumes, networks.
- SSH host: `macbook-docker` (192.168.31.168).
- Remote repo path: `/Users/aroslav/Documents/rag-fresh`.
- Shell alias: `macbook` — wraps SSH with `/opt/homebrew/bin` in PATH (see below).

Compose commands run on the MacBook because bind mounts and build contexts must
exist on the Docker host.

## Shell Alias

The `macbook` function (in `~/.zshrc`) adds Docker/Homebrew to PATH automatically:

```bash
macbook                     # interactive session with docker in PATH
macbook docker ps           # remote command with docker in PATH
```

No need to manually prefix `PATH=/opt/homebrew/bin:/usr/local/bin:$PATH`. The
Make targets already handle this internally.

## Status

```bash
make remote-docker-status
make remote-compose-config
make remote-docker-ps
```

These commands use SSH and export the Homebrew path required by non-interactive
macOS sessions.

## Start And Stop

Start the lean bot/core stack on the MacBook:

```bash
make remote-local-down
make remote-bot-up
```

This is the recommended baseline for an 8GB MacBook. It keeps the runtime to
`bot`, `litellm`, `redis`, `postgres`, `qdrant`, `user-base`, and `bge-m3`.

Start only the normal local-service subset when you need the local helper
services without the bot:

```bash
make remote-local-up
```

Start the full profile stack only for short, focused checks:

```bash
make remote-full-up
```

Start the bot container separately when the core services are already running:

```bash
make remote-bot-up
```

Stop the remote stack:

```bash
make remote-local-down
```

Show recent logs:

```bash
make remote-local-logs
```

## Host Endpoints

When containers run on the MacBook, `localhost` from WSL is not the Docker host.
The default dev compose bindings are host-local on the MacBook, so the bundled
health target runs endpoint checks over SSH on the MacBook:

```bash
make remote-service-health
```

If a compose override exposes ports on the MacBook LAN interface, use:

```text
192.168.31.168
```

Examples:

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

## Tests

Run fast tests locally on the workstation:

```bash
make test-unit
make test
make lint
make type-check
```

Run service-dependent checks locally only after pointing service URLs at the
MacBook. For example:

```bash
QDRANT_URL=http://192.168.31.168:6333 \
LITELLM_BASE_URL=http://192.168.31.168:4000 \
make test-bot-health
```

Run tests on the MacBook over SSH when they depend on Docker-local behavior such
as Compose networks, `docker exec`, bind mounts, or volumes:

```bash
ssh macbook-docker 'cd ~/Documents/rag-fresh && export PATH=/opt/homebrew/bin:/usr/local/bin:$PATH; make test-smoke'
```

## Environment

The remote Compose command uses `.env` on the MacBook when present and otherwise
falls back to `tests/fixtures/compose.ci.env`, matching the local Makefile
fallback model.

Remote Make targets set `BGE_M3_MEMORY_LIMIT=4G` by default. BGE-M3 normally
uses roughly 3-3.5 GiB after warmup; keeping the limit at 4G prevents the model
service from consuming nearly the whole Colima memory budget.

On an 8GB MacBook, Colima can run near 7G, but giving Docker more memory is not
a substitute for keeping the active Compose profile small. macOS, the Colima VM,
Docker daemon, filesystem cache, and short encode spikes still need headroom.
If the full stack is required, run it temporarily and shut it down afterward.

The BGE model cache is the named Docker volume `dev_hf_cache`; keeping this
volume avoids repeated model downloads. Do not remove volumes during routine
cleanup unless you intentionally want to redownload models and rebuild local
state.

Do not print `.env` contents in logs or chat. It is safe to report missing
variable names.

## Troubleshooting

- MacBook memory pressure: use `make remote-local-down && make remote-bot-up`,
  then check `docker stats --no-stream`. Do not leave `remote-full-up`,
  `remote-active-up`, `docker-ml-up`, `monitoring-up`, or voice services running
  as the default idle stack on an 8GB MacBook.
- SSH fails: check that `macbook` (or `ssh macbook-docker`) works and the MacBook is awake.
- Docker command is missing: the `macbook` shell function already handles PATH; if
  using raw `ssh macbook-docker`, prefix with `PATH=/opt/homebrew/bin:/usr/local/bin:$PATH`.
- Colima is stopped: run `macbook colima start`.
- A workstation health check fails on `localhost`: retry with `192.168.31.168`.
  Note: most dev ports are bound to `127.0.0.1` (host-local), not exposed to LAN.
- LiteLLM OOM / crash-loop: see [LITEllm_FAILURE.md](LITEllm_FAILURE.md). The
  dev memory override is in `compose.dev.yml` (1G for litellm).
- Compose sees stale code: sync files to `/Users/aroslav/Documents/rag-fresh` on the
  MacBook before rebuilding or starting containers (e.g., `rsync` changed files).

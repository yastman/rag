# Docker Helper Assets

This directory contains configuration files, scripts, and initialization assets used by the Docker Compose runtime. It does **not** contain the Compose files themselves—see [`../compose.yml`](../compose.yml), [`../compose.dev.yml`](../compose.dev.yml), and [`../DOCKER.md`](../DOCKER.md) for service definitions and operations.

## Layout

### `litellm/`

LiteLLM Proxy configuration that defines the model routing, fallbacks, and provider aliases used by the bot and voice agent.

- **`config.yaml`** — Model list (Cerebras, Groq, OpenAI), fallback chains, rate limits, and key management. Referenced as a Compose ConfigMap/volume mount.

### `livekit/`

LiveKit server configuration for the voice-agent path.

- **`livekit.yaml`** — API keys, port bindings, and RTC settings. The `LIVEKIT_API_SECRET` is interpolated from environment at runtime.

### `monitoring/`

Observability stack configuration for local/dev alerting and log aggregation.

- **`loki.yaml`** — Loki log aggregation server config (filesystem storage, Ruler alerting).
- **`promtail.yaml`** — Promtail agent config that scrapes Docker container logs and pushes to Loki.
- **`alertmanager.yaml`** — Alertmanager routing and receivers (Telegram integration).
- **`rules/`** — Loki alerting rules:
  - `infrastructure.yaml`
  - `telegram-bot.yaml`
  - `ingestion.yaml`
  - `extended-services.yaml`

### `postgres/init/`

Database initialization scripts executed on first Postgres startup.

- **`00-init-databases.sql`** — Creates application databases.
- **`02-cocoindex.sql`** — CocoIndex ingestion schema.
- **`03-unified-ingestion-alter.sql`** — Unified ingestion extensions.
- **`04-voice-schema.sql`** — Voice agent transcript schema.
- **`05-realestate-schema.sql`** — Real-estate domain tables.
- **`06-lead-scoring-sync.sql`** — Lead scoring sync schema.
- **`07-nurturing-funnel-analytics.sql`** — Funnel analytics schema.
- **`08-user-favorites.sql`** — User favorites schema.

### `ingestion/`

Ingestion service wrapper assets.

- **`entrypoint.sh`** — Entrypoint script for the unified ingestion container.

## Validation

```bash
# Verify Compose still resolves all configs correctly
COMPOSE_DISABLE_ENV_FILE=1 docker compose --env-file tests/fixtures/compose.ci.env -f compose.yml -f compose.dev.yml --compatibility config > /dev/null

# Check image pins match running containers
make verify-compose-images
```

## See Also

- [`../DOCKER.md`](../DOCKER.md) — Full Compose operations guide.
- [`../docs/LOCAL-DEVELOPMENT.md`](../docs/LOCAL-DEVELOPMENT.md) — Local setup and validation.
- [`../docs/ALERTING.md`](../docs/ALERTING.md) — Loki/Alertmanager setup details.
- [`../services/README.md`](../services/README.md) — Service container index (bge-m3, docling, user-base).

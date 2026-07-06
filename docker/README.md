# Docker Helper Assets

This directory contains configuration files, scripts, and initialization assets used by the Docker Compose runtime. It does **not** contain the Compose files themselves—see [`../compose.yml`](../compose.yml), [`../compose.dev.yml`](../compose.dev.yml), and [`../DOCKER.md`](../DOCKER.md) for service definitions and operations.

## Layout

### `qdrant/`

Qdrant vector-store configuration mounted into the `qdrant` container.

- **`config.yaml`** — storage, quantization, and service settings.

### `postgres/init/`

Database initialization scripts executed on first Postgres startup.

- **`00-init-databases.sql`** — Creates application databases.
- **`02-cocoindex.sql`** — Legacy CocoIndex schema (CocoIndex removed; script retained for existing volumes).
- **`03-unified-ingestion-alter.sql`** — Unified ingestion extensions.
- **`04-voice-schema.sql`** — Voice transcript schema.
- **`05-realestate-schema.sql`** — Real-estate domain tables.
- **`08-user-favorites.sql`** — User favorites schema.
- **`09-drop-orphaned-scheduler-voice-tables.sql`** — Drops orphaned scheduler/voice tables.

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
- [`../services/README.md`](../services/README.md) — Service container index (bge-m3).

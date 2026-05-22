# scripts/probe/

Health check probe scripts for bot and VPS release validation.

These shell scripts verify that runtime prerequisites (Redis, Qdrant, LiteLLM,
Docker services) are healthy before or after deployment. They are operational
probes, not pytest tests.

## Contents

| Script | Purpose |
|--------|---------|
| `bot_health.sh` | Local bot preflight: checks Redis, Qdrant, LiteLLM, and optional Postgres |
| `release_health_vps.sh` | VPS release smoke: validates service health post-deploy |

## Running

```bash
# Local bot health preflight
./scripts/probe/bot_health.sh

# VPS release smoke (typically run on the VPS host)
./scripts/probe/release_health_vps.sh
```

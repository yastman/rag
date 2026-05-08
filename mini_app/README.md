# Mini App

Telegram Mini App backend and frontend for the FortNoks real-estate workflow.

## Purpose

Provides a web UI inside Telegram for users to start expert chats, submit phone leads, and retrieve UI configuration. The backend is a FastAPI service; the frontend is a React + Vite SPA served by nginx.

## Backend

- **Entrypoint**: [`api.py`](api.py)
- **Dockerfile**: [`Dockerfile`](Dockerfile)
- **Service name**: `mini-app-api`
- **Profile**: — (default, unprofiled)
- **Compose project**: `dev` (see [`../DOCKER.md`](../DOCKER.md) for contract details)
- **Local port**: `8090` (mapped in `compose.dev.yml`)
- **Health**: `GET http://localhost:8090/health`

### API Surface

| Endpoint | Method | Description |
|---|---|---|
| `/api/config` | GET | UI questions + experts list |
| `/api/start-expert` | POST | Store deep-link payload and return `start_link` |
| `/api/phone` | POST | Collect phone and create CRM lead |
| `/api/log` | POST | Frontend remote logging sink |
| `/health` | GET | Service health |

### Quick Start

```bash
COMPOSE_FILE=compose.yml:compose.dev.yml docker compose up -d mini-app-api
curl -fsS http://localhost:8090/health
```

## Frontend

See [`frontend/README.md`](frontend/README.md).

## Tests & Checks

```bash
# Backend unit tests
uv run pytest tests/unit/mini_app/ tests/unit/test_bot_mini_app.py tests/unit/test_mini_app_dockerfile_build_deps.py -v

# Frontend unit tests
cd mini_app/frontend && npm run test
```

## Owner Boundaries

- **Backend**: FastAPI app, Redis pub/sub bridge to the bot, CRM phone lead submission
- **Frontend**: React SPA, Telegram Mini App SDK integration, static build consumed by `mini-app-frontend` container

Do not change the exposed port (`8090`), healthcheck path, or API response shapes without updating the frontend callers and Compose health checks.

## See Also

- [`frontend/README.md`](frontend/README.md) — Frontend build, dev server, and test details
- [`../DOCKER.md`](../DOCKER.md) — Compose operations and service map
- [`../docs/LOCAL-DEVELOPMENT.md`](../docs/LOCAL-DEVELOPMENT.md) — Local setup and validation ladder
- [`../docs/runbooks/README.md`](../docs/runbooks/README.md) — Operational troubleshooting

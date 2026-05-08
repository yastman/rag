# Mini App Frontend

React + Vite SPA for the Telegram Mini App.

## Purpose

Renders the expert-selection UI, deep-link flow, and phone-capture form inside Telegram. Built as static assets and served by nginx in the `mini-app-frontend` container.

## Entrypoint

- **Application**: [`src/main.tsx`](src/main.tsx)
- **Dockerfile**: [`Dockerfile`](Dockerfile)
- **Nginx config**: [`nginx.conf`](nginx.conf)

## Docker

- **Service name**: `mini-app-frontend`
- **Profile**: — (default, unprofiled)
- **Compose project**: `dev` (see [`../../DOCKER.md`](../../DOCKER.md) for contract details)
- **Local port**: `8091` (host) mapped from container port `80`
- **Health**: `GET http://localhost:8091/health` (nginx internal)
- **Runtime security**: runs as `uid:gid 101:101` with `cap_drop: [ALL]` and only `cap_add: [NET_BIND_SERVICE]`
- **Writable runtime paths**: nginx PID and temp/cache paths are rooted directly under `/tmp/*`

## Local Development

```bash
cd mini_app/frontend
npm ci
npm run dev        # Vite dev server (proxies /api to localhost:8090)
npm run build      # Production build → dist/
npm run test       # Vitest unit tests
```

## Tests & Checks

```bash
# Frontend unit tests (vitest)
npm run test

# Dockerfile / runtime contract tests
uv run pytest tests/unit/mini_app/test_frontend_runtime_contract.py -v
uv run pytest tests/unit/test_mini_app_dockerfile_build_deps.py -v
```

## Owner Boundaries

- React component tree, state management (Zustand), routing
- Telegram Mini App SDK integration (`@tma.js/sdk-react`)
- Build artifact generation and nginx static serving

Do not change the build output directory (`dist/`), nginx listen port, or healthcheck path without updating the `mini-app-frontend` Compose service.

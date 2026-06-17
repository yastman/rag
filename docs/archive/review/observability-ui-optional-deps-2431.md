# Observability and heavy UI dependency audit (#2431)

## Result

The root runtime dependency set keeps observability and heavy UI packages out of
base installs. They are available through explicit extras and development tools
only.

## Optional extras

- `observability`: `langfuse`, `sentry-sdk`
- `scheduling`: `apscheduler`
- `ui`: `pillow`, `gradio`

## Compose profile

The self-hosted Langfuse stack remains profile-gated under the existing `ml`
profile in `compose.dev.yml`:

- `clickhouse`
- `minio`
- `redis-langfuse`
- `langfuse-worker`
- `langfuse`

## Base install contract

`uv sync --no-dev` should not install `langfuse`, `sentry-sdk`, `apscheduler`,
`pillow`, or `gradio` unless an optional extra is selected.

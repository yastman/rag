# Monitoring

## Purpose
Navigation index for the folder. Use this page to quickly find files and route into this part of the project.

## Scope
docker/monitoring

## Contents
- `alloy.alloy` - Grafana Alloy log collector configuration (active)
- `alertmanager.yaml` - Alertmanager routing and receivers
- `loki.yaml` - Loki log aggregation configuration
- `promtail.yaml` - **DEPRECATED** Promtail configuration (retained for backward compatibility)
- `rules/` - LogQL alert rules for Loki

## Alloy Migration

Grafana Alloy replaces Promtail as the log collector for the RAG stack.
Promtail reached its Grafana-documented end-of-life in 2025 and will not receive
further updates. Alloy provides the same Docker log collection capabilities with
active maintenance and a unified configuration model.

### What changed

- **New collector**: `alloy` service in `compose.yml` (profile: `obs`).
- **Deprecated**: `promtail` service remains in compose for short-lived backward
  compatibility but should not be used for new deployments.
- **Config file**: `docker/monitoring/alloy.alloy` uses River-style HCL syntax
  instead of YAML.

### Stable label selectors in alert rules

All alert rules under `rules/` now use `{service="..."}` selectors derived from
the Docker Compose `com.docker.compose.service` label. The previous
`{container="dev-*"}` patterns were brittle and broke when the compose project
name changed.

Both Alloy and Promtail extract the `service` label from the same Docker metadata,
so rules work regardless of which collector is active.

## Parent
- [..](..)

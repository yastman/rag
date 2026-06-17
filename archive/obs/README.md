# Archived: Observability Stack (loki/promtail/alertmanager)

Archived as part of monolith-archival epic #2596 (issue #2599).

These configs were previously used with the `obs` Docker Compose profile.
The `loki`, `promtail`, and `alertmanager` services have been removed from
`compose.yml` and `compose.dev.yml`. The `docker-obs-up` and `monitoring-*`
Makefile targets have been removed.

Retained here for reference only. Not part of the active runtime.

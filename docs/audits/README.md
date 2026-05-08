# Audits

This directory contains timestamped operational and documentation audits. Audit files are evidence snapshots: use them to understand what was observed at a point in time, then verify current behavior against live code, config, logs, or service state.

## Recent Operational Audits

- [2026-05-08 - Telethon Langfuse runtime loop audit](2026-05-08-telethon-langfuse-runtime-loop.md)
- [2026-05-05 - Langfuse recent traces structure audit](2026-05-05-langfuse-recent-traces-structure-audit.md)
- [2026-05-05 - Langfuse Telethon trace audit](2026-05-05-langfuse-telethon-trace-audit.md)
- [2026-05-05 - Langfuse trace 8d79036a audit](2026-05-05-langfuse-trace-8d79036a-audit.md)
- [2026-05-07 - Docker Langfuse health audit](2026-05-07-docker-langfuse-health-audit.md)
- [2026-05-07 - Langfuse real env OTEL fix](2026-05-07-langfuse-real-env-otel-fix.md)
- [2026-05-07 - Telegram bot logs audit](2026-05-07-telegram-bot-logs-audit.md)

## When To Use

Start here when investigating repeated runtime failures, trace anomalies, Docker/Langfuse health drift, or Telegram bot log incidents. For operational commands and live investigation flow, use [runbooks](../runbooks/README.md) first.

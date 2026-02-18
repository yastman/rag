# Alerting

Monitoring and alerting stack for local/dev runtime:
- Loki (log storage + ruler)
- Promtail (Docker log collector)
- Alertmanager (routing to Telegram)

## Config Files

- `docker/monitoring/loki.yaml`
- `docker/monitoring/promtail.yaml`
- `docker/monitoring/alertmanager.yaml`
- `docker/monitoring/rules/*.yaml`

Rule groups currently tracked include:
- `telegram-bot.yaml`
- `infrastructure.yaml`
- `ingestion.yaml`
- `extended-services.yaml`

## Start And Validate

```bash
make monitoring-up
make monitoring-status
```

Health checks:

```bash
curl -fsS http://localhost:3100/ready
curl -fsS http://localhost:9093/-/healthy
```

## Telegram Delivery Setup

Set in `.env`:

```bash
TELEGRAM_ALERTING_BOT_TOKEN=...
TELEGRAM_ALERTING_CHAT_ID=...
```

Then send a test alert:

```bash
make monitoring-test-alert
```

## Useful Operations

```bash
make monitoring-logs
make monitoring-down
```

Query Loki directly:

```bash
curl -G 'http://localhost:3100/loki/api/v1/query_range' \
  --data-urlencode 'query={container="dev-bot"} |~ "(?i)error"' \
  --data-urlencode 'limit=100'
```

## Troubleshooting

- No Telegram notifications:
  - verify both `TELEGRAM_ALERTING_*` vars in `.env`
  - check `docker logs dev-alertmanager`
- No logs in Loki:
  - check Promtail access to Docker socket and container log path
- Rules not loaded:
  - ensure rules are mounted to `/etc/loki/rules/fake` (as in compose)

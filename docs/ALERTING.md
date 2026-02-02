# Alerting Setup Guide

This guide explains how to set up the monitoring and alerting stack for the RAG Bot development environment.

## Architecture Overview

```
Docker Containers → Promtail → Loki → Alertmanager → Telegram Bot
        ↓                              ↓
   (scrape logs)              (evaluate rules)
                                       ↓
                               (send alerts)
```

| Component | Purpose | Port |
|-----------|---------|------|
| Promtail | Scrapes Docker container logs | 9080 |
| Loki | Log aggregation and rule evaluation | 3100 |
| Alertmanager | Alert routing and deduplication | 9093 |

## Quick Start

### 1. Create Alerting Telegram Bot

1. Open Telegram and message [@BotFather](https://t.me/BotFather)
2. Send `/newbot` and follow the prompts
3. Name it something like "RAG Alerts" or "Dev Alerts"
4. Save the bot token (format: `123456789:ABCdefGHIjklMNOpqrSTUvwxYZ`)

### 2. Get Your Chat ID

**For personal alerts:**
1. Message [@userinfobot](https://t.me/userinfobot)
2. It will reply with your numeric chat ID

**For group alerts:**
1. Create a Telegram group
2. Add your alerting bot to the group
3. Add [@userinfobot](https://t.me/userinfobot) to get the group chat ID
4. Group IDs are negative numbers (e.g., `-1001234567890`)

### 3. Configure Environment

Add to your `.env` file:

```bash
# Alerting
TELEGRAM_ALERTING_BOT_TOKEN=123456789:ABCdefGHIjklMNOpqrSTUvwxYZ
TELEGRAM_ALERTING_CHAT_ID=-1001234567890
```

### 4. Start Monitoring Stack

```bash
# Start just monitoring services
make monitoring-up

# Or start full dev stack (includes monitoring)
docker compose -f docker-compose.dev.yml up -d
```

### 5. Verify Setup

```bash
# Check service status
make monitoring-status

# Send test alert
make monitoring-test-alert
```

## Make Targets

| Target | Description |
|--------|-------------|
| `make monitoring-up` | Start Loki, Promtail, Alertmanager |
| `make monitoring-down` | Stop monitoring stack |
| `make monitoring-logs` | View monitoring logs (live) |
| `make monitoring-status` | Check health of monitoring services |
| `make monitoring-test-alert` | Send test alert to Telegram |

## Alert Rules

Alert rules are defined in `docker/monitoring/rules/`:

### telegram-bot.yaml
Monitors the Telegram bot service:
- Container down
- High error rate
- Critical errors
- Telegram API errors
- Query processing errors
- LLM generation errors
- Cache errors
- Slow responses

### infrastructure.yaml
Monitors infrastructure services:
- Qdrant (down, errors, slow queries)
- Redis (down, memory, connections)
- LiteLLM (down, rate limits, provider errors)
- Langfuse (down, worker, errors)
- Embedding services (BGE-M3, BM42)
- Databases (PostgreSQL, ClickHouse)

### Extended Services (extended-services.yaml)
Monitors additional development services:

| Service | Alert | Severity | Trigger |
|---------|-------|----------|---------|
| dev-docling | DoclingDown | critical | No logs 10min |
| dev-docling | DoclingOOM | critical | OOM/crash detected |
| dev-docling | DoclingConversionFailed | warning | Conversion errors (>2 in 5min) |
| dev-docling | DoclingError | warning | Errors (>3 in 5min) |
| dev-minio | MinioDown | critical | No logs 5min |
| dev-minio | MinioDiskFull | critical | Disk full or offline |
| dev-minio | MinioCorruption | critical | Data corruption/auth error |
| dev-minio | MinioHealingFailed | warning | Drive init/healing failed |
| dev-minio | MinioError | warning | Errors (>5 in 5min) |
| dev-mlflow | MLflowDown | critical | No logs 5min |
| dev-mlflow | MLflowDBError | critical | Database connection error |
| dev-mlflow | MLflowError | warning | Errors (>3 in 5min) |
| dev-redis-langfuse | RedisLangfuseDown | critical | No logs 5min |
| dev-redis-langfuse | RedisLangfuseConnectionError | critical | Connection refused/readonly |
| dev-redis-langfuse | RedisLangfuseMemory | warning | Memory pressure/eviction |
| dev-lightrag | LightRAGDown | critical | No logs 10min |
| dev-lightrag | LightRAGError | warning | Errors (>3 in 5min) |
| dev-lightrag | LightRAGAPIError | warning | API errors (rate limits) |

## Alert Severity Levels

| Severity | Timing | Description |
|----------|--------|-------------|
| `critical` | 10s wait, 1h repeat | Service down, fatal errors |
| `warning` | 1m wait, 4h repeat | Errors, degradation |
| `info` | 5m wait, 12h repeat | Informational (restarts, fallbacks) |

## Querying Logs

Access Loki directly for log queries:

```bash
# Query recent bot errors
curl -G 'http://localhost:3100/loki/api/v1/query_range' \
  --data-urlencode 'query={container="dev-bot"} |~ "error"' \
  --data-urlencode 'limit=100'
```

Or use Grafana (if installed) connected to Loki at `http://loki:3100`.

## Troubleshooting

### Alerts not sending

1. Check Alertmanager is running: `curl http://localhost:9093/-/healthy`
2. Verify env vars are set: `echo $TELEGRAM_ALERTING_BOT_TOKEN`
3. Check Alertmanager logs: `docker logs dev-alertmanager`
4. Verify bot token with Telegram API:
   ```bash
   curl "https://api.telegram.org/bot$TELEGRAM_ALERTING_BOT_TOKEN/getMe"
   ```

### Promtail not scraping logs

1. Check Promtail can access Docker socket
2. Verify container name pattern matches `dev-*`
3. Check Promtail logs: `docker logs dev-promtail`

### Loki not receiving logs

1. Check Loki is ready: `curl http://localhost:3100/ready`
2. Verify Promtail→Loki connection in Promtail logs
3. Check Loki storage permissions

## Configuration Files

| File | Purpose |
|------|---------|
| `docker/monitoring/loki.yaml` | Loki configuration (storage, retention, ruler) |
| `docker/monitoring/promtail.yaml` | Promtail scrape config (Docker logs) |
| `docker/monitoring/alertmanager.yaml` | Alertmanager routing and receivers |
| `docker/monitoring/rules/*.yaml` | Alert rules (LogQL queries) |

## Customizing Alerts

To add new alert rules, edit files in `docker/monitoring/rules/`:

```yaml
groups:
  - name: my-alerts
    rules:
      - alert: MyCustomAlert
        expr: |
          count_over_time({container="dev-myservice"} |~ "specific error" [5m]) > 3
        for: 3m
        labels:
          severity: warning
          service: myservice
        annotations:
          summary: "My custom alert triggered"
          description: "Specific error occurred more than 3 times in 5 minutes"
```

After editing, restart Loki to reload rules:
```bash
docker compose -f docker-compose.dev.yml restart loki
```

## Security Notes

- The alerting bot token is separate from the main bot token
- Never commit actual tokens to version control
- Use environment variables or secrets management
- The alerting bot should have minimal permissions (just send messages)

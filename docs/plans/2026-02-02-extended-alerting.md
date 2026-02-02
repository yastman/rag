# Extended Alerting Coverage Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add monitoring alerts for 5 missing Docker services (docling, minio, mlflow, redis-langfuse, lightrag) and configure Telegram notifications.

**Architecture:** Create new Loki alert rules file with service-specific patterns. Update .env with Telegram credentials. Restart monitoring stack to apply.

**Tech Stack:** Loki LogQL, Alertmanager, Telegram Bot API

---

## Task 1: Create Extended Services Alert Rules

**Files:**
- Create: `docker/monitoring/rules/extended-services.yaml`

**Step 1: Create the alert rules file**

```yaml
# Alert Rules for Extended Services
# Monitors: docling, minio, mlflow, redis-langfuse, lightrag

groups:
  - name: extended-services
    interval: 1m
    rules:
      # =========================================================================
      # DEV-DOCLING (Critical - Ingestion Pipeline)
      # =========================================================================

      - alert: DoclingDown
        expr: absent(count_over_time({container="dev-docling"} [10m]))
        for: 2m
        labels:
          severity: critical
          service: docling
        annotations:
          summary: "Docling document parser is down"
          description: "No logs from dev-docling for 10 minutes - ingestion blocked"

      - alert: DoclingOOM
        expr: count_over_time({container="dev-docling"} |~ "(?i)killed|out of memory|oom|segmentation fault" [5m]) > 0
        for: 0m
        labels:
          severity: critical
          service: docling
        annotations:
          summary: "Docling OOM/crash detected"
          description: "Docling killed by OOM or segfault"

      - alert: DoclingConversionFailed
        expr: count_over_time({container="dev-docling"} |~ "(?i)failed to convert|conversion failed|pdf.*error|ocr.*error|timeout" [5m]) > 2
        for: 3m
        labels:
          severity: warning
          service: docling
        annotations:
          summary: "Docling conversion errors"
          description: "Multiple document conversion failures"

      - alert: DoclingError
        expr: count_over_time({container="dev-docling"} |~ "(?i)error|exception|traceback" [5m]) > 3
        for: 3m
        labels:
          severity: warning
          service: docling
        annotations:
          summary: "Docling errors detected"
          description: "Multiple errors in Docling logs"

      # =========================================================================
      # DEV-MINIO (Critical - Langfuse Storage)
      # =========================================================================

      - alert: MinioDown
        expr: absent(count_over_time({container="dev-minio"} [5m]))
        for: 2m
        labels:
          severity: critical
          service: minio
        annotations:
          summary: "MinIO S3 storage is down"
          description: "No logs from dev-minio - Langfuse storage broken"

      - alert: MinioDiskFull
        expr: count_over_time({container="dev-minio"} |~ "(?i)disk full|no space left|drive offline" [5m]) > 0
        for: 0m
        labels:
          severity: critical
          service: minio
        annotations:
          summary: "MinIO disk full or offline"
          description: "MinIO storage critically low or unavailable"

      - alert: MinioCorruption
        expr: count_over_time({container="dev-minio"} |~ "(?i)corrupt|AccessDenied|signature mismatch" [5m]) > 0
        for: 1m
        labels:
          severity: critical
          service: minio
        annotations:
          summary: "MinIO data corruption or auth error"
          description: "MinIO reporting corruption or access issues"

      - alert: MinioHealingFailed
        expr: count_over_time({container="dev-minio"} |~ "(?i)failed to initialize|unable to use drive|healing.*failed" [5m]) > 0
        for: 3m
        labels:
          severity: warning
          service: minio
        annotations:
          summary: "MinIO healing/init failed"
          description: "MinIO drive initialization or healing problems"

      - alert: MinioError
        expr: count_over_time({container="dev-minio"} |~ "(?i)error|exception" [5m]) > 5
        for: 5m
        labels:
          severity: warning
          service: minio
        annotations:
          summary: "MinIO errors detected"
          description: "Multiple errors in MinIO logs"

      # =========================================================================
      # DEV-MLFLOW (Critical - Experiment Tracking)
      # =========================================================================

      - alert: MLflowDown
        expr: absent(count_over_time({container="dev-mlflow"} [5m]))
        for: 2m
        labels:
          severity: critical
          service: mlflow
        annotations:
          summary: "MLflow is down"
          description: "No logs from dev-mlflow - experiment tracking unavailable"

      - alert: MLflowDBError
        expr: count_over_time({container="dev-mlflow"} |~ "(?i)OperationalError|migration|failed to connect|psycopg" [5m]) > 0
        for: 1m
        labels:
          severity: critical
          service: mlflow
        annotations:
          summary: "MLflow database error"
          description: "MLflow cannot connect to PostgreSQL"

      - alert: MLflowError
        expr: count_over_time({container="dev-mlflow"} |~ "(?i)error|exception|traceback" [5m]) > 3
        for: 3m
        labels:
          severity: warning
          service: mlflow
        annotations:
          summary: "MLflow errors detected"
          description: "Multiple errors in MLflow logs"

      # =========================================================================
      # DEV-REDIS-LANGFUSE (Critical - Langfuse Queue)
      # =========================================================================

      - alert: RedisLangfuseDown
        expr: absent(count_over_time({container="dev-redis-langfuse"} [5m]))
        for: 2m
        labels:
          severity: critical
          service: redis-langfuse
        annotations:
          summary: "Redis Langfuse is down"
          description: "No logs from dev-redis-langfuse - Langfuse queue broken"

      - alert: RedisLangfuseConnectionError
        expr: count_over_time({container="dev-redis-langfuse"} |~ "(?i)connection.*refused|connection.*error|READONLY" [5m]) > 0
        for: 1m
        labels:
          severity: critical
          service: redis-langfuse
        annotations:
          summary: "Redis Langfuse connection error"
          description: "Redis Langfuse refusing connections or readonly"

      - alert: RedisLangfuseMemory
        expr: count_over_time({container="dev-redis-langfuse"} |~ "(?i)maxmemory|evict|oom" [5m]) > 0
        for: 1m
        labels:
          severity: warning
          service: redis-langfuse
        annotations:
          summary: "Redis Langfuse memory pressure"
          description: "Redis Langfuse memory eviction detected"

      # =========================================================================
      # DEV-LIGHTRAG (Critical - Graph RAG)
      # =========================================================================

      - alert: LightRAGDown
        expr: absent(count_over_time({container="dev-lightrag"} [10m]))
        for: 3m
        labels:
          severity: critical
          service: lightrag
        annotations:
          summary: "LightRAG is down"
          description: "No logs from dev-lightrag - graph retrieval unavailable"

      - alert: LightRAGError
        expr: count_over_time({container="dev-lightrag"} |~ "(?i)error|exception|failed|traceback" [5m]) > 3
        for: 3m
        labels:
          severity: warning
          service: lightrag
        annotations:
          summary: "LightRAG errors detected"
          description: "Multiple errors in LightRAG logs"

      - alert: LightRAGAPIError
        expr: count_over_time({container="dev-lightrag"} |~ "(?i)openai.*error|api.*error|rate.*limit" [5m]) > 2
        for: 3m
        labels:
          severity: warning
          service: lightrag
        annotations:
          summary: "LightRAG API errors"
          description: "LightRAG having issues with OpenAI API"
```

**Step 2: Verify YAML syntax**

Run: `python -c "import yaml; yaml.safe_load(open('docker/monitoring/rules/extended-services.yaml'))"`
Expected: No output (valid YAML)

**Step 3: Commit the rules file**

```bash
git add docker/monitoring/rules/extended-services.yaml
git commit -m "feat(monitoring): add alert rules for docling, minio, mlflow, redis-langfuse, lightrag"
```

---

## Task 2: Configure Telegram Credentials

**Files:**
- Modify: `.env`

**Step 1: Add Telegram alerting credentials to .env**

Add these lines:
```bash
# Alerting (Telegram)
TELEGRAM_ALERTING_BOT_TOKEN=7546342785:AAEuuFw8nAZCEEf6Ye6gFybszW5a9ok2ZQI
TELEGRAM_ALERTING_CHAT_ID=7933283409
```

**Step 2: Verify .env has the values**

Run: `grep TELEGRAM_ALERTING .env`
Expected:
```
TELEGRAM_ALERTING_BOT_TOKEN=7546342785:AAEuuFw8nAZCEEf6Ye6gFybszW5a9ok2ZQI
TELEGRAM_ALERTING_CHAT_ID=7933283409
```

**Note:** Do NOT commit .env (it's in .gitignore)

---

## Task 3: Restart Monitoring Stack

**Step 1: Restart monitoring containers to load new rules**

Run: `docker compose -f docker-compose.dev.yml restart loki alertmanager`
Expected: Both containers restart successfully

**Step 2: Verify Loki loaded the new rules**

Run: `curl -s http://localhost:3100/loki/api/v1/rules | jq '.data.groups[].name'`
Expected: Should include `"extended-services"`

**Step 3: Verify Alertmanager has Telegram configured**

Run: `curl -s http://localhost:9093/api/v2/status | jq '.config.original'`
Expected: Should contain `telegram_configs` with your bot token

---

## Task 4: Test Alerting End-to-End

**Step 1: Send test alert via Alertmanager API**

Run:
```bash
curl -X POST http://localhost:9093/api/v2/alerts \
  -H "Content-Type: application/json" \
  -d '[{
    "labels": {
      "alertname": "TestExtendedAlerting",
      "severity": "info",
      "service": "test"
    },
    "annotations": {
      "summary": "Test alert from extended-services setup",
      "description": "If you see this in Telegram, alerting is working!"
    }
  }]'
```
Expected: Empty response `[]` or success status

**Step 2: Check Telegram for the test alert**

Expected: Message in chat 7933283409 with "TestExtendedAlerting"

**Step 3: Verify alert shows in Alertmanager UI**

Run: `curl -s http://localhost:9093/api/v2/alerts | jq '.[].labels.alertname'`
Expected: `"TestExtendedAlerting"`

---

## Task 5: Document in ALERTING.md

**Files:**
- Modify: `docs/ALERTING.md`

**Step 1: Add extended services section**

Add to the "Alert Rules" section:
```markdown
### Extended Services (extended-services.yaml)

| Service | Alert | Severity | Trigger |
|---------|-------|----------|---------|
| dev-docling | DoclingDown | critical | No logs 10min |
| dev-docling | DoclingOOM | critical | OOM/segfault |
| dev-docling | DoclingConversionFailed | warning | >2 conversion errors |
| dev-docling | DoclingError | warning | >3 errors |
| dev-minio | MinioDown | critical | No logs 5min |
| dev-minio | MinioDiskFull | critical | Disk full/offline |
| dev-minio | MinioCorruption | critical | Corruption/auth |
| dev-minio | MinioHealingFailed | warning | Healing failed |
| dev-minio | MinioError | warning | >5 errors |
| dev-mlflow | MLflowDown | critical | No logs 5min |
| dev-mlflow | MLflowDBError | critical | DB connection |
| dev-mlflow | MLflowError | warning | >3 errors |
| dev-redis-langfuse | RedisLangfuseDown | critical | No logs 5min |
| dev-redis-langfuse | RedisLangfuseConnectionError | critical | Conn refused/readonly |
| dev-redis-langfuse | RedisLangfuseMemory | warning | Memory pressure |
| dev-lightrag | LightRAGDown | critical | No logs 10min |
| dev-lightrag | LightRAGError | warning | >3 errors |
| dev-lightrag | LightRAGAPIError | warning | OpenAI API errors |
```

**Step 2: Commit documentation**

```bash
git add docs/ALERTING.md
git commit -m "docs(alerting): add extended services alert rules reference"
```

---

## Summary

| Task | Files | Purpose |
|------|-------|---------|
| 1 | `docker/monitoring/rules/extended-services.yaml` | 18 new alert rules |
| 2 | `.env` | Telegram credentials |
| 3 | - | Restart monitoring stack |
| 4 | - | End-to-end test |
| 5 | `docs/ALERTING.md` | Documentation |

**Total new alerts:** 18 rules for 5 services
**Credentials:** Bot `7546342785`, Chat `7933283409`

# 🚀 VPS Quick Start Guide

> **Для работы на production сервере** `/home/admin/contextual_rag`

**Дата:** 2025-01-06
**Версия:** v2.8.0
**Статус:** 95% Production-Ready

---

## 📋 Checklist перед началом

### 1. Проверка текущего состояния

```bash
# SSH на сервер
ssh admin@your-server-ip

# Переход в проект
cd /home/admin/contextual_rag

# Проверка Git
git status
git log --oneline -5

# Pull последних изменений
git pull origin main
```

### 2. Проверка running сервисов

```bash
# Проверить Docker контейнеры
docker ps
# Ожидается: Qdrant (6333), Redis (6379)

# Проверить systemd services
systemctl status telegram-bot
# Или если в Docker:
docker ps | grep telegram-bot

# Проверить порты
netstat -tlnp | grep -E "6333|6379|8001|5000|3001"
```

### 3. Проверка работоспособности

```bash
***REMOVED***
curl http://localhost:6333/collections
# Ожидается: JSON со списком коллекций

# Redis
redis-cli ping
# Ожидается: PONG

# BGE-M3 API (если есть)
curl http://localhost:8001/health
# Ожидается: {"status": "ok"}

# MLflow (если есть)
curl http://localhost:5000
# Ожидается: HTML страница

# Telegram Bot logs
journalctl -u telegram-bot -f
# Или: docker logs telegram-bot -f
```

---

## 🎯 Приоритетные задачи на сервере

### 🔴 Priority 1: Must Deploy (Критические)

#### S1. Deploy BGE-M3 as FastAPI Service
**Время:** 2-3 часа
**Зачем:** Embeddings service должен работать 24/7

```bash
# Location: создать src/services/bge_m3_api.py
# Port: 8001
# Docker: создать docker/bge-m3/Dockerfile

Actions:
1. Создать FastAPI app с endpoint /embed
2. Load BGE-M3 model один раз при старте
3. Health check endpoint /health
4. Dockerfile с CUDA support (если GPU есть)
5. docker-compose integration

Test:
curl -X POST http://localhost:8001/embed \
  -H "Content-Type: application/json" \
  -d '{"texts": ["test query"]}'
```

**Status:** ⏳ BOT config ссылается на localhost:8001, но сервис не running

---

#### S2. Deploy MLflow Server
**Время:** 1 час
**Зачем:** Experiment tracking + Model registry

```bash
# Install
pip install mlflow

# Run with SQLite backend
mlflow server \
  --backend-store-uri sqlite:///mlflow.db \
  --default-artifact-root ./mlruns \
  --host 0.0.0.0 \
  --port 5000

# Or with systemd:
sudo cp mlflow.service /etc/systemd/system/
sudo systemctl enable mlflow
sudo systemctl start mlflow

# Verify
curl http://localhost:5000
```

**Status:** ⏳ Referenced in code but unclear if running

---

#### S3. Deploy Langfuse Server
**Время:** 1 час
**Зачем:** LLM tracing and cost tracking

```bash
# Docker deployment
docker run -d \
  --name langfuse \
  -p 3001:3000 \
  -e DATABASE_URL=postgresql://... \
  -e NEXTAUTH_SECRET=$(openssl rand -base64 32) \
  langfuse/langfuse:latest

# Or docker-compose (см. ниже)

# Verify
curl http://localhost:3001
```

**Status:** ⏳ Code integration exists, server status unknown

---

### 🟡 Priority 2: Should Deploy (Важные)

#### S4. Prometheus + Grafana Monitoring
**Время:** 2-3 часа

```bash
# docker-compose.monitoring.yml
services:
  prometheus:
    image: prom/prometheus
    ports: [9090:9090]
    volumes:
      - ./prometheus.yml:/etc/prometheus/prometheus.yml

  grafana:
    image: grafana/grafana
    ports: [3000:3000]
    volumes:
      - grafana-storage:/var/lib/grafana

# Start
docker-compose -f docker-compose.monitoring.yml up -d

# Access: http://your-server-ip:3000
```

---

#### S5. Backup Strategy
**Время:** 2 часа

```bash
# Create backup scripts
mkdir -p /home/admin/backups/scripts

***REMOVED*** backup
cat > /home/admin/backups/scripts/backup_qdrant.sh <<'EOF'
#!/bin/bash
BACKUP_DIR=/home/admin/backups/qdrant
DATE=$(date +%Y%m%d_%H%M%S)
docker exec qdrant tar czf - /qdrant/storage > $BACKUP_DIR/qdrant_$DATE.tar.gz
# Keep only last 7 days
find $BACKUP_DIR -name "qdrant_*.tar.gz" -mtime +7 -delete
EOF

chmod +x /home/admin/backups/scripts/backup_qdrant.sh

# Cron job (daily at 2 AM)
crontab -e
# Add: 0 2 * * * /home/admin/backups/scripts/backup_qdrant.sh
```

---

#### S6. Load Testing
**Время:** 4 часа

```bash
# Install locust
pip install locust

# Create tests/load/locustfile.py (создай локально, потом загрузи)

# Run on server
locust -f tests/load/locustfile.py \
  --host http://localhost \
  --users 10 \
  --spawn-rate 2 \
  --run-time 5m \
  --headless

# Monitor with htop, docker stats
htop
docker stats
```

---

## 📝 Рекомендованный workflow

### День 1: Deployment Services
```bash
Morning:
- [ ] S1: Deploy BGE-M3 FastAPI (2-3h)
- [ ] S2: Deploy MLflow (1h)

Afternoon:
- [ ] S3: Deploy Langfuse (1h)
- [ ] Test integration: Bot → BGE-M3 → MLflow

Evening:
- [ ] Document what's working
- [ ] Update .env with new endpoints
```

### День 2: Monitoring & Testing
```bash
Morning:
- [ ] S4: Prometheus + Grafana (2-3h)
- [ ] Configure dashboards

Afternoon:
- [ ] S6: Load testing (4h)
- [ ] Performance tuning

Evening:
- [ ] Document bottlenecks
- [ ] Plan optimizations
```

### День 3: Backups & Cleanup
```bash
Morning:
- [ ] S5: Backup strategy (2h)
- [ ] Test restore procedures

Afternoon:
- [ ] Code cleanup
- [ ] Update documentation

Evening:
- [ ] Commit all server configs to git
- [ ] Push to main branch
```

---

## 🐳 Docker Compose Setup

### Minimal docker-compose.yml (для сервера)

```yaml
# /home/admin/contextual_rag/docker-compose.yml
version: '3.8'

services:
  qdrant:
    image: qdrant/qdrant:v1.15.4
    ports:
      - "6333:6333"
      - "6334:6334"
    volumes:
      - ./qdrant_storage:/qdrant/storage
    restart: always

  redis:
    image: redis/redis-stack:8.2.0-v0
    ports:
      - "6379:6379"
    volumes:
      - redis-data:/data
    restart: always

  bge-m3:
    build: ./docker/bge-m3
    ports:
      - "8001:8001"
    environment:
      - MODEL_NAME=BAAI/bge-m3
      - DEVICE=cuda  # или cpu
    volumes:
      - model-cache:/root/.cache
    restart: always

  telegram-bot:
    build: .
    depends_on:
      - qdrant
      - redis
      - bge-m3
    env_file:
      - .env
    restart: always

  mlflow:
    image: ghcr.io/mlflow/mlflow:latest
    ports:
      - "5000:5000"
    command: >
      mlflow server
      --backend-store-uri sqlite:///mlflow.db
      --default-artifact-root /mlruns
      --host 0.0.0.0
    volumes:
      - mlflow-data:/mlruns
    restart: always

  langfuse:
    image: langfuse/langfuse:latest
    ports:
      - "3001:3000"
    environment:
      - DATABASE_URL=postgresql://langfuse:password@postgres:5432/langfuse
      - NEXTAUTH_SECRET=${LANGFUSE_SECRET}
    depends_on:
      - postgres
    restart: always

  postgres:
    image: postgres:15
    environment:
      - POSTGRES_USER=langfuse
      - POSTGRES_PASSWORD=password
      - POSTGRES_DB=langfuse
    volumes:
      - postgres-data:/var/lib/postgresql/data
    restart: always

volumes:
  redis-data:
  mlflow-data:
  postgres-data:
  model-cache:
```

### Запуск

```bash
# Start all services
docker-compose up -d

# Check status
docker-compose ps

# View logs
docker-compose logs -f

# Stop all
docker-compose down

# Rebuild after code changes
docker-compose up -d --build telegram-bot
```

---

## 🔍 Troubleshooting

### BGE-M3 не запускается
```bash
# Check memory
free -h
# BGE-M3 requires ~3GB RAM

# Check GPU (if using CUDA)
nvidia-smi

# Check Docker logs
docker logs bge-m3

# Fallback to CPU
# Edit docker-compose.yml: DEVICE=cpu
```

##***REMOVED*** connection errors
```bash
# Check Qdrant is running
docker ps | grep qdrant

# Check collections
curl http://localhost:6333/collections

# Restart Qdrant
docker restart qdrant

# Check logs
docker logs qdrant
```

### Redis connection errors
```bash
# Check Redis is running
docker ps | grep redis

# Test connection
redis-cli ping

# Check memory usage
redis-cli info memory

# Restart Redis
docker restart redis
```

### Telegram Bot не отвечает
```bash
# Check bot is running
docker ps | grep telegram-bot

# Check logs
docker logs telegram-bot -f

# Check .env file
cat .env | grep TELEGRAM_BOT_TOKEN

# Restart bot
docker restart telegram-bot
```

---

## 📊 Monitoring Commands

### Server Resources
```bash
# CPU & RAM
htop

# Disk usage
df -h
du -sh /home/admin/contextual_rag/*

# Docker stats
docker stats

# Network
netstat -tlnp
```

### Application Metrics
```bash
# Cache hit rates (из бота)
# Используй команду /stats в Telegram

***REMOVED*** metrics
curl http://localhost:6333/metrics

# Redis info
redis-cli info stats

# MLflow experiments
curl http://localhost:5000/api/2.0/mlflow/experiments/list
```

---

## 🔐 Security Checklist

```bash
# Check .env не в git
cat .gitignore | grep .env

# Check firewall
sudo ufw status
# Открыть только: 22 (SSH), 80/443 (HTTP/HTTPS)
# Закрыть: 6333, 6379, 8001, 5000, 3001

# Check secrets
grep -r "API_KEY\|SECRET\|PASSWORD" .env | wc -l

# Check file permissions
ls -la .env
# Должно быть: -rw------- (600)
```

---

## 📚 Полезные ссылки

**Документация:**
- [TASK_ALLOCATION.md](./docs/TASK_ALLOCATION.md) - Полный список задач
- [TESTING_PLAN.md](./docs/TESTING_PLAN.md) - План тестирования
- [DEPLOYMENT.md](./DEPLOYMENT.md) - Detailed deployment guide
- [CHANGELOG.md](./CHANGELOG.md) - История изменений

**Endpoints (после deployment):**
- Qdrant UI: http://localhost:6333/dashboard
- MLflow UI: http://localhost:5000
- Langfuse UI: http://localhost:3001
- Grafana: http://localhost:3000
- Prometheus: http://localhost:9090

---

## ✅ Deployment Checklist

После выполнения всех задач:

```bash
Сервисы:
✅ Qdrant running on 6333
✅ Redis running on 6379
✅ BGE-M3 API on 8001
✅ Telegram Bot working
✅ MLflow on 5000
✅ Langfuse on 3001
✅ Prometheus + Grafana setup

Tests:
✅ Bot responds to /start
✅ Bot answers queries
✅ Cache hit rates > 70%
✅ Load test passed (10 users, 100 req/min)

Backups:
✅ Qdrant backup script
✅ Redis persistence enabled
✅ Cron jobs configured
✅ Restore procedure tested

Monitoring:
✅ Grafana dashboards created
✅ Prometheus scraping metrics
✅ Alerts configured
✅ Log rotation setup
```

---

**Last Updated:** 2025-01-06
**Maintained by:** @yastman
**Questions:** Create issue with label `#vps-deployment`

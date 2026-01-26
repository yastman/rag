***REMOVED*** 🚀 VPS Quick Start Guide

> **Для работы на production сервере** `/srv/rag-fresh`

**Дата:** 2025-01-06
**Версия:** v2.8.0
**Статус:** 95% Production-Ready

---

***REMOVED******REMOVED*** 📋 Checklist перед началом

***REMOVED******REMOVED******REMOVED*** 1. Проверка текущего состояния

```bash
***REMOVED*** SSH на сервер
ssh admin@your-server-ip

***REMOVED*** Переход в проект
cd /srv/rag-fresh

***REMOVED*** Проверка Git
git status
git log --oneline -5

***REMOVED*** Pull последних изменений
git pull origin main
```

***REMOVED******REMOVED******REMOVED*** 2. Проверка running сервисов

```bash
***REMOVED*** Проверить Docker контейнеры
docker ps
***REMOVED*** Ожидается: Qdrant (6333), Redis (6379)

***REMOVED*** Проверить systemd services
systemctl status telegram-bot
***REMOVED*** Или если в Docker:
docker ps | grep telegram-bot

***REMOVED*** Проверить порты
netstat -tlnp | grep -E "6333|6379|8001|5000|3001"
```

***REMOVED******REMOVED******REMOVED*** 3. Проверка работоспособности

```bash
***REMOVED*** Qdrant
curl http://localhost:6333/collections
***REMOVED*** Ожидается: JSON со списком коллекций

***REMOVED*** Redis
redis-cli ping
***REMOVED*** Ожидается: PONG

***REMOVED*** BGE-M3 API (если есть)
curl http://localhost:8001/health
***REMOVED*** Ожидается: {"status": "ok"}

***REMOVED*** MLflow (если есть)
curl http://localhost:5000
***REMOVED*** Ожидается: HTML страница

***REMOVED*** Telegram Bot logs
journalctl -u telegram-bot -f
***REMOVED*** Или: docker logs telegram-bot -f
```

---

***REMOVED******REMOVED*** 🎯 Приоритетные задачи на сервере

***REMOVED******REMOVED******REMOVED*** 🔴 Priority 1: Must Deploy (Критические)

***REMOVED******REMOVED******REMOVED******REMOVED*** S1. Deploy BGE-M3 as FastAPI Service
**Время:** 2-3 часа
**Зачем:** Embeddings service должен работать 24/7

```bash
***REMOVED*** Location: создать src/services/bge_m3_api.py
***REMOVED*** Port: 8001
***REMOVED*** Docker: создать docker/bge-m3/Dockerfile

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

***REMOVED******REMOVED******REMOVED******REMOVED*** S2. Deploy MLflow Server
**Время:** 1 час
**Зачем:** Experiment tracking + Model registry

```bash
***REMOVED*** Install
pip install mlflow

***REMOVED*** Run with SQLite backend
mlflow server \
  --backend-store-uri sqlite:///mlflow.db \
  --default-artifact-root ./mlruns \
  --host 0.0.0.0 \
  --port 5000

***REMOVED*** Or with systemd:
sudo cp mlflow.service /etc/systemd/system/
sudo systemctl enable mlflow
sudo systemctl start mlflow

***REMOVED*** Verify
curl http://localhost:5000
```

**Status:** ⏳ Referenced in code but unclear if running

---

***REMOVED******REMOVED******REMOVED******REMOVED*** S3. Deploy Langfuse Server
**Время:** 1 час
**Зачем:** LLM tracing and cost tracking

```bash
***REMOVED*** Docker deployment
docker run -d \
  --name langfuse \
  -p 3001:3000 \
  -e DATABASE_URL=postgresql://... \
  -e NEXTAUTH_SECRET=$(openssl rand -base64 32) \
  langfuse/langfuse:latest

***REMOVED*** Or docker-compose (см. ниже)

***REMOVED*** Verify
curl http://localhost:3001
```

**Status:** ⏳ Code integration exists, server status unknown

---

***REMOVED******REMOVED******REMOVED*** 🟡 Priority 2: Should Deploy (Важные)

***REMOVED******REMOVED******REMOVED******REMOVED*** S4. Prometheus + Grafana Monitoring
**Время:** 2-3 часа

```bash
***REMOVED*** docker-compose.monitoring.yml
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

***REMOVED*** Start
docker-compose -f docker-compose.monitoring.yml up -d

***REMOVED*** Access: http://your-server-ip:3000
```

---

***REMOVED******REMOVED******REMOVED******REMOVED*** S5. Backup Strategy
**Время:** 2 часа

```bash
***REMOVED*** Create backup scripts
mkdir -p /srv/backups/scripts

***REMOVED*** Qdrant backup
cat > /srv/backups/scripts/backup_qdrant.sh <<'EOF'
***REMOVED***!/bin/bash
BACKUP_DIR=/srv/backups/qdrant
DATE=$(date +%Y%m%d_%H%M%S)
docker exec qdrant tar czf - /qdrant/storage > $BACKUP_DIR/qdrant_$DATE.tar.gz
***REMOVED*** Keep only last 7 days
find $BACKUP_DIR -name "qdrant_*.tar.gz" -mtime +7 -delete
EOF

chmod +x /srv/backups/scripts/backup_qdrant.sh

***REMOVED*** Cron job (daily at 2 AM)
crontab -e
***REMOVED*** Add: 0 2 * * * /srv/backups/scripts/backup_qdrant.sh
```

---

***REMOVED******REMOVED******REMOVED******REMOVED*** S6. Load Testing
**Время:** 4 часа

```bash
***REMOVED*** Install locust
pip install locust

***REMOVED*** Create tests/load/locustfile.py (создай локально, потом загрузи)

***REMOVED*** Run on server
locust -f tests/load/locustfile.py \
  --host http://localhost \
  --users 10 \
  --spawn-rate 2 \
  --run-time 5m \
  --headless

***REMOVED*** Monitor with htop, docker stats
htop
docker stats
```

---

***REMOVED******REMOVED*** 📝 Рекомендованный workflow

***REMOVED******REMOVED******REMOVED*** День 1: Deployment Services
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

***REMOVED******REMOVED******REMOVED*** День 2: Monitoring & Testing
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

***REMOVED******REMOVED******REMOVED*** День 3: Backups & Cleanup
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

***REMOVED******REMOVED*** 🐳 Docker Compose Setup

***REMOVED******REMOVED******REMOVED*** Minimal docker-compose.yml (для сервера)

```yaml
***REMOVED*** /srv/app/docker-compose.yml
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
      - DEVICE=cuda  ***REMOVED*** или cpu
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

***REMOVED******REMOVED******REMOVED*** Запуск

```bash
***REMOVED*** Start all services
docker-compose up -d

***REMOVED*** Check status
docker-compose ps

***REMOVED*** View logs
docker-compose logs -f

***REMOVED*** Stop all
docker-compose down

***REMOVED*** Rebuild after code changes
docker-compose up -d --build telegram-bot
```

---

***REMOVED******REMOVED*** 🔍 Troubleshooting

***REMOVED******REMOVED******REMOVED*** BGE-M3 не запускается
```bash
***REMOVED*** Check memory
free -h
***REMOVED*** BGE-M3 requires ~3GB RAM

***REMOVED*** Check GPU (if using CUDA)
nvidia-smi

***REMOVED*** Check Docker logs
docker logs bge-m3

***REMOVED*** Fallback to CPU
***REMOVED*** Edit docker-compose.yml: DEVICE=cpu
```

***REMOVED******REMOVED******REMOVED*** Qdrant connection errors
```bash
***REMOVED*** Check Qdrant is running
docker ps | grep qdrant

***REMOVED*** Check collections
curl http://localhost:6333/collections

***REMOVED*** Restart Qdrant
docker restart qdrant

***REMOVED*** Check logs
docker logs qdrant
```

***REMOVED******REMOVED******REMOVED*** Redis connection errors
```bash
***REMOVED*** Check Redis is running
docker ps | grep redis

***REMOVED*** Test connection
redis-cli ping

***REMOVED*** Check memory usage
redis-cli info memory

***REMOVED*** Restart Redis
docker restart redis
```

***REMOVED******REMOVED******REMOVED*** Telegram Bot не отвечает
```bash
***REMOVED*** Check bot is running
docker ps | grep telegram-bot

***REMOVED*** Check logs
docker logs telegram-bot -f

***REMOVED*** Check .env file
cat .env | grep TELEGRAM_BOT_TOKEN

***REMOVED*** Restart bot
docker restart telegram-bot
```

---

***REMOVED******REMOVED*** 📊 Monitoring Commands

***REMOVED******REMOVED******REMOVED*** Server Resources
```bash
***REMOVED*** CPU & RAM
htop

***REMOVED*** Disk usage
df -h
du -sh /srv/app/*

***REMOVED*** Docker stats
docker stats

***REMOVED*** Network
netstat -tlnp
```

***REMOVED******REMOVED******REMOVED*** Application Metrics
```bash
***REMOVED*** Cache hit rates (из бота)
***REMOVED*** Используй команду /stats в Telegram

***REMOVED*** Qdrant metrics
curl http://localhost:6333/metrics

***REMOVED*** Redis info
redis-cli info stats

***REMOVED*** MLflow experiments
curl http://localhost:5000/api/2.0/mlflow/experiments/list
```

---

***REMOVED******REMOVED*** 🔐 Security Checklist

```bash
***REMOVED*** Check .env не в git
cat .gitignore | grep .env

***REMOVED*** Check firewall
sudo ufw status
***REMOVED*** Открыть только: 22 (SSH), 80/443 (HTTP/HTTPS)
***REMOVED*** Закрыть: 6333, 6379, 8001, 5000, 3001

***REMOVED*** Check secrets
grep -r "API_KEY\|SECRET\|PASSWORD" .env | wc -l

***REMOVED*** Check file permissions
ls -la .env
***REMOVED*** Должно быть: -rw------- (600)
```

---

***REMOVED******REMOVED*** 📚 Полезные ссылки

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

***REMOVED******REMOVED*** ✅ Deployment Checklist

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
**Questions:** Create issue with label `***REMOVED***vps-deployment`

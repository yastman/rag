# VPS Docker Migration — Design

**Дата:** 2026-03-02
**Статус:** Утверждён
**Подход:** rsync + remote build (Docker Compose)

## Контекст

VPS-контейнеры устарели на 3+ недели (код от 8 февраля). Image drift: redis 8.4.0→8.6.0, qdrant v1.16→v1.17.0, litellm v1.81.3.rc.3→v1.81.3-stable. Бот не запущен. Нужна полная переустановка с чистого листа.

## VPS

| Параметр | Значение |
|----------|----------|
| Host | `95.111.252.29:1654`, user `admin` |
| OS | Ubuntu 24.04 LTS |
| Resources | 6 CPU, 11 GB RAM, 96 GB disk (56 GB free) |
| Docker | 29.2.1, Compose v5.0.2 |
| Path | `/opt/rag-fresh` |
| SSH alias | `vps` |

## Решения

| Решение | Выбор | Причина |
|---------|-------|---------|
| Оркестратор | Docker Compose | Проверен, минимальный overhead, k3s не нужен |
| Доставка образов | rsync код + remote build | Минимум трафика (~50 MB vs ~12 GB), build cache на VPS |
| Даунтайм | Любой (не критично) | Полная остановка, чистый старт |
| Данные (volumes) | Чистый старт | Удалить все volumes, PostgreSQL init scripts пересоздадут БД |

## Архитектура

```
WSL2 (dev)                              VPS (prod)
┌─────────────┐   rsync -avz    ┌──────────────────────┐
│ rag-fresh/  │ ──────────────→ │ /opt/rag-fresh/      │
│ main branch │                 │                      │
└─────────────┘                 │ docker compose build  │
                                │ docker compose up -d  │
                                │                      │
                                │ 9 контейнеров:       │
                                │ ├─ postgres (512M)   │
                                │ ├─ redis (300M)      │
                                │ ├─ qdrant (1G)       │
                                │ ├─ bge-m3 (4G)       │
                                │ ├─ user-base (2G)    │
                                │ ├─ docling (2G)      │
                                │ ├─ litellm (512M)    │
                                │ ├─ bot (512M)        │
                                │ └─ ingestion (ingest)│
                                └──────────────────────┘
```

## План шагов

### Phase 1: Подготовка (локально)

1. **Проверить main стабилен**
   ```bash
   make check           # ruff + mypy
   make test-unit       # unit tests
   ```

2. **Подготовить .env для VPS**
   - Проверить `.env.example` на новые переменные (CRM, nurturing)
   - Обновить `.env` на VPS

3. **rsync код на VPS**
   ```bash
   rsync -avz --delete \
     --exclude '.git' --exclude '.venv' --exclude '__pycache__' \
     --exclude 'node_modules' --exclude '.mypy_cache' --exclude '.ruff_cache' \
     --exclude '.pytest_cache' --exclude 'logs/' --exclude '.env' \
     --exclude '.env.local' --exclude '.env.server' --exclude '.claude' \
     --exclude 'data/' --exclude '.cache' --exclude '.deepeval' \
     -e "ssh -i ~/.ssh/vps_access_key -p 1654 -o IdentitiesOnly=yes" \
     /home/user/projects/rag-fresh/ admin@95.111.252.29:/opt/rag-fresh/
   ```

### Phase 2: Очистка на VPS

4. **Остановить контейнеры + удалить volumes**
   ```bash
   ssh vps "cd /opt/rag-fresh && docker compose -f docker-compose.vps.yml down -v"
   ```

5. **Удалить старые образы + build cache**
   ```bash
   ssh vps "docker image prune -af && docker builder prune -af"
   ```
   Освобождает ~15 GB.

### Phase 3: Сборка и запуск на VPS

6. **Собрать кастомные образы**
   ```bash
   # Через tmux — build долгий (~15-20 мин без кэша)
   ssh vps "cd /opt/rag-fresh && docker compose -f docker-compose.vps.yml build 2>&1 | tee /tmp/docker-build.log"
   ```
   Собирает 5 образов: bot, bge-m3, user-base, docling, ingestion.
   Публичные (postgres, redis, qdrant, litellm) — pull при `up`.

7. **Обновить .env на VPS**
   ```bash
   # Скопировать обновлённый .env (или отредактировать на месте)
   scp -P 1654 -i ~/.ssh/vps_access_key .env.vps admin@95.111.252.29:/opt/rag-fresh/.env
   ```

8. **Запустить всё**
   ```bash
   ssh vps "cd /opt/rag-fresh && docker compose --compatibility -f docker-compose.vps.yml up -d"
   ```

### Phase 4: Верификация

9. **Проверить статус контейнеров**
   ```bash
   ssh vps "docker ps --format 'table {{.Names}}\t{{.Status}}\t{{.Image}}' | grep vps"
   ```

10. **Проверить использование ресурсов**
    ```bash
    ssh vps "docker stats --no-stream | grep vps"
    ```

11. **Smoke test — бот отвечает в Telegram**

12. **При необходимости — запустить ingestion**
    ```bash
    ssh vps "cd /opt/rag-fresh && docker compose -f docker-compose.vps.yml --profile ingest up -d"
    ```

## Ожидаемые результаты

| Метрика | До | После |
|---------|-----|-------|
| Контейнеры | 8 (бот не запущен) | 9 (все healthy + бот) |
| Redis | 8.4.0 | 8.6.0 |
| Qdrant | v1.16 | v1.17.0 |
| LiteLLM | v1.81.3.rc.3 | v1.81.3-stable |
| Код | 8 февраля | main 2 марта |
| Disk freed | — | ~15 GB (old images) |

## Риски и митигация

| Риск | Митигация |
|------|-----------|
| Build fails на VPS (нет RAM) | 11 GB RAM, 4 GB swap — достаточно. Собирать по одному сервису если нужно. |
| bge-m3 долго грузит модели | start_period: 180s в healthcheck. HF кэш скачается ~5 мин. |
| Потеря данных Qdrant | Re-ingest через `--profile ingest`. Данные восстановимы. |
| .env не совпадает | Проверить .env.example перед переносом. |

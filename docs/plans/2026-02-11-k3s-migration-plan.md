# VPS Migration: Docker Compose to k3s -- Implementation Plan

**Issue:** [#54](https://github.com/yastman/rag/issues/54) feat: migrate VPS stack from Docker Compose to k3s
**Date:** 2026-02-11
**Effort:** XL (3-5 дней, 6 фаз)
**Milestone:** Deferred: Post-Baseline

## Goal

Перевести VPS-стек (9 сервисов) с Docker Compose на k3s (single-node Kubernetes) для:
- Rolling updates без downtime
- Нативного secrets management (encrypted at rest)
- Init containers вместо depends_on
- Kustomize overlays вместо Docker profiles
- Готовность к масштабированию

## Текущее состояние

### VPS (95.111.252.29)

| Ресурс | Значение |
|--------|----------|
| RAM | 11 GB (1.4 GB actual) |
| CPU | 6 cores |
| Disk | 55 GB free |
| Текущий стек | Docker Compose (docker-compose.vps.yml) |
| Контейнеры | 9 сервисов, все healthy |

### Docker Compose стек (docker-compose.vps.yml)

| Сервис | Image | Memory Limit | Примечание |
|--------|-------|-------------|------------|
| postgres | pgvector/pgvector:pg17 | 512M | PVC |
| redis | redis:8.4.0 | 300M | PVC |
| qdrant | qdrant/qdrant:v1.16 | 1G | PVC |
| docling | custom (build) | 2G | PVC для HF cache |
| bge-m3 | custom (build) | 4G | hostPath /models |
| user-base | custom (build) | 2G | hostPath /models |
| litellm | ghcr.io/berriai/litellm:main-v1.81.3-stable | 512M | ConfigMap |
| bot | custom (build) | 512M | 5 depends_on |
| ingestion | custom (build, profile: ingest) | 512M | replicas=0 default |

### Готовые k8s манифесты (k8s/)

Phase 0 уже завершена. Все манифесты написаны и организованы:

    k8s/
    +-- base/                          # 22 ресурса
    |   +-- kustomization.yaml
    |   +-- namespace.yaml             # rag
    |   +-- configmaps/                # postgres-init, litellm-config
    |   +-- postgres/                  # PVC + Deployment + Service
    |   +-- redis/                     # PVC + Deployment + Service
    |   +-- qdrant/                    # PVC + Deployment + Service
    |   +-- docling/                   # PVC + Deployment + Service
    |   +-- bge-m3/                    # Deployment + Service (hostPath)
    |   +-- user-base/                 # Deployment + Service (hostPath)
    |   +-- litellm/                   # Deployment + Service + initContainer
    |   +-- bot/                       # Deployment + 5 initContainers
    |   +-- ingestion/                 # Deployment (replicas: 0)
    +-- overlays/
    |   +-- core/                      # postgres, redis, qdrant
    |   +-- bot/                       # core + ML + litellm + bot
    |   +-- ingest/                    # core + docling + bge-m3 + ingestion
    |   +-- full/                      # Everything
    +-- secrets/.env.example
    +-- k3s-config.yaml                # Server config (eviction, encryption, gc)

**Security в манифестах:**
- seccompProfile: RuntimeDefault (pod-level)
- allowPrivilegeEscalation: false (все контейнеры + init)
- capabilities.drop: ["ALL"]
- imagePullPolicy: Never (custom images)

### Makefile targets (готовы)

| Target | Описание |
|--------|----------|
| k3s-core | kubectl apply -k k8s/overlays/core/ |
| k3s-bot | kubectl apply -k k8s/overlays/bot/ |
| k3s-ingest | kubectl apply -k k8s/overlays/ingest/ |
| k3s-full | kubectl apply -k k8s/overlays/full/ |
| k3s-status | kubectl get pods -n rag |
| k3s-logs SVC=x | kubectl logs -n rag deployment/x |
| k3s-down | kubectl delete -k k8s/overlays/full/ |
| k3s-secrets | kubectl create secret from .env |
| k3s-push-% | docker save | k3s ctr import |
| k3s-ingest-start/stop | kubectl scale deployment |

## Prerequisites

| Issue | Описание | Статус | Зачем |
|-------|----------|--------|-------|
| #73 | k3s tuning (eviction, gc) | План готов | k3s-config.yaml |
| #70 | Qdrant snapshots | План готов | Backup перед миграцией |
| #72 | Slim Docker images | План готов | Меньше transfer time |

**Hard prerequisites:** Только #70 (backup данных перед миграцией)
**Soft prerequisites:** #72 и #73 желательны, но можно делать параллельно

## Migration Strategy: Staged Rollout (НЕ Big-Bang)

    Phase 1: VPS prep          Phase 2: Core         Phase 3: ML           Phase 4: App
    +---------+               +--------+             +--------+            +--------+
    | k3s     |    ------>    | PG     |   ------>   | BGE-M3 |   ----->  | Bot    |
    | install |               | Redis  |             | User-  |            | LiteL  |
    | backup  |               | Qdrant |             | base   |            |        |
    +---------+               +--------+             +--------+            +--------+
         |                         |                       |                    |
         v                         v                       v                    v
    Docker Compose             Docker: ML+App         Docker: App          Docker: OFF
    running (9 svc)            k3s: Core (3)          k3s: Core+ML (5)    k3s: All (8)

**Принцип:** На каждой фазе Docker Compose и k3s работают параллельно. Переносим сервисы по одной группе, проверяем, откатываем если проблемы.

## Rollback Plan

| Фаза | Откат |
|------|-------|
| Phase 1 (k3s install) | k3s-uninstall.sh, Docker Compose не тронут |
| Phase 2 (core) | kubectl delete -k k8s/overlays/core/, docker compose up |
| Phase 3 (ML) | kubectl delete deployment bge-m3 user-base, docker compose up |
| Phase 4 (app) | kubectl delete deployment bot litellm, docker compose up |
| Полный откат | k3s-uninstall.sh && docker compose up -d |

**Docker Compose файлы НЕ удаляются.** Остаются как fallback минимум 1 неделю.

## RAM Budget

| Компонент | RAM |
|-----------|-----|
| k3s control plane | ~700 MB |
| postgres | 512 MB |
| redis | 300 MB |
| qdrant | 1 GB |
| docling | 2 GB |
| bge-m3 | 4 GB |
| user-base | 2 GB |
| litellm | 512 MB |
| bot | 512 MB |
| ingestion (replicas=0) | 0 |
| **Итого** | **~11.5 GB** |

**VPS:** 11 GB RAM. Tight fit, но предыдущий Docker Compose стек работает. k3s overhead ~700 MB vs Docker ~300 MB = +400 MB. Eviction policies в k3s-config.yaml защитят от OOM.

---

# Phase 1: VPS Preparation (30 мин)

## Task 1.1: Backup данных (prereq: #70)

**Files:** нет (VPS commands)
**Time:** 5 мин

Шаги:
1. Создать Qdrant snapshot:

        ssh vps "docker compose -f /opt/rag-fresh/docker-compose.vps.yml exec -T qdrant \
          curl -X POST 'http://localhost:6333/collections/gdrive_documents_bge/snapshots'"

2. Скопировать snapshot локально:

        ssh vps "docker cp vps-qdrant:/qdrant/snapshots ./qdrant-backup-$(date +%Y%m%d)"

3. pg_dump для Postgres:

        ssh vps "docker compose -f /opt/rag-fresh/docker-compose.vps.yml exec -T postgres \
          pg_dump -U postgres postgres" > backup-postgres-$(date +%Y%m%d).sql

**Acceptance:** snapshot + pg_dump файлы созданы, размер > 0

## Task 1.2: Установить k3s на VPS

**Files:**
- Read: k8s/k3s-config.yaml
**Time:** 5 мин

Шаги:
1. Скопировать k3s-config.yaml:

        scp k8s/k3s-config.yaml vps:/tmp/k3s-config.yaml
        ssh vps "sudo mkdir -p /etc/rancher/k3s && sudo cp /tmp/k3s-config.yaml /etc/rancher/k3s/config.yaml"

2. Установить k3s:

        ssh vps "curl -sfL https://get.k3s.io | sh -"

3. Проверить:

        ssh vps "sudo k3s kubectl get nodes"

**Acceptance:** node в статусе Ready

## Task 1.3: Настроить kubectl доступ

**Time:** 3 мин

Шаги:
1. Скопировать kubeconfig:

        ssh vps "sudo cat /etc/rancher/k3s/k3s.yaml" > ~/.kube/config-vps

2. Обновить server URL в config-vps:

        sed -i 's|https://127.0.0.1:6443|https://95.111.252.29:6443|' ~/.kube/config-vps

3. Проверить:

        KUBECONFIG=~/.kube/config-vps kubectl get nodes

**Acceptance:** node видна через kubectl с dev машины

## Task 1.4: Создать namespace + secrets

**Files:**
- Read: k8s/base/namespace.yaml
- Read: k8s/secrets/.env.example
**Time:** 3 мин

Шаги:
1. Создать .env файл из существующего VPS .env:

        ssh vps "grep -E 'TELEGRAM_BOT_TOKEN|LITELLM_MASTER_KEY|CEREBRAS_API_KEY|GROQ_API_KEY|OPENAI_API_KEY' /opt/rag-fresh/.env" > k8s/secrets/.env

2. Применить:

        ssh vps "cd /opt/rag-fresh && sudo k3s kubectl apply -f k8s/base/namespace.yaml"
        ssh vps "cd /opt/rag-fresh && sudo k3s kubectl create secret generic api-keys --from-env-file=k8s/secrets/.env -n rag --dry-run=client -o yaml | sudo k3s kubectl apply -f -"
        ssh vps "cd /opt/rag-fresh && sudo k3s kubectl create secret generic db-credentials \
          --from-literal=POSTGRES_USER=postgres \
          --from-literal=POSTGRES_PASSWORD=postgres \
          --from-literal=POSTGRES_DB=postgres \
          -n rag --dry-run=client -o yaml | sudo k3s kubectl apply -f -"

**Acceptance:** kubectl get secrets -n rag показывает api-keys и db-credentials

## Task 1.5: Создать hostPath директории

**Time:** 2 мин

Шаги:
1. Создать директории для PVC и shared data:

        ssh vps "sudo mkdir -p /opt/k3s-data/hf-cache && sudo chmod 777 /opt/k3s-data/hf-cache"

2. Проверить, что drive-sync доступен:

        ssh vps "ls /home/admin/drive-sync/"

**Acceptance:** директории существуют, drive-sync содержит файлы

## Task 1.6: Pre-pull public images

**Time:** 5 мин

Публичные images (из k8s манифестов) нужно загрузить заранее:

        ssh vps "sudo k3s ctr -n k8s.io images pull docker.io/pgvector/pgvector:pg17"
        ssh vps "sudo k3s ctr -n k8s.io images pull docker.io/library/redis:8.4.0"
        ssh vps "sudo k3s ctr -n k8s.io images pull docker.io/qdrant/qdrant:v1.16"
        ssh vps "sudo k3s ctr -n k8s.io images pull ghcr.io/berriai/litellm:main-v1.81.3-stable"
        ssh vps "sudo k3s ctr -n k8s.io images pull docker.io/library/busybox:1.37"

**Acceptance:** k3s ctr -n k8s.io images list | grep -E "pgvector|redis|qdrant|litellm|busybox"

---

# Phase 2: Core Services (20 мин)

**Стратегия:** Остановить Docker Compose core сервисы, развернуть в k3s, проверить.

## Task 2.1: Build + transfer custom images (from WSL2)

**Files:**
- Read: docker-bake.hcl
**Time:** 10 мин

Шаги:
1. Build все 5 custom images:

        docker buildx bake --load

2. Transfer на VPS:

        for img in bot bge-m3 user-base docling ingestion; do
          make k3s-push-$img
        done

3. Проверить:

        ssh vps "sudo k3s ctr -n k8s.io images list | grep rag/"

**Acceptance:** 5 images (rag/bot, rag/bge-m3, rag/user-base, rag/docling, rag/ingestion) в containerd

## Task 2.2: Остановить Docker Compose core сервисы

**Time:** 2 мин

ВАЖНО: Остановить ТОЛЬКО postgres, redis, qdrant. Остальные зависят от них и упадут сами.

        ssh vps "cd /opt/rag-fresh && docker compose -f docker-compose.vps.yml stop"

**Acceptance:** docker ps | grep vps = пусто

## Task 2.3: Data migration -- PVC из Docker volumes

**Time:** 5 мин

k3s local-path-provisioner создаёт PVC в /var/lib/rancher/k3s/storage/. Нужно перенести данные из Docker volumes.

Шаги:
1. Найти Docker volume paths:

        ssh vps "docker volume inspect rag-fresh_postgres_data --format '{{.Mountpoint}}'"
        ssh vps "docker volume inspect rag-fresh_redis_data --format '{{.Mountpoint}}'"
        ssh vps "docker volume inspect rag-fresh_qdrant_data --format '{{.Mountpoint}}'"

2. Развернуть core overlay (создаст PVC):

        ssh vps "cd /opt/rag-fresh && sudo k3s kubectl apply -k k8s/overlays/core/ --load-restrictor=LoadRestrictionsNone"

3. Дождаться PVC binding, найти paths:

        ssh vps "sudo k3s kubectl get pvc -n rag"

4. Остановить pods, скопировать данные:

        ssh vps "sudo k3s kubectl scale deployment postgres redis qdrant -n rag --replicas=0"

        # Postgres
        ssh vps "sudo cp -a /var/lib/docker/volumes/rag-fresh_postgres_data/_data/* \
          /var/lib/rancher/k3s/storage/<pvc-postgres-id>/"

        # Redis
        ssh vps "sudo cp -a /var/lib/docker/volumes/rag-fresh_redis_data/_data/* \
          /var/lib/rancher/k3s/storage/<pvc-redis-id>/"

        # Qdrant
        ssh vps "sudo cp -a /var/lib/docker/volumes/rag-fresh_qdrant_data/_data/* \
          /var/lib/rancher/k3s/storage/<pvc-qdrant-id>/"

5. Scale back up:

        ssh vps "sudo k3s kubectl scale deployment postgres redis qdrant -n rag --replicas=1"

**Acceptance:** kubectl get pods -n rag, все 3 пода Running + Ready

## Task 2.4: Проверить core

**Time:** 3 мин

Шаги:
1. Проверить Postgres:

        ssh vps "sudo k3s kubectl exec -n rag deployment/postgres -- pg_isready -U postgres"

2. Проверить Redis:

        ssh vps "sudo k3s kubectl exec -n rag deployment/redis -- redis-cli ping"

3. Проверить Qdrant (через exec):

        ssh vps "sudo k3s kubectl exec -n rag deployment/qdrant -- sh -c \
          'wget -qO- http://localhost:6333/collections/gdrive_documents_bge | head -1'"

4. Проверить points_count > 0:

        ssh vps "sudo k3s kubectl exec -n rag deployment/qdrant -- sh -c \
          'wget -qO- http://localhost:6333/collections/gdrive_documents_bge' | python3 -c 'import sys,json; print(json.load(sys.stdin)[\"result\"][\"points_count\"])'"

**Acceptance:** pg_isready = ok, redis PONG, qdrant points_count = 278 (или текущее значение)

---

# Phase 3: ML Services (15 мин)

## Task 3.1: Deploy ML сервисы

**Files:**
- Read: k8s/base/bge-m3/deployment.yaml
- Read: k8s/base/user-base/deployment.yaml
- Read: k8s/base/docling/deployment.yaml
**Time:** 10 мин

Шаги:
1. Применить bot overlay (включает core + ML + litellm + bot):

        ssh vps "cd /opt/rag-fresh && sudo k3s kubectl apply -k k8s/overlays/bot/ --load-restrictor=LoadRestrictionsNone"

2. Мониторить startup (bge-m3 стартует 3-5 мин из-за загрузки модели):

        ssh vps "sudo k3s kubectl get pods -n rag -w"

3. Проверить логи BGE-M3:

        ssh vps "sudo k3s kubectl logs -n rag deployment/bge-m3 --tail=20"

**Acceptance:** Все pods в Running/Ready. bge-m3 startup может занять до 6 мин (startupProbe: failureThreshold=72, periodSeconds=5 = 360s).

## Task 3.2: Smoke test ML

**Time:** 5 мин

Шаги:
1. Проверить BGE-M3 health:

        ssh vps "sudo k3s kubectl exec -n rag deployment/bge-m3 -- \
          python -c \"import urllib.request; print(urllib.request.urlopen('http://localhost:8000/health').read())\""

2. Тест encode:

        ssh vps "sudo k3s kubectl exec -n rag deployment/bge-m3 -- \
          python -c \"
        import urllib.request, json
        req = urllib.request.Request('http://localhost:8000/encode/dense',
          data=json.dumps({'texts': ['test']}).encode(), headers={'Content-Type': 'application/json'})
        r = json.loads(urllib.request.urlopen(req).read())
        print(f'Dense dims: {len(r[\"dense_vecs\"][0])}')\""

3. Проверить user-base health:

        ssh vps "sudo k3s kubectl exec -n rag deployment/user-base -- \
          python -c \"import urllib.request; print(urllib.request.urlopen('http://localhost:8000/health').read())\""

**Acceptance:** BGE-M3 dense_vecs[0] length = 1024, user-base healthy

---

# Phase 4: Application Layer (10 мин)

## Task 4.1: Проверить LiteLLM

**Time:** 3 мин

Шаги:
1. LiteLLM health:

        ssh vps "sudo k3s kubectl exec -n rag deployment/litellm -- \
          python -c \"import urllib.request; print(urllib.request.urlopen('http://localhost:4000/health/liveliness').read())\""

**Acceptance:** healthy

## Task 4.2: Проверить Bot

**Time:** 5 мин

Шаги:
1. Проверить pod status:

        ssh vps "sudo k3s kubectl get pod -n rag -l app=bot"

2. Проверить init containers завершились:

        ssh vps "sudo k3s kubectl describe pod -n rag -l app=bot | grep -A 2 'Init Containers:'"

3. Проверить логи бота:

        ssh vps "sudo k3s kubectl logs -n rag deployment/bot --tail=30"

4. Отправить тестовое сообщение в Telegram бот и проверить ответ

**Acceptance:** Bot pod Running, init containers Completed, ответ на Telegram сообщение получен

---

# Phase 5: Cleanup (10 мин)

## Task 5.1: Остановить Docker Compose

**Time:** 2 мин

ВНИМАНИЕ: Только после подтверждения что k3s stack работает полностью.

        ssh vps "cd /opt/rag-fresh && docker compose -f docker-compose.vps.yml down"

**Acceptance:** docker ps | grep vps = пусто

## Task 5.2: Освободить ресурсы Docker

**Time:** 3 мин

        # НЕ удаляем volumes (backup)
        ssh vps "docker image prune -f"
        ssh vps "docker builder prune -f"

**Acceptance:** docker system df показывает освобождённое место

## Task 5.3: Настроить k3s autostart

**Time:** 2 мин

k3s уже ставится как systemd service при установке. Проверить:

        ssh vps "sudo systemctl is-enabled k3s"

**Acceptance:** enabled

## Task 5.4: Обновить документацию

**Files:**
- Modify: CLAUDE.md (Deployment секция)
- Modify: .claude/rules/docker.md (VPS Stack секция)
- Modify: .claude/rules/k3s.md (добавить VPS deployed статус)
**Time:** 3 мин

Обновить:
- Deployment commands: docker compose -> kubectl/make k3s-*
- VPS Quick Commands: docker -> kubectl
- Troubleshooting: добавить k3s-specific issues

---

# Phase 6: Validation (15 мин)

## Task 6.1: Full system check

**Time:** 5 мин

        # All pods
        ssh vps "sudo k3s kubectl get pods -n rag -o wide"

        # Resources
        ssh vps "sudo k3s kubectl top pods -n rag"

        # Node resources
        ssh vps "sudo k3s kubectl top node"

        # Events (ошибки)
        ssh vps "sudo k3s kubectl get events -n rag --sort-by='.metadata.creationTimestamp' | tail -20"

**Acceptance:** Все pods Running/Ready, RAM < 11 GB, no Error events

## Task 6.2: Persistence check

**Time:** 5 мин

Шаги:
1. Удалить pod postgres (проверить что данные сохраняются):

        ssh vps "sudo k3s kubectl delete pod -n rag -l app=postgres"

2. Дождаться рестарта:

        ssh vps "sudo k3s kubectl get pods -n rag -l app=postgres -w"

3. Проверить данные:

        ssh vps "sudo k3s kubectl exec -n rag deployment/postgres -- psql -U postgres -c 'SELECT count(*) FROM information_schema.tables'"

**Acceptance:** Pod рестартовал, данные на месте

## Task 6.3: Ingestion test

**Time:** 5 мин

        # Scale up ingestion
        ssh vps "sudo k3s kubectl scale deployment ingestion -n rag --replicas=1"

        # Watch logs
        ssh vps "sudo k3s kubectl logs -n rag deployment/ingestion -f --tail=20"

        # Scale down after test
        ssh vps "sudo k3s kubectl scale deployment ingestion -n rag --replicas=0"

**Acceptance:** Ingestion стартует, подключается к зависимостям, обрабатывает файлы

---

## Test Strategy

| Тест | Когда | Что проверяем |
|------|-------|---------------|
| Core health | Phase 2 | pg_isready, redis ping, qdrant /collections |
| Data migration | Phase 2 | points_count = 278, postgres tables |
| ML inference | Phase 3 | BGE-M3 /encode/dense, user-base /health |
| Bot E2E | Phase 4 | Telegram message -> response |
| Persistence | Phase 6 | Pod restart -> data intact |
| Ingestion | Phase 6 | Scale up -> process files -> scale down |
| RAM budget | Phase 6 | kubectl top node < 11 GB |

## Acceptance Criteria

1. [ ] 8 pods Running/Ready в namespace rag (без ingestion)
2. [ ] Qdrant points_count = текущее значение (278+)
3. [ ] Telegram бот отвечает на сообщения
4. [ ] RAM usage < 11 GB (kubectl top node)
5. [ ] k3s autostart enabled (systemctl)
6. [ ] Docker Compose остановлен, volumes сохранены
7. [ ] Ingestion scale up/down работает
8. [ ] Pod restart не теряет данные (PVC)

## Risks

| Риск | Вероятность | Impact | Митигация |
|------|-------------|--------|-----------|
| RAM overflow (+700 MB k3s overhead) | Medium | High | eviction-hard в k3s-config.yaml, мониторить kubectl top |
| Data loss при миграции volumes | Low | Critical | pg_dump + qdrant snapshot ДО миграции |
| ML services OOMKill | Medium | Medium | startupProbe (6 мин), requests/limits в манифестах |
| Network connectivity (services) | Low | Medium | Init containers (busybox nc) проверяют доступность |
| Rollback needed | Low | Low | Docker Compose файлы + volumes остаются |

## MCP Research Summary

### Best Practices (Exa 2026)

1. **Kompose не рекомендуется для production** -- ручные манифесты надёжнее (уже сделано)
2. **Staged rollout** -- переносить сервисы группами, не big-bang
3. **k3s image import** -- docker save | k3s ctr import для custom images (без registry)
4. **local-path-provisioner** -- встроен в k3s, автоматически создаёт PVC на hostPath
5. **Pre-pull public images** -- загрузить заранее, не ждать при deploy
6. **k3s v1.33.7+k3s3** -- последний стабильный (Feb 2026), containerd v2.1.5

### Отличия от Docker Compose

| Docker Compose | k3s |
|---------------|-----|
| depends_on + healthcheck | initContainers (busybox nc) |
| profiles (core, bot, ingest) | Kustomize overlays |
| deploy.resources.limits | resources.requests/limits |
| docker volumes | PVC (local-path) |
| restart: unless-stopped | restartPolicy + k3s auto-restart |
| docker compose logs | kubectl logs |
| docker compose ps | kubectl get pods |

## Effort Estimate

| Фаза | Время | Кто |
|------|-------|-----|
| Phase 1: VPS prep | 30 мин | 1 воркер |
| Phase 2: Core | 20 мин | 1 воркер |
| Phase 3: ML | 15 мин | 1 воркер |
| Phase 4: App | 10 мин | 1 воркер |
| Phase 5: Cleanup | 10 мин | 1 воркер |
| Phase 6: Validation | 15 мин | 1 воркер |
| **Итого** | **~1.5 часа** | Sequential |

**Реальная оценка:** 3-5 часов (с учётом debug, volume migration gotchas, ML startup waits).
**Effort size:** XL (много VPS SSH, data migration, rollback scenarios).

## Dependencies Graph

    #70 Qdrant snapshots -----> Phase 1.1 (backup)
    #72 Slim images ----------> Phase 2.1 (smaller transfer)
    #73 k3s tuning -----------> Phase 1.2 (k3s-config.yaml уже готов)

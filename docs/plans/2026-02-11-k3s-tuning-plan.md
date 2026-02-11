# k3s Production Tuning (2026) -- Implementation Plan

**Issue:** [#73 — infra: k3s production tuning (2026 best practices)](https://github.com/yastman/rag/issues/73)
**Milestone:** Stream-F: Infra-Sec
**Priority:** Medium | **Effort:** High (~6 шагов, 2-5 мин каждый)

## Goal

Привести k3s single-node VPS (11 GB RAM, 55 GB SSD) к production-grade 2026 стандартам:
обновить k3s до v1.32+, добавить Trivy image scanning в CI/CD, настроить Gateway API,
оптимизировать resource limits по реальным метрикам, добавить NetworkPolicy, настроить
local-path-provisioner для бэкап-тома.

## Текущее состояние

**k3s config** (`k8s/k3s-config.yaml`):
- secrets-encryption: true
- eviction-hard: memory<200Mi, nodefs<10%, imagefs<15%
- eviction-soft: memory<500Mi с grace period 1m30s
- etcd snapshots: каждые 6 часов, retention 10
- kubelet: log rotation 10Mi/3 файла, image-gc 80-85%, pod-max-pids 4096

**Security (все deployments):**
- seccompProfile: RuntimeDefault (pod-level)
- allowPrivilegeEscalation: false
- capabilities.drop: ["ALL"] (кроме postgres — отсутствует)
- runAsNonRoot: true (qdrant, redis, litellm)

**Текущие image versions:**
- pgvector/pgvector:pg17 — postgres
- redis:8.4.0 — redis
- qdrant/qdrant:v1.16 — qdrant
- ghcr.io/berriai/litellm:main-v1.81.3-stable — litellm
- busybox:1.37 — init containers
- rag/bot:latest, rag/bge-m3:latest, rag/user-base:latest, rag/docling:latest, rag/ingestion:latest — custom

**CI/CD** (`.github/workflows/ci.yml`):
- lint → test → baseline-compare
- Нет Trivy scanning, нет image scanning

**Networking:**
- Только ClusterIP Services, нет Ingress/Gateway API
- Нет NetworkPolicy

## Шаги реализации

### Шаг 1: Trivy Image Scanning в CI/CD (~5 мин)

**Файлы:**
- `.github/workflows/ci.yml` — добавить job `security-scan` после `lint`

**Что делать:**
1. Добавить job `security-scan` с двумя шагами:
   - Scan k8s manifests: `trivy config ./k8s/ --severity HIGH,CRITICAL --exit-code 1`
   - Scan Dockerfiles: `trivy config . --severity HIGH,CRITICAL --file-patterns "Dockerfile*"`
2. Использовать `aquasecurity/trivy-action@master` для GitHub Actions
3. Формат вывода: `table` для PR comments, `sarif` для GitHub Security tab

**Пример job (отступ 4 пробела в YAML):**

    security-scan:
      name: Security Scan (Trivy)
      runs-on: ubuntu-latest
      needs: [lint]
      steps:
        - uses: actions/checkout@v4
        - name: Scan k8s manifests
          uses: aquasecurity/trivy-action@master
          with:
            scan-type: config
            scan-ref: ./k8s/
            format: table
            exit-code: 1
            severity: HIGH,CRITICAL
        - name: Scan Dockerfiles
          uses: aquasecurity/trivy-action@master
          with:
            scan-type: config
            scan-ref: .
            format: table
            exit-code: 1
            severity: HIGH,CRITICAL

**Acceptance:** CI pipeline blocks on HIGH/CRITICAL misconfigurations.

---

### Шаг 2: k3s Version Upgrade Path (~3 мин)

**Файлы:**
- `k8s/k3s-config.yaml` — обновить для совместимости с v1.32+
- `docs/plans/` — зафиксировать версию

**Текущие версии k3s (из scans.k3s.io, февраль 2026):**
- v1.35.0 (latest)
- v1.34.3
- v1.33.7
- v1.32.11

**Рекомендация:** k3s v1.32.11 (LTS-like, проверенный, containerd 2.x)

**Что делать:**
1. На VPS: проверить текущую версию `k3s --version`
2. Обновить: `curl -sfL https://get.k3s.io | INSTALL_K3S_VERSION=v1.32.11+k3s1 sh -`
3. Убедиться что config.yaml совместим (текущий формат OK для v1.32)
4. Добавить в k3s-config.yaml:

    # Audit logging (новое в v1.32)
    kube-apiserver-arg:
      - "audit-log-path=/var/log/k3s-audit.log"
      - "audit-log-maxage=30"
      - "audit-log-maxbackup=3"
      - "audit-log-maxsize=100"

**Acceptance:** `k3s --version` показывает v1.32.11+, все pods Running.

---

### Шаг 3: Resource Limits Tuning (~4 мин)

**Файлы:**
- `k8s/base/postgres/deployment.yaml:37-41` — добавить resource requests
- `k8s/base/bge-m3/deployment.yaml:42-47` — уточнить CPU request
- `k8s/base/redis/deployment.yaml:42-45` — сверить с реальным потреблением

**Проблема:** Total limits (~12.5 Gi) превышают VPS RAM (11 Gi). Нужна оптимизация.

**Что делать:**
1. На VPS собрать актуальные метрики:

    kubectl top pods -n rag --containers
    kubectl top node

2. Скорректировать limits на основе реальных данных. Ожидаемые изменения:
   - postgres: добавить `requests: memory: 128Mi, cpu: 50m` (сейчас missing)
   - bge-m3: если ONNX (issue #106), снизить limit с 4Gi до 2Gi
   - docling: проверить реальное потребление, возможно 1Gi достаточно
   - user-base: проверить, возможно 1Gi limit достаточно

3. Добавить `capabilities.drop: ["ALL"]` для postgres контейнера
   (`k8s/base/postgres/deployment.yaml:23` — добавить после `allowPrivilegeEscalation: false`)

**Acceptance:** `kubectl top node` показывает <80% memory utilization, все pods Running.

---

### Шаг 4: NetworkPolicy (~3 мин)

**Файлы:**
- `k8s/base/network-policies.yaml` — новый файл
- `k8s/base/kustomization.yaml:7` — добавить ресурс

**Что делать:**
1. Создать deny-all default policy для namespace `rag`
2. Разрешить только нужные connections:

    bot → redis:6379, qdrant:6333/6334, bge-m3:8000, user-base:8000, litellm:4000
    litellm → postgres:5432, egress to LLM APIs
    ingestion → postgres:5432, qdrant:6333, docling:5001, bge-m3:8000
    bge-m3 → нет исходящих (кроме DNS)
    qdrant → нет исходящих (кроме DNS)
    redis → нет исходящих (кроме DNS)

3. Добавить в kustomization.yaml:

    resources:
      - network-policies.yaml  # после namespace.yaml

**Acceptance:** Pods communicate only through allowed paths. `kubectl get networkpolicy -n rag` shows policies.

---

### Шаг 5: Local-Path Provisioner для бэкап-тома (~3 мин)

**Файлы:**
- `k8s/base/backup/` — новая директория
- `k8s/base/backup/pvc.yaml` — PVC для бэкапов
- `k8s/k3s-config.yaml` — ничего менять не нужно (local-path уже default в k3s)

**Что делать:**
1. Создать PVC с storageClassName: local-path:

    apiVersion: v1
    kind: PersistentVolumeClaim
    metadata:
      name: backup-data
    spec:
      accessModes: [ReadWriteOnce]
      storageClassName: local-path
      resources:
        requests:
          storage: 10Gi

2. Создать CronJob для бэкапа postgres:

    k8s/base/backup/cronjob.yaml — pg_dump каждые 12 часов
    Монтирует backup-data PVC
    Retention: последние 7 дампов

3. Добавить в base/kustomization.yaml

**Acceptance:** `kubectl get pvc -n rag` shows backup-data Bound, CronJob runs successfully.

---

### Шаг 6: Gateway API (исследование, опционально) (~5 мин)

**Файлы:**
- Не создаём пока — только исследование

**Контекст:**
- Gateway API стал GA в K8s 1.33+
- k3s v1.32 имеет beta поддержку через CRDs
- Для single-node VPS без внешнего Ingress — Gateway API не приоритет
- Бот использует polling (не webhook), Ingress не нужен

**Что делать:**
1. Отложить до момента когда понадобится webhook для бота или внешний API
2. Зафиксировать решение в этом плане: Gateway API = deferred
3. Если потребуется в будущем:
   - Установить Gateway API CRDs: `kubectl apply -f https://github.com/kubernetes-sigs/gateway-api/releases/download/v1.2.0/standard-install.yaml`
   - Использовать Traefik (встроен в k3s) как GatewayClass

**Acceptance:** Documented decision to defer. No changes needed now.

## Test Strategy

| Шаг | Тест | Команда |
|-----|------|---------|
| 1 | Trivy CI runs on PR | Создать PR, проверить job в Actions |
| 2 | k3s upgrade | `k3s --version`, `kubectl get nodes` |
| 3 | Resources | `kubectl top pods -n rag`, `kubectl describe node` |
| 4 | NetworkPolicy | `kubectl exec bot -- nc -z redis 6379` (OK), `kubectl exec bot -- nc -z postgres 5432` (blocked) |
| 5 | Backup | `kubectl get cronjob -n rag`, `kubectl logs job/backup-postgres-xxx` |
| 6 | N/A | Deferred |

## Acceptance Criteria

1. Trivy scanning blocks CI on HIGH/CRITICAL в k8s manifests и Dockerfiles
2. k3s на VPS обновлён до v1.32+ с audit logging
3. Resource limits оптимизированы по реальным метрикам, total < 11 Gi
4. NetworkPolicy ограничивает трафик между pods
5. Postgres бэкапится через CronJob на local-path PVC
6. Все pods Running после изменений: `make k3s-status`
7. Postgres deployment имеет `capabilities.drop: ["ALL"]`

## Effort Estimate

| Шаг | Время | Зависимости |
|-----|-------|-------------|
| 1. Trivy CI | 5 мин | нет |
| 2. k3s upgrade | 3 мин (план) + 10 мин (VPS) | VPS access |
| 3. Resource limits | 4 мин (plan) + VPS metrics | Шаг 2 |
| 4. NetworkPolicy | 3 мин | нет |
| 5. Backup CronJob | 3 мин | нет |
| 6. Gateway API | deferred | — |
| **Total** | ~18 мин code + VPS work | |

## Risks

- **RAM overcommit:** Total limits > VPS RAM. Шаг 3 критичен для стабильности.
- **k3s upgrade:** Нужен downtime 1-2 мин для рестарта k3s service.
- **NetworkPolicy + Flannel:** k3s использует Flannel по умолчанию — NetworkPolicy НЕ поддерживается.
  Нужно либо переключить CNI на Calico/Cilium, либо использовать `--flannel-backend=none` + Cilium.
  Альтернатива: k3s v1.32+ можно запустить с `--disable=flannel` и установить Cilium.

## Связанные issues

- #106 — BGE-M3 ONNX (влияет на resource limits bge-m3)
- CI/CD (`ci.yml`) — Trivy интегрируется в существующий pipeline

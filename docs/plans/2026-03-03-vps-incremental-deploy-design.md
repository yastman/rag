# VPS Incremental Deploy — Design

**Дата:** 2026-03-03
**Статус:** Утверждён
**Подход:** rsync (clean excludes) + rebuild bot only
**Предыдущий план:** `2026-03-02-vps-docker-migration-design.md` — выполнен

## Контекст

Plan от 2 марта **выполнен**: images обновлены (redis 8.6.0, qdrant v1.17.0, litellm stable),
код синхронизирован. Осталось:

- 29 новых коммитов (welcome redesign, viewing fixes, streaming sendMessageDraft)
- **Bot Exited(137)** — SIGKILL 7 часов назад (не OOM, логи показывают успешный старт)
- **bge-m3 unhealthy** — работает 25ч, healthcheck fails
- **litellm 92.85% RAM** (475/512MB) — near limit
- Ingestion только что запущен, Qdrant: 60 points

## VPS Status (live 2026-03-03)

| Параметр | Значение |
|----------|----------|
| Контейнеров | 8 running + **bot Exited(137)** |
| Images | Актуальны (redis 8.6.0, qdrant v1.17, litellm stable) |
| Код на VPS | commit `f9d5c7b` — **29 коммитов позади** main |
| RAM | 5.1 GB used, 6.5 GB available (из 11 GB) |
| Disk | 47 GB used, 50 GB free |
| Ingestion | Up 16s (healthy), Qdrant 60 points |

## Аудит: что чистили

### rsync excludes (добавлено в deploy-vps.sh)

| Категория | Исключено | Экономия |
|-----------|-----------|----------|
| Tests + eval | `tests/`, `evaluation/`, `coverage*`, `test_*.py` | ~5.5 MB |
| Documentation | `docs/` | ~11 MB |
| Unused infra | `k8s/`, `legacy/`, `deploy/` | ~420 KB |
| Planning | `.planning/`, `.signals/`, `*.session` | ~330 KB |
| Legacy | `requirements*.txt` | ~1 KB |
| **Итого** | | **~28 MB** (48% transfer savings) |

### Docker cleanup

- Удалён `COLBERT_TIMEOUT` из bot env (ColBERT отключён — `RERANK_PROVIDER=none`)
- Dockerfile.ingestion и src/api/Dockerfile **оставлены как есть** — `telegram_bot/`
  реально импортируется из `src/` (apartment_models, bge_m3_client, observability, graph)

## Решения

| Решение | Выбор | Причина |
|---------|-------|---------|
| Rebuild scope | Только bot | Dockerfile/deps не менялись, только код telegram_bot/ |
| Clean deploy? | НЕТ | Images актуальны, volumes на месте, данные в Qdrant |
| bge-m3 | restart | Unhealthy но работает 25ч — скорее всего healthcheck timeout |
| litellm | мониторить | 92.85% RAM — пока работает, может потребоваться увеличение лимита |

## Архитектура

```
WSL2                                  VPS
┌──────────────┐   rsync (~2MB)  ┌────────────────────────┐
│ 29 commits:  │ ─────────────→  │ /opt/rag-fresh/        │
│ - welcome    │  (clean excl.)  │                        │
│ - viewing    │                 │ 1. build bot only      │
│ - streaming  │                 │ 2. up -d bot           │
│ - langfuse   │                 │ 3. restart bge-m3      │
└──────────────┘                 │ 4. verify 9/9          │
                                 └────────────────────────┘
```

## Риски

| Риск | Митигация |
|------|-----------|
| Bot fails again (137) | Проверить docker events, dmesg на OOM-killer |
| bge-m3 не восстановится | docker logs, при необходимости rebuild |
| litellm OOM (92.85%) | Увеличить memory limit до 768M если падает |

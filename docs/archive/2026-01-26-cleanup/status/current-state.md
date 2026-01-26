# Текущее состояние проекта

> **Версия:** 2.8.0 | **Дата:** 2026-01-21

---

## Статус компонентов

### Работает локально

| Компонент | Статус | Порт | Примечание |
|-----------|--------|------|------------|
| Qdrant | Ready | 6333 | docker-compose.local.yml |
| Redis Stack | Ready | 6379 | С RediSearch для semantic cache |
| BGE-M3 API | Ready | 8000 | Embeddings service |
| Docling | Ready | 5001 | Document parsing |
| RAG Pipeline | Ready | - | src/core/pipeline.py |
| Telegram Bot | Ready | - | telegram_bot/ |

### Требует настройки для Production

| Компонент | Статус | Что нужно |
|-----------|--------|-----------|
| MLflow | Partial | Настроить PostgreSQL backend |
| Langfuse | Partial | Настроить PostgreSQL + credentials |
| Prometheus | Not setup | Добавить в docker-compose |
| Grafana | Not setup | Добавить dashboards |
| SSL/TLS | Not setup | Nginx reverse proxy |
| Backup | Not setup | Qdrant snapshots + Redis RDB |

---

## Версии

| Зависимость | Версия | Примечание |
|-------------|--------|------------|
| Python | 3.12.3 | pyproject.toml |
| Qdrant | 1.15.4 (local), 1.16 (dev) | docker-compose |
| Redis Stack | 8.2 | С RediSearch модулем |
| BGE-M3 | latest | BAAI/bge-m3 |
| Aiogram | 3.15.0 | Telegram bot framework |

---

## Метрики качества

| Метрика | Текущее | Цель |
|---------|---------|------|
| Recall@10 | 0.96 | >=0.95 |
| NDCG@10 | 0.98 | >=0.95 |
| Search latency | ~1.0s | <1.5s |
| Cache hit rate | 70-80% | >70% |
| RAM usage | ~6GB | <4GB |

---

## Известные проблемы

1. **RAM usage высокий** — BGE-M3 singleton помогает, но всё ещё ~6GB
2. **Нет distributed lock** — race condition в semantic cache (Task 2.2)
3. **Нет rate limiting** — Telegram bot уязвим к spam (Task 2.3)

---

**Последнее обновление:** 2026-01-21

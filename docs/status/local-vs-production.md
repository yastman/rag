# Local vs Production: Чеклист готовности

---

## Что работает локально

Всё из docker-compose.local.yml:
- Qdrant (vector database)
- Redis Stack (caching + vector search)
- BGE-M3 API (embeddings)
- Docling (document parsing)

Код:
- RAG Pipeline (src/core/)
- Search Engines (src/retrieval/)
- Telegram Bot (telegram_bot/)
- Ingestion (src/ingestion/)

---

## Чеклист для Production

### Critical (блокирует деплой)

- [ ] **Secrets management**
  - [ ] Все API ключи в .env (не в коде!)
  - [ ] .env.server настроен на VPS
  - [ ] Qdrant API key ротирован (был exposed)

- [ ] **Services running**
  - [ ] Qdrant доступен и отвечает
  - [ ] Redis доступен и отвечает
  - [ ] BGE-M3 API загружен и отвечает
  - [ ] Telegram Bot подключен к API

### High (нужно для стабильности)

- [ ] **Monitoring**
  - [ ] Логи пишутся в файл (LOG_FILE env var)
  - [ ] JSON формат логов включен
  - [ ] Health checks настроены

- [ ] **Resilience**
  - [ ] Graceful degradation работает
  - [ ] Fallback answers при LLM failure
  - [ ] Timeouts настроены (10s default)

### Medium (улучшает надёжность)

- [ ] **Infrastructure**
  - [ ] docker-compose.yml для всех сервисов
  - [ ] Systemd services для auto-restart
  - [ ] Backup strategy для Qdrant

- [ ] **Security**
  - [ ] Rate limiting для bot
  - [ ] SSL/TLS (nginx reverse proxy)
  - [ ] Firewall rules

### Nice-to-have

- [ ] **Observability**
  - [ ] MLflow для experiment tracking
  - [ ] Langfuse для LLM tracing
  - [ ] Prometheus metrics
  - [ ] Grafana dashboards

- [ ] **CI/CD**
  - [ ] GitHub Actions для tests
  - [ ] Auto-deploy on tag

---

## Различия окружений

| Аспект | Local | Production |
|--------|-------|------------|
| **Путь** | /mnt/c/.../rag-fresh | /srv/contextual_rag |
| **Qdrant** | localhost:6333 | localhost:6333 (или remote) |
| **Redis** | localhost:6379 | localhost:6379 (secure) |
| **Logs** | Console | JSON file |
| **SSL** | Нет | Nginx + Let's Encrypt |
| **Backup** | Нет | Qdrant snapshots |

---

## Команды деплоя

```bash
# На VPS
cd /srv/contextual_rag
git pull origin main

# Перезапуск сервисов
sudo systemctl restart telegram-bot

# Проверка статуса
sudo systemctl status telegram-bot
curl localhost:6333/health
```

---

**Последнее обновление:** 2026-01-21

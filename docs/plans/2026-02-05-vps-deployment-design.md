# VPS Deployment Design

Деплой RAG чат-бота на VPS сервер (алиас `vps`).

## Контекст

- **VPS:** 16GB RAM
- **Коллекция:** `gdrive_documents_bge` (тестовая, переиндексируем на месте)
- **Google Drive:** OAuth token (скопируем с локальной машины)
- **Embeddings:** BGE-M3 локально (без Voyage API)

## Архитектура

```
┌─────────────────────────────────────────────────────────────┐
│                         VPS (16GB)                          │
├─────────────────────────────────────────────────────────────┤
│  Google Drive ──rclone sync──► ~/drive-sync/                │
│                                     │                       │
│                          CocoIndex FlowLiveUpdater          │
│                                     │                       │
│  ┌──────────┐  ┌─────────┐  ┌──────────────┐               │
│  │ Docling  │  │ BGE-M3  │  │   Qdrant     │               │
│  │ (parse)  │──│ (embed) │──│  (vectors)   │               │
│  └──────────┘  └─────────┘  └──────────────┘               │
│                     │              │                        │
│              ┌──────┴──────┐       │                        │
│              │   BM42      │       │                        │
│              │  (sparse)   │───────┤                        │
│              └─────────────┘       │                        │
│                                    │                        │
│  ┌──────────┐  ┌─────────┐  ┌─────┴────────┐               │
│  │ LiteLLM  │──│  Bot    │──│    Redis     │               │
│  │ (LLM GW) │  │ (TG)    │  │   (cache)    │               │
│  └──────────┘  └─────────┘  └──────────────┘               │
│       │                                                     │
│  Cerebras/Groq/OpenAI (external APIs)                      │
└─────────────────────────────────────────────────────────────┘
```

## Сервисы

| Сервис | RAM | Порт | Назначение |
|--------|-----|------|------------|
| postgres | 512MB | 5432 | БД для LiteLLM/CocoIndex state |
| redis | 300MB | 6379 | Semantic cache, rerank cache |
| qdrant | 1GB | 6333 | Векторная БД |
| **docling** | 3GB | 5001 | Document parsing (PDF/DOCX/etc.) |
| bge-m3 | 4GB | 8000 | Dense embeddings + ColBERT rerank |
| user-base | 2GB | 8003 | Semantic cache embeddings (USER2-base) |
| bm42 | 1GB | 8002 | Sparse embeddings (BM42) |
| litellm | 512MB | 4000 | LLM gateway с fallback chain |
| bot | 512MB | - | Telegram бот |
| **ingestion** | 512MB | - | CocoIndex pipeline (profile: ingest) |

**Итого:** ~13GB RAM (runtime) / ~14GB с ingestion

## Файлы для переноса

| Файл | Источник | Назначение на VPS |
|------|----------|-------------------|
| Репозиторий | `git clone` | `/opt/rag-fresh/` |
| rclone.conf | `~/.config/rclone/rclone.conf` | `~/.config/rclone/rclone.conf` |
| .env | Создать | `/opt/rag-fresh/.env` |

## Переменные окружения

```bash
# === Обязательные ===
TELEGRAM_BOT_TOKEN=xxx
LITELLM_MASTER_KEY=sk-xxx  # любой секрет для LiteLLM

# === LLM провайдеры (минимум один) ===
CEREBRAS_API_KEY=xxx       # primary
GROQ_API_KEY=xxx           # fallback 1
OPENAI_API_KEY=xxx         # fallback 2

# === VPS-специфичные (уже в docker-compose.vps.yml) ===
# RETRIEVAL_DENSE_PROVIDER=bge_m3_api
# RERANK_PROVIDER=colbert
# USE_LOCAL_EMBEDDINGS=true
```

## Команды деплоя

```bash
# 1. Подготовка VPS
ssh vps
sudo apt update && sudo apt install -y docker.io docker-compose-v2
sudo usermod -aG docker $USER
curl https://rclone.org/install.sh | sudo bash

# 2. Клонирование репо
sudo mkdir -p /opt/rag-fresh
sudo chown $USER:$USER /opt/rag-fresh
git clone https://github.com/USER/rag-fresh.git /opt/rag-fresh

# 3. Копирование конфигов (с локальной машины)
scp ~/.config/rclone/rclone.conf vps:~/.config/rclone/
scp .env vps:/opt/rag-fresh/.env

# 4. Запуск стека
cd /opt/rag-fresh
docker compose -f docker-compose.vps.yml up -d

# 5. Первичная синхронизация Google Drive
rclone sync gdrive:RAG ~/drive-sync/ --progress

# 6. Индексация
make ingest-unified
```

## Проверка

```bash
# Статус контейнеров
docker ps --format "table {{.Names}}\t{{.Status}}"

# Здоровье бота
docker logs vps-bot --tail 50

# Qdrant коллекция
curl -s localhost:6333/collections/gdrive_documents_bge | jq '.result.points_count'

# Тест rclone
rclone ls gdrive:RAG
```

## Cron для rclone

```bash
# /etc/cron.d/rclone-sync
*/5 * * * * user rclone sync gdrive:RAG /home/user/drive-sync/ -q --log-file /var/log/rclone-sync.log
```

## Риски и митигация

| Риск | Митигация |
|------|-----------|
| OAuth token expire | Refresh token автообновляется; если нет — re-auth через `rclone config reconnect gdrive:` |
| Первый запуск долгий (модели) | Ожидаемо 15-30 мин на загрузку моделей с HuggingFace |
| Нехватка RAM | Мониторить `htop`; при проблемах отключить user-base |

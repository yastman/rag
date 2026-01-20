# Dev Workflow Design: Локальная разработка → GitHub → Deploy

**Дата:** 2026-01-20
**Статус:** Approved
**Автор:** Claude + User

---

## Обзор

Настройка полного dev workflow для проекта Contextual RAG:
- Локальная разработка на Windows + WSL2 с полным Docker стеком
- CI/CD через GitHub Actions
- Два режима deploy: быстрый (код) и релизный (Docker)

---

## 1. Архитектура

```
┌─────────────────────────────────────────────────────────────────┐
│                    ЛОКАЛЬНАЯ МАШИНА (WSL2)                      │
├─────────────────────────────────────────────────────────────────┤
│  Docker Desktop                                                  │
│  ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐              │
│  │ Qdrant  │ │  Redis  │ │ BGE-M3  │ │ Docling │              │
│  │  :6333  │ │  :6379  │ │  :8001  │ │  :5001  │              │
│  └─────────┘ └─────────┘ └─────────┘ └─────────┘              │
│                                                                  │
│  VS Code / PyCharm                                              │
│  ┌──────────────────────────────────────────────┐              │
│  │  contextual_rag/                              │              │
│  │  - src/          (RAG pipeline)               │              │
│  │  - telegram_bot/ (Telegram бот)               │              │
│  │  - tests/        (тесты)                      │              │
│  └──────────────────────────────────────────────┘              │
└───────────────────────────┬─────────────────────────────────────┘
                            │ git push
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│                      GITHUB (yastman/rag)                        │
├─────────────────────────────────────────────────────────────────┤
│  main branch ──────► GitHub Actions                             │
│                      ├── tests (pytest)                         │
│                      ├── lint (ruff)                            │
│                      └── deploy trigger                         │
└───────────────────────────┬─────────────────────────────────────┘
                            │ SSH / Docker
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│                 ПРОДАКШН СЕРВЕР (95.111.252.29)                 │
├─────────────────────────────────────────────────────────────────┤
│  Быстрый deploy (код):     │  Релизный deploy (Docker):        │
│  - git pull                │  - docker build                    │
│  - systemctl restart bot   │  - docker push to registry         │
│                            │  - docker pull + restart           │
└─────────────────────────────────────────────────────────────────┘
```

**Два режима deploy:**
- **Quick** (тег `deploy-code`) — только `git pull` + restart, для hotfixes
- **Release** (тег `v*.*.*`) — полный Docker build/push/pull, для релизов

---

## 2. Локальная среда (docker-compose.local.yml)

```yaml
version: "3.8"

services:
  qdrant:
    image: qdrant/qdrant:v1.15.4
    ports:
      - "6333:6333"
    volumes:
      - qdrant_data:/qdrant/storage
    environment:
      - QDRANT__SERVICE__GRPC_PORT=6334

  redis:
    image: redis/redis-stack:7.4.0-v3
    ports:
      - "6379:6379"
      - "8001:8001"  # RedisInsight
    volumes:
      - redis_data:/data

  bge-m3:
    image: ghcr.io/yastman/bge-m3:latest
    ports:
      - "8001:8001"
    deploy:
      resources:
        reservations:
          devices:
            - capabilities: [gpu]  # опционально

  docling:
    image: ghcr.io/ds4sd/docling-serve:latest
    ports:
      - "5001:5001"

volumes:
  qdrant_data:
  redis_data:
```

**Требования:**
- Docker Desktop с WSL2 интеграцией
- 16GB RAM (12GB для WSL)
- ~20GB свободного места

---

## 3. GitHub Actions

### 3.1 CI Pipeline (.github/workflows/ci.yml)

```yaml
name: CI

on:
  push:
    branches: [main, development]
  pull_request:
    branches: [main]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - name: Install dependencies
        run: |
          pip install -e ".[dev]"
      - name: Lint
        run: ruff check src/ telegram_bot/ tests/
      - name: Type check
        run: mypy src/ --ignore-missing-imports
      - name: Tests
        run: pytest tests/ -v --ignore=tests/legacy/
```

### 3.2 Deploy Pipeline (.github/workflows/deploy.yml)

```yaml
name: Deploy

on:
  push:
    tags:
      - 'v*.*.*'      # Release deploy (Docker)
      - 'deploy-code' # Quick deploy (git pull only)

jobs:
  deploy-code:
    if: github.ref == 'refs/tags/deploy-code'
    runs-on: ubuntu-latest
    steps:
      - name: Deploy via SSH
        uses: appleboy/ssh-action@v1
        with:
          host: ${{ secrets.SERVER_HOST }}
          username: ${{ secrets.SERVER_USER }}
          key: ${{ secrets.SSH_PRIVATE_KEY }}
          script: |
            cd /home/admin/contextual_rag
            git pull origin main
            sudo systemctl restart telegram-bot

  deploy-release:
    if: startsWith(github.ref, 'refs/tags/v')
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Build & Push Docker
        run: |
          echo ${{ secrets.GHCR_TOKEN }} | docker login ghcr.io -u ${{ github.actor }} --password-stdin
          docker build -t ghcr.io/yastman/rag-bot:${{ github.ref_name }} .
          docker push ghcr.io/yastman/rag-bot:${{ github.ref_name }}
      - name: Deploy via SSH
        uses: appleboy/ssh-action@v1
        with:
          host: ${{ secrets.SERVER_HOST }}
          username: ${{ secrets.SERVER_USER }}
          key: ${{ secrets.SSH_PRIVATE_KEY }}
          script: |
            docker pull ghcr.io/yastman/rag-bot:${{ github.ref_name }}
            cd /home/admin && docker compose up -d rag-bot
```

---

## 4. GitHub Secrets

| Secret | Значение |
|--------|----------|
| `SERVER_HOST` | `95.111.252.29` |
| `SERVER_USER` | `admin` |
| `SSH_PRIVATE_KEY` | Приватный SSH ключ |
| `GHCR_TOKEN` | GitHub Personal Access Token |

---

## 5. Настройка сервера

### 5.1 Systemd сервис

```ini
# /etc/systemd/system/telegram-bot.service
[Unit]
Description=RAG Telegram Bot
After=network.target docker.service

[Service]
Type=simple
User=admin
WorkingDirectory=/home/admin/contextual_rag
Environment=PATH=/home/admin/contextual_rag/venv/bin:/usr/bin
ExecStart=/home/admin/contextual_rag/venv/bin/python -m telegram_bot.main
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

### 5.2 Sudoers правило

```bash
# /etc/sudoers.d/telegram-bot
admin ALL=(ALL) NOPASSWD: /bin/systemctl restart telegram-bot
```

### 5.3 SSH ключ

Добавить публичный ключ GitHub Actions в `~/.ssh/authorized_keys`

---

## 6. Локальный workflow

### Первоначальная настройка

```bash
# 1. Клонировать
git clone https://github.com/yastman/rag.git contextual_rag
cd contextual_rag

# 2. Виртуальное окружение
python3.12 -m venv venv
source venv/bin/activate

# 3. Зависимости
pip install -e ".[dev]"

# 4. Конфиг
cp .env.example .env
# Заполнить API ключи

# 5. Локальные сервисы
docker compose -f docker-compose.local.yml up -d

# 6. Pre-commit hooks
pre-commit install
```

### Ежедневная работа

```bash
# Запуск
docker compose -f docker-compose.local.yml up -d
source venv/bin/activate

# Разработка
code .
make test
make lint

# Коммит
git add .
git commit -m "feat: описание"
git push origin main

# Quick deploy
git tag -d deploy-code 2>/dev/null
git tag deploy-code
git push origin deploy-code --force

# Release deploy
git tag v2.6.0
git push origin v2.6.0
```

---

## 7. Файлы для создания

| Файл | Статус |
|------|--------|
| `docker-compose.local.yml` | TODO |
| `.github/workflows/ci.yml` | TODO |
| `.github/workflows/deploy.yml` | TODO |
| `/etc/systemd/system/telegram-bot.service` | TODO (на сервере) |
| `/etc/sudoers.d/telegram-bot` | TODO (на сервере) |
| `.env.local.example` | TODO |
| `CONTRIBUTING.md` | TODO |

---

## 8. Checklist реализации

- [ ] Создать `docker-compose.local.yml`
- [ ] Создать `.github/workflows/ci.yml`
- [ ] Создать `.github/workflows/deploy.yml`
- [ ] Настроить GitHub Secrets
- [ ] Создать systemd сервис на сервере
- [ ] Настроить sudoers на сервере
- [ ] Сгенерировать SSH ключ для GitHub Actions
- [ ] Добавить SSH ключ в authorized_keys
- [ ] Создать `.env.local.example`
- [ ] Создать `CONTRIBUTING.md`
- [ ] Протестировать CI pipeline
- [ ] Протестировать quick deploy
- [ ] Протестировать release deploy

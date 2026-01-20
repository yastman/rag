# Dev Workflow Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Настроить полный dev workflow: локальная разработка на WSL2 → GitHub Actions CI/CD → deploy на сервер

**Architecture:** Локальный Docker стек (Qdrant, Redis, BGE-M3, Docling) для разработки. GitHub Actions для CI (тесты, линт) и CD (два режима deploy: quick code и full Docker release).

**Tech Stack:** Docker Compose, GitHub Actions, systemd, SSH, Python 3.12, Ruff, pytest

---

## Task 1: Добавить BGE-M3 API в репозиторий

**Files:**
- Create: `services/bge-m3-api/Dockerfile`
- Create: `services/bge-m3-api/app.py`
- Create: `services/bge-m3-api/config.py`
- Create: `services/bge-m3-api/requirements.txt`
- Modify: `.gitignore`

**Step 1: Создать директорию services/bge-m3-api**

```bash
mkdir -p services/bge-m3-api
```

**Step 2: Скопировать файлы BGE-M3 API**

```bash
cp /home/admin/bge-m3-api/Dockerfile services/bge-m3-api/
cp /home/admin/bge-m3-api/app.py services/bge-m3-api/
cp /home/admin/bge-m3-api/config.py services/bge-m3-api/
cp /home/admin/bge-m3-api/requirements.txt services/bge-m3-api/
```

**Step 3: Добавить исключения в .gitignore**

Добавить в конец `.gitignore`:
```
# BGE-M3 models cache
services/bge-m3-api/models/
*.pt
*.bin
*.safetensors
```

**Step 4: Проверить структуру**

```bash
ls -la services/bge-m3-api/
```

Expected: 4 файла (Dockerfile, app.py, config.py, requirements.txt)

**Step 5: Commit**

```bash
git add services/bge-m3-api/ .gitignore
git commit -m "feat: add BGE-M3 API service for local development"
```

---

## Task 2: Создать docker-compose.local.yml

**Files:**
- Create: `docker-compose.local.yml`
- Create: `.env.local.example`

**Step 1: Создать docker-compose.local.yml**

```yaml
# docker-compose.local.yml
# Локальная среда разработки для RAG проекта
# Запуск: docker compose -f docker-compose.local.yml up -d

version: "3.8"

services:
  # Vector Database
  qdrant:
    image: qdrant/qdrant:v1.15.4
    container_name: rag-qdrant
    ports:
      - "6333:6333"
      - "6334:6334"
    volumes:
      - qdrant_data:/qdrant/storage
    environment:
      - QDRANT__SERVICE__GRPC_PORT=6334
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:6333/readyz"]
      interval: 10s
      timeout: 5s
      retries: 3

  # Redis with Vector Search
  redis:
    image: redis/redis-stack:7.4.0-v3
    container_name: rag-redis
    ports:
      - "6379:6379"
      - "8002:8001"  # RedisInsight на 8002 (8001 занят BGE-M3)
    volumes:
      - redis_data:/data
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 10s
      timeout: 5s
      retries: 3

  # BGE-M3 Embeddings API
  bge-m3:
    build:
      context: ./services/bge-m3-api
      dockerfile: Dockerfile
    container_name: rag-bge-m3
    ports:
      - "8001:8000"
    volumes:
      - bge_models:/models
    environment:
      - OMP_NUM_THREADS=4
      - MKL_NUM_THREADS=4
      - MODEL_CACHE_DIR=/models
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/health"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 120s
    deploy:
      resources:
        limits:
          memory: 4G

  # Docling Document Parser
  docling:
    image: ds4sd/docling-serve:latest
    container_name: rag-docling
    ports:
      - "5001:5001"
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:5001/health"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 60s

volumes:
  qdrant_data:
  redis_data:
  bge_models:
```

**Step 2: Создать .env.local.example**

```bash
# .env.local.example
# Шаблон для локальной разработки
# Скопируйте в .env и заполните значения

# === API Keys ===
OPENAI_API_KEY=sk-your-openai-key
ANTHROPIC_API_KEY=sk-ant-your-anthropic-key
GROQ_API_KEY=gsk_your-groq-key

# === Local Services (docker-compose.local.yml) ===
QDRANT_URL=http://localhost:6333
QDRANT_API_KEY=  # Пустой для локальной разработки
BGE_M3_URL=http://localhost:8001
DOCLING_URL=http://localhost:5001
REDIS_URL=redis://localhost:6379

# === Telegram Bot (опционально) ===
TELEGRAM_BOT_TOKEN=your-bot-token

# === LLM Settings ===
LLM_MODEL=gpt-4o-mini
LLM_BASE_URL=https://api.openai.com/v1
```

**Step 3: Проверить синтаксис docker-compose**

```bash
docker compose -f docker-compose.local.yml config --quiet && echo "OK"
```

Expected: OK (без ошибок)

**Step 4: Commit**

```bash
git add docker-compose.local.yml .env.local.example
git commit -m "feat: add local development Docker Compose configuration"
```

---

## Task 3: Создать GitHub Actions CI pipeline

**Files:**
- Create: `.github/workflows/ci.yml`

**Step 1: Создать директорию .github/workflows**

```bash
mkdir -p .github/workflows
```

**Step 2: Создать ci.yml**

```yaml
# .github/workflows/ci.yml
name: CI

on:
  push:
    branches: [main, development]
  pull_request:
    branches: [main]

jobs:
  lint:
    name: Lint & Type Check
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: "3.12"
          cache: "pip"

      - name: Install dependencies
        run: |
          pip install ruff mypy
          pip install -e ".[dev]" || pip install -e .

      - name: Ruff lint
        run: ruff check src/ telegram_bot/ tests/ --output-format=github

      - name: Ruff format check
        run: ruff format --check src/ telegram_bot/ tests/

      - name: Type check
        run: mypy src/ --ignore-missing-imports --no-error-summary || true

  test:
    name: Tests
    runs-on: ubuntu-latest
    needs: lint
    steps:
      - uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: "3.12"
          cache: "pip"

      - name: Install dependencies
        run: |
          pip install pytest pytest-cov pytest-asyncio
          pip install -e ".[dev]" || pip install -e .

      - name: Run tests
        run: |
          pytest tests/ -v \
            --ignore=tests/legacy/ \
            --ignore=tests/test_qdrant_connection.py \
            --ignore=tests/test_redis_cache.py \
            -x --tb=short
        env:
          QDRANT_URL: http://localhost:6333
          BGE_M3_URL: http://localhost:8001
```

**Step 3: Проверить YAML синтаксис**

```bash
python -c "import yaml; yaml.safe_load(open('.github/workflows/ci.yml'))" && echo "OK"
```

Expected: OK

**Step 4: Commit**

```bash
git add .github/workflows/ci.yml
git commit -m "ci: add GitHub Actions CI pipeline for linting and testing"
```

---

## Task 4: Создать GitHub Actions Deploy pipeline

**Files:**
- Create: `.github/workflows/deploy.yml`

**Step 1: Создать deploy.yml**

```yaml
# .github/workflows/deploy.yml
name: Deploy

on:
  push:
    tags:
      - "v*.*.*"       # Release deploy (Docker build + push)
      - "deploy-code"  # Quick deploy (git pull only)

env:
  REGISTRY: ghcr.io
  IMAGE_NAME: ${{ github.repository }}-bot

jobs:
  # Quick deploy - только git pull + restart
  deploy-code:
    name: Quick Deploy (Code Only)
    if: github.ref == 'refs/tags/deploy-code'
    runs-on: ubuntu-latest
    steps:
      - name: Deploy via SSH
        uses: appleboy/ssh-action@v1.0.3
        with:
          host: ${{ secrets.SERVER_HOST }}
          username: ${{ secrets.SERVER_USER }}
          key: ${{ secrets.SSH_PRIVATE_KEY }}
          script: |
            cd /home/admin/contextual_rag
            git fetch origin main
            git reset --hard origin/main
            sudo systemctl restart telegram-bot
            echo "Deploy completed at $(date)"

  # Release deploy - полный Docker workflow
  deploy-release:
    name: Release Deploy (Docker)
    if: startsWith(github.ref, 'refs/tags/v')
    runs-on: ubuntu-latest
    permissions:
      contents: read
      packages: write

    steps:
      - uses: actions/checkout@v4

      - name: Log in to Container Registry
        uses: docker/login-action@v3
        with:
          registry: ${{ env.REGISTRY }}
          username: ${{ github.actor }}
          password: ${{ secrets.GITHUB_TOKEN }}

      - name: Extract version
        id: version
        run: echo "VERSION=${GITHUB_REF#refs/tags/}" >> $GITHUB_OUTPUT

      - name: Build and push Docker image
        uses: docker/build-push-action@v5
        with:
          context: .
          push: true
          tags: |
            ${{ env.REGISTRY }}/${{ env.IMAGE_NAME }}:${{ steps.version.outputs.VERSION }}
            ${{ env.REGISTRY }}/${{ env.IMAGE_NAME }}:latest

      - name: Deploy to server
        uses: appleboy/ssh-action@v1.0.3
        with:
          host: ${{ secrets.SERVER_HOST }}
          username: ${{ secrets.SERVER_USER }}
          key: ${{ secrets.SSH_PRIVATE_KEY }}
          script: |
            docker pull ${{ env.REGISTRY }}/${{ env.IMAGE_NAME }}:${{ steps.version.outputs.VERSION }}
            cd /home/admin
            docker compose up -d telegram-bot
            echo "Release ${{ steps.version.outputs.VERSION }} deployed at $(date)"
```

**Step 2: Проверить YAML синтаксис**

```bash
python -c "import yaml; yaml.safe_load(open('.github/workflows/deploy.yml'))" && echo "OK"
```

Expected: OK

**Step 3: Commit**

```bash
git add .github/workflows/deploy.yml
git commit -m "ci: add GitHub Actions deploy pipeline (quick + release modes)"
```

---

## Task 5: Создать конфигурацию сервера

**Files:**
- Create: `deploy/telegram-bot.service`
- Create: `deploy/sudoers-telegram-bot`
- Create: `deploy/README.md`

**Step 1: Создать директорию deploy**

```bash
mkdir -p deploy
```

**Step 2: Создать telegram-bot.service**

```ini
# deploy/telegram-bot.service
# Systemd unit для Telegram бота
# Установка: sudo cp deploy/telegram-bot.service /etc/systemd/system/
#            sudo systemctl daemon-reload
#            sudo systemctl enable telegram-bot

[Unit]
Description=RAG Telegram Bot
After=network.target docker.service
Wants=docker.service

[Service]
Type=simple
User=admin
Group=admin
WorkingDirectory=/home/admin/contextual_rag
Environment=PATH=/home/admin/contextual_rag/venv/bin:/usr/local/bin:/usr/bin:/bin
EnvironmentFile=/home/admin/contextual_rag/telegram_bot/.env

ExecStart=/home/admin/contextual_rag/venv/bin/python -m telegram_bot.main
ExecReload=/bin/kill -HUP $MAINPID

Restart=always
RestartSec=10
StandardOutput=journal
StandardError=journal
SyslogIdentifier=telegram-bot

# Security hardening
NoNewPrivileges=true
ProtectSystem=strict
ProtectHome=read-only
ReadWritePaths=/home/admin/contextual_rag/telegram_bot

[Install]
WantedBy=multi-user.target
```

**Step 3: Создать sudoers правило**

```bash
# deploy/sudoers-telegram-bot
# Разрешить admin перезапускать telegram-bot без пароля
# Установка: sudo cp deploy/sudoers-telegram-bot /etc/sudoers.d/telegram-bot
#            sudo chmod 440 /etc/sudoers.d/telegram-bot

admin ALL=(ALL) NOPASSWD: /bin/systemctl restart telegram-bot
admin ALL=(ALL) NOPASSWD: /bin/systemctl start telegram-bot
admin ALL=(ALL) NOPASSWD: /bin/systemctl stop telegram-bot
admin ALL=(ALL) NOPASSWD: /bin/systemctl status telegram-bot
```

**Step 4: Создать deploy/README.md**

```markdown
# Server Deployment Configuration

## Files

| File | Destination | Purpose |
|------|-------------|---------|
| `telegram-bot.service` | `/etc/systemd/system/` | Systemd unit |
| `sudoers-telegram-bot` | `/etc/sudoers.d/telegram-bot` | Passwordless restart |

## Installation

```bash
# 1. Copy systemd unit
sudo cp deploy/telegram-bot.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable telegram-bot

# 2. Copy sudoers rule
sudo cp deploy/sudoers-telegram-bot /etc/sudoers.d/telegram-bot
sudo chmod 440 /etc/sudoers.d/telegram-bot

# 3. Start service
sudo systemctl start telegram-bot
sudo systemctl status telegram-bot
```

## GitHub Actions Secrets

Configure in GitHub repo → Settings → Secrets → Actions:

| Secret | Value |
|--------|-------|
| `SERVER_HOST` | `95.111.252.29` |
| `SERVER_USER` | `admin` |
| `SSH_PRIVATE_KEY` | Private key for SSH access |

### Generate SSH Key for GitHub Actions

```bash
# On local machine
ssh-keygen -t ed25519 -C "github-actions-deploy" -f ~/.ssh/github_actions

# Copy public key to server
ssh-copy-id -i ~/.ssh/github_actions.pub admin@95.111.252.29

# Add private key content to GitHub Secrets as SSH_PRIVATE_KEY
cat ~/.ssh/github_actions
```
```

**Step 5: Commit**

```bash
git add deploy/
git commit -m "feat: add server deployment configuration (systemd, sudoers)"
```

---

## Task 6: Создать CONTRIBUTING.md

**Files:**
- Create: `CONTRIBUTING.md`

**Step 1: Создать CONTRIBUTING.md**

```markdown
# Contributing to Contextual RAG

## Development Setup (Windows + WSL2)

### Prerequisites

- Windows 10/11 with WSL2
- Docker Desktop with WSL2 integration
- Python 3.12+
- Git

### First-time Setup

```bash
# 1. Clone repository
git clone https://github.com/yastman/rag.git contextual_rag
cd contextual_rag

# 2. Create virtual environment
python3.12 -m venv venv
source venv/bin/activate

# 3. Install dependencies
pip install -e ".[dev]"

# 4. Copy environment template
cp .env.local.example .env
# Edit .env and add your API keys

# 5. Start local services
docker compose -f docker-compose.local.yml up -d

# 6. Install pre-commit hooks
pre-commit install

# 7. Verify setup
make test
```

### Daily Workflow

```bash
# Start services
docker compose -f docker-compose.local.yml up -d
source venv/bin/activate

# Development
code .                    # Open VS Code
make lint                 # Check code style
make test                 # Run tests

# Before commit
make all-checks           # Run all checks

# Commit
git add .
git commit -m "type: description"
git push origin main
```

### Commit Message Format

```
type: short description

- Detail 1
- Detail 2

🤖 Generated with Claude Code
Co-Authored-By: Claude <noreply@anthropic.com>
```

Types: `feat`, `fix`, `docs`, `refactor`, `test`, `chore`, `ci`

### Deploy

```bash
# Quick deploy (code only)
git tag -d deploy-code 2>/dev/null || true
git tag deploy-code
git push origin deploy-code --force

# Release deploy (Docker)
git tag v2.6.0
git push origin v2.6.0
```

### Code Quality

- **Linter:** Ruff (replaces flake8, black, isort)
- **Type checker:** MyPy
- **Tests:** pytest with pytest-asyncio
- **Pre-commit:** Automatic checks before commit

### Project Structure

```
contextual_rag/
├── src/                    # Core RAG pipeline
│   ├── core/              # Pipeline orchestration
│   ├── ingestion/         # Document parsing & chunking
│   ├── retrieval/         # Search engines (RRF, DBSF)
│   ├── cache/             # Redis semantic cache
│   └── evaluation/        # MLflow, RAGAS integration
├── telegram_bot/          # Telegram bot
├── services/              # Docker services
│   └── bge-m3-api/       # BGE-M3 embeddings API
├── tests/                 # Test suite
├── docs/                  # Documentation
└── deploy/                # Server configuration
```

### Useful Commands

| Command | Description |
|---------|-------------|
| `make install-dev` | Install dev dependencies |
| `make lint` | Run Ruff linter |
| `make format` | Format code with Ruff |
| `make test` | Run tests |
| `make test-cov` | Run tests with coverage |
| `make all-checks` | Run all quality checks |
| `make docker-up` | Start local Docker services |
| `make docker-down` | Stop local Docker services |
```

**Step 2: Commit**

```bash
git add CONTRIBUTING.md
git commit -m "docs: add contributing guide for local development workflow"
```

---

## Task 7: Обновить Makefile

**Files:**
- Modify: `Makefile`

**Step 1: Прочитать текущий Makefile**

```bash
cat Makefile
```

**Step 2: Добавить команды для локальной разработки**

Добавить в конец `Makefile`:

```makefile
# =============================================================================
# Local Development (docker-compose.local.yml)
# =============================================================================

.PHONY: local-up local-down local-logs local-ps

local-up:  ## Start local Docker services
	docker compose -f docker-compose.local.yml up -d

local-down:  ## Stop local Docker services
	docker compose -f docker-compose.local.yml down

local-logs:  ## View local Docker logs
	docker compose -f docker-compose.local.yml logs -f

local-ps:  ## Show local Docker status
	docker compose -f docker-compose.local.yml ps

local-build:  ## Rebuild local Docker services
	docker compose -f docker-compose.local.yml build

# =============================================================================
# Deployment
# =============================================================================

.PHONY: deploy-code deploy-release

deploy-code:  ## Quick deploy (git pull only)
	git tag -d deploy-code 2>/dev/null || true
	git tag deploy-code
	git push origin deploy-code --force

deploy-release:  ## Release deploy (requires VERSION, e.g., make deploy-release VERSION=2.6.0)
ifndef VERSION
	$(error VERSION is required. Usage: make deploy-release VERSION=2.6.0)
endif
	git tag v$(VERSION)
	git push origin v$(VERSION)
```

**Step 3: Commit**

```bash
git add Makefile
git commit -m "feat: add local development and deploy commands to Makefile"
```

---

## Task 8: Установить серверную конфигурацию

**Note:** Эта задача выполняется на сервере, не в репозитории.

**Step 1: Установить systemd unit**

```bash
sudo cp /home/admin/contextual_rag/deploy/telegram-bot.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable telegram-bot
```

**Step 2: Установить sudoers правило**

```bash
sudo cp /home/admin/contextual_rag/deploy/sudoers-telegram-bot /etc/sudoers.d/telegram-bot
sudo chmod 440 /etc/sudoers.d/telegram-bot
sudo visudo -c  # Проверить синтаксис
```

Expected: `/etc/sudoers.d/telegram-bot: parsed OK`

**Step 3: Сгенерировать SSH ключ для GitHub Actions**

```bash
ssh-keygen -t ed25519 -C "github-actions-deploy" -f ~/.ssh/github_actions -N ""
cat ~/.ssh/github_actions.pub >> ~/.ssh/authorized_keys
chmod 600 ~/.ssh/authorized_keys
```

**Step 4: Показать приватный ключ для GitHub Secrets**

```bash
cat ~/.ssh/github_actions
```

Скопировать вывод в GitHub Secrets как `SSH_PRIVATE_KEY`.

**Step 5: Запустить сервис**

```bash
sudo systemctl start telegram-bot
sudo systemctl status telegram-bot
```

---

## Task 9: Настроить GitHub Secrets

**Note:** Выполняется в браузере на github.com

**Step 1: Открыть Settings → Secrets → Actions**

URL: `https://github.com/yastman/rag/settings/secrets/actions`

**Step 2: Добавить секреты**

| Name | Value |
|------|-------|
| `SERVER_HOST` | `95.111.252.29` |
| `SERVER_USER` | `admin` |
| `SSH_PRIVATE_KEY` | Содержимое `~/.ssh/github_actions` |

**Step 3: Проверить**

Перейти в Actions → видеть что секреты доступны.

---

## Task 10: Финальный push и тестирование

**Step 1: Push всех изменений**

```bash
git push origin main
```

**Step 2: Проверить CI**

Открыть `https://github.com/yastman/rag/actions` и убедиться что CI прошёл.

**Step 3: Протестировать quick deploy**

```bash
make deploy-code
```

Проверить что GitHub Action запустился и выполнился успешно.

**Step 4: Проверить статус бота на сервере**

```bash
sudo systemctl status telegram-bot
```

---

## Checklist

- [ ] Task 1: BGE-M3 API добавлен в репозиторий
- [ ] Task 2: docker-compose.local.yml создан
- [ ] Task 3: CI pipeline создан
- [ ] Task 4: Deploy pipeline создан
- [ ] Task 5: Серверная конфигурация создана
- [ ] Task 6: CONTRIBUTING.md создан
- [ ] Task 7: Makefile обновлён
- [ ] Task 8: Серверная конфигурация установлена
- [ ] Task 9: GitHub Secrets настроены
- [ ] Task 10: Финальное тестирование пройдено

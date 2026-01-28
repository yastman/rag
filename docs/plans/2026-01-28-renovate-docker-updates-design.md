# Renovate Bot для автообновления Docker-образов

**Дата:** 2026-01-28
**Статус:** Draft
**Автор:** Claude Code

## Проблема

Docker-образы в `docker-compose.dev.yml` устаревают. Сейчас 12+ сервисов:
- Часть с pinned версиями: `qdrant:v1.16`, `litellm:v1.81.3.rc.3`
- Часть с floating tags: `redis-stack:latest`, `langfuse:2`

Ручное отслеживание обновлений занимает время и часто забывается.

## Решение

Внедрить **Renovate Bot** (GitHub App) для автоматического создания PR при выходе новых версий Docker-образов.

## Цели

1. Автоматическое обнаружение новых версий для всех Docker-образов
2. Создание PR с changelog и release notes
3. Auto-merge для patch-версий (безопасные обновления)
4. Ручной review для minor/major версий
5. Dependency Dashboard для обзора всех pending updates

## Scope

**В scope:**
- `docker-compose.dev.yml` — основной dev-стек (12 сервисов)
- `docker-compose.local.yml` — если есть
- `telegram_bot/Dockerfile` — базовый образ Python
- `docker/*/Dockerfile` — кастомные образы (mlflow, bge-m3, bm42)

**Out of scope:**
- Production deployment (отдельный compose файл)
- Python dependencies (pyproject.toml) — можно добавить позже
- Watchtower для live-обновлений

## Архитектура

```
GitHub Repo ←→ Renovate GitHub App ←→ Docker Registries
                    ↓                   (Docker Hub, GHCR)
              renovate.json
                    ↓
              Pull Requests + Dependency Dashboard (Issue)
```

### Как работает проверка версий

1. **Парсинг docker-compose.yml** — Renovate находит все `image:` директивы
2. **Запрос к Docker Registry API** — получает список всех доступных тегов
3. **Семантический анализ** — понимает semver, prefixes (`v1.16`), фильтрует unstable
4. **Сравнение и PR** — создаёт PR при обнаружении новой версии

### Расписание

- Проверка: раз в неделю (понедельник, до 9:00)
- Можно запустить вручную через Dependency Dashboard

## Конфигурация

Файл `renovate.json` в корне репозитория:

```json
{
  "$schema": "https://docs.renovatebot.com/renovate-schema.json",
  "extends": ["config:recommended", "docker:enableMajor"],

  "schedule": ["before 9am on monday"],
  "timezone": "Europe/Kiev",

  "dependencyDashboard": true,
  "platformAutomerge": true,
  "prHourlyLimit": 5,
  "labels": ["dependencies", "docker"],

  "packageRules": [
    {
      "description": "Auto-merge patch updates",
      "matchUpdateTypes": ["patch"],
      "automerge": true
    },
    {
      "description": "Databases - stable, auto-merge minor",
      "matchPackageNames": ["pgvector/pgvector", "redis/redis-stack", "qdrant/qdrant"],
      "matchUpdateTypes": ["minor", "patch"],
      "automerge": true,
      "groupName": "databases"
    },
    {
      "description": "ML Platform - group together",
      "matchPackageNames": ["ghcr.io/berriai/litellm", "langfuse/langfuse"],
      "groupName": "ml-platform"
    },
    {
      "description": "LiteLLM - fast releases, only patch auto-merge",
      "matchPackageNames": ["ghcr.io/berriai/litellm"],
      "matchUpdateTypes": ["patch"],
      "automerge": true,
      "ignoreUnstable": false
    },
    {
      "description": "Skip release candidates by default",
      "matchPackagePatterns": [".*"],
      "allowedVersions": "!/^.*(-rc|-alpha|-beta).*$/"
    },
    {
      "description": "Pin floating tags to digest",
      "matchPackageNames": ["redis/redis-stack"],
      "pinDigests": true
    }
  ]
}
```

## Стратегия обновлений по сервисам

| Категория | Сервисы | Стратегия |
|-----------|---------|-----------|
| **Databases** | postgres, redis, qdrant | Minor/patch auto-merge, Major — review |
| **ML Platform** | litellm, langfuse, mlflow | Patch auto-merge, Minor/Major — review |
| **AI Services** | docling, lightrag | Patch auto-merge, остальное — review |
| **Custom builds** | bge-m3, bm42, user-base, bot | Только base image в Dockerfile |

### Floating tags

Образы с `latest` или major-only тегами (`langfuse:2`) будут:
1. Заменены на pinned digest: `redis/redis-stack:latest@sha256:abc123...`
2. Обновляться при пересборке образа в registry

## Dependency Dashboard

Автоматически создаваемый Issue в репозитории:

```markdown
# Dependency Dashboard

## Pending Approval
- [ ] Update qdrant/qdrant to v1.17 (major)
- [ ] Update langfuse/langfuse to 2.1 (minor)

## Open PRs
- #142 Update databases (postgres, redis)
- #143 Update litellm to v1.82.0

## Awaiting Schedule
- docling-serve-cpu: v2.0.0 available (scheduled for Monday)
```

**Checkbox workflow:** Галочка в Issue → Renovate создаёт PR немедленно.

## Шаги внедрения

### 1. Установить Renovate GitHub App

1. Перейти на https://github.com/apps/renovate
2. Нажать "Install"
3. Выбрать репозиторий `rag-fresh`
4. Подтвердить permissions

### 2. Дождаться onboarding PR

Renovate автоматически создаст PR "Configure Renovate" с базовым `renovate.json`.

### 3. Заменить конфиг

Заменить предложенный конфиг на наш (из секции "Конфигурация" выше).

### 4. Merge onboarding PR

После merge:
- Создаётся Issue "Dependency Dashboard"
- Начинается сканирование репозитория
- По schedule появляются первые PR

### 5. Проверить первые PR

- Убедиться что PR содержат правильные изменения
- Проверить что auto-merge работает для patch
- Настроить исключения если нужно

## Файловая структура

```
rag-fresh/
├── renovate.json              # Основной конфиг Renovate
├── docker-compose.dev.yml     # Сканируется автоматически
├── docker-compose.local.yml   # Сканируется автоматически
├── telegram_bot/
│   └── Dockerfile             # Base image python:3.12-slim
└── docker/
    ├── mlflow/Dockerfile
    └── ...
```

## Тестирование

1. **Dry-run:** Renovate показывает что найдёт в onboarding PR
2. **Первый PR:** Проверить что изменения корректны
3. **Auto-merge:** Убедиться что patch-версии мержатся автоматически
4. **Dashboard:** Проверить что Issue создан и обновляется

## Rollback

При проблемах с обновлением:

1. **Revert PR** — стандартный GitHub revert
2. **Ignore версию** — добавить в `ignoreDeps` или через Dashboard
3. **Отключить Renovate** — удалить `renovate.json` или uninstall App

## Расширения (future)

- Добавить Python dependencies (`pyproject.toml`)
- Добавить GitHub Actions versions
- Настроить Slack/Telegram уведомления
- Добавить автотесты перед auto-merge

## Ссылки

- [Renovate Documentation](https://docs.renovatebot.com/)
- [Renovate GitHub App](https://github.com/apps/renovate)
- [Docker Compose support](https://docs.renovatebot.com/docker/)
- [Package Rules](https://docs.renovatebot.com/configuration-options/#packagerules)

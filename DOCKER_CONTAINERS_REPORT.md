# Отчет: анализ Docker/Compose контейнеров (rag-fresh)

Дата: 2026-01-29
Проект: `rag-fresh`
Рабочая директория: `/mnt/c/Users/user/Documents/Сайты/rag-fresh`

## 1) Снимок окружения

- Docker Engine: `28.5.1` (Docker Desktop `4.50.0`)
- Docker Compose: `v2.40.3-desktop.1`
- Docker Scout CLI: `v1.18.3` (требует `docker login` для анализа уязвимостей/quickview)

## 2) Инвентаризация: что обнаружено в репозитории

Compose-файлы:
- `docker-compose.dev.yml` — полный dev-стек
- `docker-compose.local.yml` — минимальный локальный стек

Dockerfile’ы:
- `Dockerfile` (корень)
- `telegram_bot/Dockerfile`
- `docker/mlflow/Dockerfile`
- `services/bge-m3-api/Dockerfile`
- `services/bm42/Dockerfile`
- `services/user-base/Dockerfile`

Доп. конфиги:
- `docker/litellm/config.yaml`
- `docker/postgres/init/00-init-databases.sql`

## 3) Текущее состояние контейнеров (по факту на машине)

Проект в `docker compose ls`:
- `rag-fresh` — `running(1)` (из всего стека реально запущен только 1 контейнер).

Контейнеры из `docker ps -a`:
- `dev-bot` — `Up (healthy)`
- `dev-docling` — `Exited (137)` и `OOMKilled=true` (падение по памяти)
- `dev-langfuse` — `Exited (1)`
- `dev-redis`, `dev-qdrant`, `dev-postgres`, `dev-bge-m3`, `dev-bm42`, `dev-user-base`, `dev-litellm`, `dev-mlflow`, `dev-lightrag` — `Exited (255)` примерно в один момент времени

Интерпретация:
- `Exit 255` у множества сервисов в одно время обычно похоже на “Docker/WSL/Docker Desktop был остановлен/перезапущен”, а т.к. у большинства сервисов в compose **нет `restart:`**, они не поднялись автоматически.
- При этом `dev-bot` имеет `restart: unless-stopped`, поэтому он вернулся.

## 4) Анализ `docker-compose.dev.yml`

### 4.1 Порты наружу (поверхность атаки + конфликты)

Проброшены в хост почти все ключевые сервисы (Postgres/Redis/Qdrant/ClickHouse/MinIO/Langfuse/MLflow/LiteLLM и AI-сервисы).
Примеры:
- Postgres: `5432:5432`
- Redis: `6379:6379`
- Qdrant: `6333:6333`, `6334:6334`
- LiteLLM: `4000:4000`
- Langfuse: `3001:3000`
- MinIO: `9090:9000`, `9091:9001`

Риск: если хост доступен из сети, сервисы будут слушать не только `localhost` (по умолчанию Docker публикует на `0.0.0.0`), а часть паролей/ключей в compose — dev-значения.

### 4.2 Лимиты ресурсов: применяются не везде

В `docker-compose.dev.yml` лимиты памяти заданы через `deploy.resources.limits.memory` для:
- `bge-m3` (4G)
- `bm42` (1G)
- `user-base` (2G)
- `docling` (4G)
- `litellm` (512M)
- `bot` (512M)

Но **не заданы** для:
- `postgres`, `redis`, `qdrant`
- `langfuse`, `langfuse-worker`
- `clickhouse`, `minio`, `redis-langfuse`
- `mlflow`, `lightrag`

Следствие:
- возможны OOM/высокое давление на память/IO при поднятии полного стека;
- `docling` уже упал по OOM при лимите 4G.

### 4.3 Dev-секреты/дефолты (важно даже в dev)

Примеры значений “по умолчанию” в `docker-compose.dev.yml`:
- Postgres: `POSTGRES_PASSWORD=postgres`
- MinIO: `MINIO_ROOT_PASSWORD=miniosecret`
- ClickHouse: `CLICKHOUSE_PASSWORD=clickhouse`
- Langfuse: `NEXTAUTH_SECRET=dev-secret-change-in-production`, `SALT=dev-salt-change-in-production`
- LiteLLM: `LITELLM_MASTER_KEY` по умолчанию `sk-litellm-master-dev`

Рекомендация: вынести в `.env` и не публиковать порты наружу.

### 4.4 Healthchecks и зависимости (`depends_on`)

Наблюдение: `bot` зависит от `redis/qdrant/bm42/user-base/litellm` по `condition: service_healthy`.
Это хорошо, но повышает требования к корректности healthcheck’ов.

Потенциальная критическая проблема:
- `minio` healthcheck задан как `["CMD", "mc", "ready", "local"]`.
- В образе `minio/minio:latest` утилита `mc` часто отсутствует, из-за чего healthcheck может падать всегда.
- Если MinIO будет `unhealthy`, то Langfuse v3/worker (и далее LiteLLM) не стартуют из-за `depends_on`.

### 4.5 Drift конфигурации (контейнеры ≠ compose-файл)

Факт:
- В “живых” контейнерах на машине `dev-langfuse` был на `langfuse/langfuse:2`.
- В текущем `docker-compose.dev.yml` Langfuse задан как v3: `langfuse/langfuse:3.150.0` + `langfuse-worker` + ClickHouse + MinIO + отдельный Redis.

Это означает:
- контейнеры были созданы/запущены из **старой версии** compose-файла;
- обновление compose без пересоздания контейнеров приводит к труднообъяснимым ошибкам.

## 5) Анализ БД и миграций (Postgres + LiteLLM)

Инициализация БД:
- `docker/postgres/init/00-init-databases.sql` создает базы `langfuse`, `mlflow`, `litellm`.

Симптомы в логах:
- ошибки вида `relation ... does not exist` для LiteLLM (отсутствуют таблицы/вьюхи).

Вероятная причина:
- LiteLLM использует Prisma-схему для DB-части, и без миграций/инициализации схемы БД объектам неоткуда взяться.
- По актуальной документации LiteLLM Proxy рекомендуется включить Prisma migrations через `USE_PRISMA_MIGRATE="True"` (env var), чтобы LiteLLM применял миграции при старте/деплое.

Контекст7/документация LiteLLM (использовано):
- `DATABASE_URL` можно задавать в `general_settings.database_url` или через env `DATABASE_URL`.
- `USE_PRISMA_MIGRATE="True"` — рекомендуемый флаг для миграций в проде/версии прокси.

## 6) Анализ Dockerfile’ов (ключевые замечания)

- `telegram_bot/Dockerfile` (multi-stage):
  - плюс: non-root пользователь `botuser`, venv переносится, нет dev-зависимостей в runtime
  - минус: healthcheck импортом модуля проверяет только импорт, но не внешние зависимости (это ок для “process health”, но не “service readiness”)

- Корневой `Dockerfile`:
  - делает `COPY . .` и ставит `requirements.txt` из корня
  - риск: build context может захватить лишние файлы, если `.dockerignore` неполный

## 7) `.dockerignore` и риск утечки секретов в build context

Факт:
- `.dockerignore` игнорирует только `.env`, но **не игнорирует** `.env.local`, `.env.server`, `.env.*`.
- В репозитории есть отслеживаемый git-файл `.env.server`.

Риск:
- при `docker build` файлы окружения могут попасть в build context и потенциально “запечься” в слоях/кэше (особенно если где-то есть `COPY . .`).

## 8) Ресурсы/диск

`docker system df` показывает:
- Images: ~83.45GB (reclaimable ~53.88GB)
- Build Cache: ~19.4GB

Рекомендация:
- периодически чистить: `docker builder prune` / `docker image prune` / `docker system prune` (аккуратно, если важны локальные образы/кэш).

## 9) Рекомендации (приоритет)

P0 (устойчивость запуска):
1) Устранить drift: пересоздать контейнеры из текущего compose (например, `down` → `up -d --remove-orphans`).
2) Исправить healthcheck для `minio` (иначе Langfuse v3/worker/LiteLLM могут не запускаться по `depends_on`).
3) Добавить `restart: unless-stopped` для базовых сервисов (`postgres`, `redis`, `qdrant`, `mlflow`, `lightrag` и т.д.), иначе после рестарта Docker все останется `Exited`.

P1 (безопасность и гигиена):
4) Закрыть публикацию портов наружу: биндинг на `127.0.0.1:PORT:PORT` как минимум для Postgres/Redis/ClickHouse/MinIO.
5) Убрать dev-секреты из compose в `.env` (или хотя бы не оставлять “опасные дефолты”).
6) Усилить `.dockerignore`: добавить `.env.*`, `*.pem`, `*key*` (по необходимости), и все, что не нужно в build context.

P2 (ресурсы):
7) Выставить лимиты памяти/CPU для тяжелых сервисов (`docling`, `clickhouse`, `langfuse`, `mlflow`) и/или уменьшить параллелизм.
8) Для Docling: либо увеличить лимит RAM, либо вынести модельные кэши на volume и/или перейти на более “легкий” образ/настройки.

---

Если нужно — сделаю отдельный “исправляющий PR-патч” по конкретному целевому режиму:
- **только локально** (все порты на `127.0.0.1`, безопаснее)
- **частично наружу** (экспонируем только UI, остальное локально)

# Отчет: ревью / аудит репозитория `rag-fresh` (восстановлен и дополнен)

**Дата:** 2026-01-29
**Коммит (HEAD):** `686a5d6` (`686a5d6081a698e1360ccca2484eb73dd94fd8ef`)
**Контекст:** Python 3.12.3 (локальный `venv/`), Docker Compose v2, проект “Contextual RAG Pipeline” + Telegram bot, dev/local Docker стеки.

---

## 1) Executive summary

Проект выглядит как зрелая RAG-система с хорошей документацией, большим набором тестов, продуманной архитектурой retrieval (dense+sparse, RRF/DBSF, ColBERT, quantization) и заделом под observability (Langfuse + OTEL через LiteLLM).

При этом обнаружены системные проблемы и риски, которые мешают эксплуатации и развитию:
- выключенный CI;
- неконсистентность окружений/зависимостей (несколько “источников истины”);
- import-time сайд-эффекты и тяжелые импорты;
- несоответствия Docker/compose фактическому использованию RedisVL (нужен Redis Stack);
- не герметичные тесты по observability (OTEL export пытается ходить в локальный Langfuse).
- повышенная “поверхность атаки” dev-стека (много портов наружу) + dev-дефолты паролей/секретов;
- риски запуска стека из-за healthcheck/depends_on (MinIO) и отсутствия restart policy у базовых сервисов;
- риск утечки env-файлов в Docker build context из-за слабого `.dockerignore` (особенно при `COPY . .`).

---

## 2) Сильные стороны (что уже хорошо)

- **Хорошая модульность домена:** `src/` (пайплайн/ингест/ретривал) и `telegram_bot/` (продуктовый интерфейс) разделены.
- **Сильный retrieval-стек:** hybrid search, RRF/DBSF, ColBERT, quantization; в `telegram_bot/services/qdrant.py` используется корректный SDK-паттерн `query_points` + `Prefetch` + `FusionQuery`.
- **Кэширование:** многоуровневая архитектура кэша; есть переход на RedisVL (SemanticCache/EmbeddingsCache/SemanticMessageHistory).
- **Документация:** `docs/PIPELINE_OVERVIEW.md`, `docs/LOCAL-DEVELOPMENT.md`, `DOCKER.md`, планы в `docs/plans/`.
- **Тестовая база:** `tests/` содержит unit/smoke/load и инфраструктурные проверки.
- **LLM gateway:** LiteLLM прокси + конфиг `docker/litellm/config.yaml` с Langfuse OTEL callback — правильное направление для “единых” LLM интеграций.

---

## 3) Критические находки (P0 — исправить немедленно)

### P0.1 Секреты/ключи и `.env` файлы

Файл `.env.server` **находится под контролем git** (tracked), хотя и перечислен в `.gitignore`. Это само по себе является высоким риском (любой будущий “случайный” коммит с реальными ключами попадет в историю).

Также в документации/архивах/планах встречаются примеры ключей/переменных окружения. В аудите не обнаружены очевидные “живые” ключи по шаблонам, но наличие tracked `.env.server` и исторические примечания в документах требуют осторожности.

**Немедленные действия (рекомендуемый порядок):**
1) Удалить `.env.server` из репозитория (и добавить проверку, чтобы он не мог появиться снова).
2) Если в `.env.server` когда-либо были реальные ключи — выполнить очистку истории (git filter-repo/BFG) + ротацию ключей у провайдеров.
3) Добавить secret scanning:
   - pre-commit (gitleaks),
   - GitHub Actions job (gitleaks/trufflehog).

### P0.2 CI выключен

Workflow’ы лежат в `.github/workflows.disabled/`. Это снижает безопасность и качество релизов: нет проверки форматирования/линта/типов, нет “quality gate” на PR.

**Рекомендация:** вернуть хотя бы базовый CI (ruff + format-check). Затем добавить smoke-routing/load (они уже описаны в disabled workflow).

### P0.3 Redis образ не соответствует использованию RedisVL (функциональный риск)

В `docker-compose.dev.yml` и `docker-compose.local.yml` используется `redis:8.4.0`. RedisVL SemanticCache/Vector Search требует модулей RediSearch/Vector (обычно Redis Stack).

Результат: семантический кэш либо не будет работать, либо будет отключаться/падать (в зависимости от конфигурации и обработки ошибок), а поведение станет “неочевидным”.

**Немедленное действие:** перейти на Redis Stack образ в средах, где включен SemanticCache, либо явно выключить SemanticCache.

### P0.4 Docker dev-стек может “не подниматься” из-за healthcheck/depends_on

В dev compose важные части Langfuse зависят от MinIO. Если healthcheck MinIO не проходит (например, из-за отсутствия `mc` в образе), downstream сервисы могут не стартовать из-за `depends_on`.

**Немедленное действие:** починить healthcheck MinIO на корректный для образа (или использовать образ/entrypoint, где есть `mc`), затем пересоздать стек из актуального compose.

---

## 4) Высокий приоритет (P1 — 1–2 недели)

### P1.1 Конфигурация: import-time сайд-эффекты и “ломкие” импорты

Наблюдения:
- В `src/config/settings.py` создается глобальный инстанс (`settings = Settings()`) при импорте, и внутри `Settings()` выполняется валидация ключей (`_validate_api_keys()`).

Риски:
- импорт `src.*` может падать/тормозить в окружениях без ключей;
- ухудшается тестируемость и переиспользование как библиотеки.

**Рекомендации:**
- убрать глобальный `settings = Settings()` или сделать его ленивым (factory/get_settings()).
- разделить “загрузку настроек” и “валидацию ключей” (валидировать только при фактическом использовании провайдера/операции).

### P1.2 Dependency management: рассинхрон `pyproject.toml` vs `requirements.txt`

Сейчас присутствуют:
- `pyproject.toml` (PEP 621);
- `requirements.txt` (частично pinned/частично `>=`, есть дубли);
- отдельные зависимости в `telegram_bot/requirements.txt`;
- зависимости, устанавливаемые прямо в Dockerfile’ах сервисов.

Риски:
- воспроизводимость окружения низкая;
- Docker и локальная установка могут тянуть разные версии;
- сложнее обновлять зависимости безопасно.

**Рекомендации:**
- выбрать один источник истины и иметь lockfile (uv/pip-tools/poetry);
- стандартизировать установку в Docker: либо `pip install .`, либо `pip install -r requirements.lock`.
- зафиксировать, что работа ведется через `venv/` (учитывая PEP 668 в system python).

### P1.3 Несостыковки Docker-документации и compose

Пример: `DOCKER.md`/`docs/LOCAL-DEVELOPMENT.md` описывают Redis Stack как требование для vector search, но compose использует `redis:8.4.0`.

**Рекомендация:** привести документацию и compose в соответствие, иначе команда будет тратить время на “неработающие” окружения.

### P1.4 Тяжелые eager-import’ы в `telegram_bot/services`

`telegram_bot/services/__init__.py` импортирует все сервисы, что нивелирует попытки “ленивого” импорта в `CacheService.initialize()` и может делать импорт пакета тяжелым/долгим.

**Рекомендации:**
- перейти на explicit imports в местах использования;
- или сделать `telegram_bot/services/__init__.py` минимальным (экспортировать только стабильные интерфейсы).

### P1.5 Тесты и observability: не герметичный OTEL export

При запуске unit-тестов фиксируются попытки экспортировать OTEL traces в `localhost:3001` (Langfuse), что приводит к таймаутам/шуму, если Langfuse не запущен.

**Рекомендации:**
- добавить “no-op mode” для tracing в unit-тестах (например, `OTEL_SDK_DISABLED=true` или явная деактивация exporter’ов);
- убедиться, что `tests/conftest.py` полностью отключает внешние отправки, а не только “часть” флагов.

---

## 5) Средний приоритет (P2 — планово)

### P2.1 Логи/ошибки: `print()` в коде

В отдельных местах используются `print()` для предупреждений/ошибок. Рекомендуется перейти на единый логгер (уровни, формат, корреляция с trace-id).

### P2.2 Prompt-injection / контентные атаки

Для RAG систем важно:
- явно разделять “контекст документов” и “инструкции”;
- добавлять правила “не выполнять инструкции из контента”;
- делимитировать источники;
- логировать “почему ответ такой” без утечек PII.

В `src/security/` есть задел под PII redaction — стоит внедрить его в реальные точки логирования/трассинга.

### P2.3 Лицензирование и “чистота” репозитория

- В README есть badge “MIT”, но нужно убедиться, что `LICENSE` реально присутствует и корректен.
- В репозитории есть артефакты (coverage, кеши, документы) — стоит подтвердить, что они нужны и не засоряют историю.

### P2.4 Дублирование компонент (два “мира”)

Есть параллельные реализации pipeline/retrieval в `src/` и в `telegram_bot/`. Это ок, если цель — “library vs product”, но требует явного разделения ответственности, иначе растет стоимость поддержки.

---

## 6) SDK-first рекомендации (в сторону “меньше кастома”)

### 6.1 LLM: уйти от ручного HTTP/SSE в пользу SDK

Сейчас `telegram_bot/services/llm.py` и `telegram_bot/services/query_analyzer.py` реализуют OpenAI-compatible запросы вручную (httpx + SSE parsing).

**Рекомендация:** использовать официальный OpenAI Python SDK, направив его на LiteLLM (`LLM_BASE_URL=http://litellm:4000`, ключ — `LITELLM_MASTER_KEY`). Это уменьшит кастомный код и упростит поддержку стриминга/ошибок/ретраев.

### 6.2 RedisVL: сделать окружение корректным (Redis Stack)

Если semantic cache — часть продукта, то Redis Stack обязателен (иначе RedisVL vector/semantic функции не гарантируются).

### 6.3 Qdrant: закрепить один gateway

Сейчас есть и `telegram_bot/services/qdrant.py` (gateway), и `telegram_bot/services/retriever.py` (отдельный thin-client), плюс еще клиенты в `src/`.

**Рекомендация:** оставить один gateway в продуктовой ветке (telebot) и использовать его везде; `src/` либо отделить как “library/experiments”, либо тоже привести к единообразию.

---

## 7) Дорожная карта (приоритеты)

Ниже — приоритизированный план работ “как серия PR”, с критериями готовности (Definition of Done).

### P0 (сегодня/завтра) — блокеры/риски

**P0.1 Секреты и env-гигиена**
- Действия:
  - удалить tracked `.env.server` из репозитория; при необходимости очистить историю (`git filter-repo`/BFG) и ротировать ключи;
  - усилить `.dockerignore` (добавить `.env.*` как минимум), чтобы env не попадали в build context.
- DoD:
  - `git ls-files | rg '^\\.env\\.server$'` → пусто;
  - в CI/локально есть проверка, которая падает при обнаружении секретов/ключей;
  - `docker build` не видит `.env.*` в контексте (проверяется через временный debug build или списком файлов в контексте).

**P0.2 Включить CI “минимальный gate”**
- Действия:
  - вернуть workflow из `.github/workflows.disabled/` в `.github/workflows/` (минимум: ruff + format-check).
- DoD:
  - на PR запускается workflow и блокирует merge при падении.

**P0.3 Docker dev-стек: чтобы поднимался предсказуемо**
- Действия:
  - исправить MinIO healthcheck на корректный для образа (или сменить образ/entrypoint), иначе Langfuse может не стартовать по `depends_on`;
  - добавить `restart: unless-stopped` для базовых сервисов dev-стека (Postgres/Redis/Qdrant/Langfuse/ClickHouse/MinIO/MLflow/LiteLLM — минимум по необходимости);
  - пересоздать стек (устранить drift), убрать orphan’ы.
- DoD:
  - `docker compose -f docker-compose.dev.yml up -d` поднимает основные сервисы в `healthy` без ручного “пинка”;
  - после рестарта Docker Desktop сервисы возвращаются автоматически.

**P0.4 RedisVL SemanticCache: сделать “по-настоящему”**
- Действия:
  - если SemanticCache используется в продуктовой логике — заменить `redis:8.4.0` на Redis Stack образ в dev/local;
  - иначе — отключить semantic cache явно и задокументировать.
- DoD:
  - `CacheService.initialize()` в dev не падает и реально создаёт индексы/использует vector search (а не просто “молча отключается”);
  - есть smoke проверка наличия нужных модулей Redis (аналог `make test-redis`, но соответствующая текущему образу).

### P1 (1–2 недели) — воспроизводимость/поддерживаемость

**P1.1 Убрать import-time сайд-эффекты**
- Действия:
  - удалить/лениво инициализировать `settings = Settings()` в `src/config/settings.py`;
  - разделить “загрузку настроек” и “валидацию ключей” (валидировать при использовании, не при импорте).
- DoD:
  - импорт `src.*` не требует наличия ключей/сервисов;
  - unit-тесты не ломаются из-за отсутствия env.

**P1.2 Ускорить/упростить импорты `telegram_bot/services`**
- Действия:
  - убрать eager-importы из `telegram_bot/services/__init__.py` (оставить минимум или перейти на explicit imports).
- DoD:
  - `python -c "import telegram_bot.services.cache"` не “висит” и не тянет тяжёлые зависимости без необходимости.

**P1.3 Герметичность тестов по observability**
- Действия:
  - в unit-тестах по умолчанию полностью отключить OTEL/Langfuse экспорт (чтобы не было попыток ходить в `localhost:3001`);
  - оставить opt-in режим для e2e/интеграционных тестов.
- DoD:
  - `pytest tests/unit` не делает внешних сетевых запросов к Langfuse/OTEL endpoint’ам.

**P1.4 Dependency management: один источник истины + lock**
- Действия:
  - выбрать стратегию (uv / pip-tools / poetry) и зафиксировать процесс;
  - привести Docker и локальную установку к одному пути установки зависимостей.
- DoD:
  - воспроизводимое окружение (одинаковые версии в CI/Docker/локально);
  - документированная команда установки (1 путь, не 3 разных).

**P1.5 Сократить поверхность атаки dev-стека**
- Действия:
  - биндинг портов на `127.0.0.1` (или убрать наружные порты для внутренних сервисов);
  - вынести dev-дефолты паролей/секретов в `.env` и убрать “опасные дефолты”.
- DoD:
  - при поднятии dev-стека наружу торчит только то, что реально нужно разработчику (обычно UI).

### P2 (1–2 месяца) — SDK-first и консолидация

**P2.1 LLM слой на SDK (вместо ручного httpx/SSE)**
- Действия:
  - перевести `telegram_bot/services/llm.py` и `telegram_bot/services/query_analyzer.py` на официальный OpenAI SDK, направив его на LiteLLM (OpenAI-compatible).
- DoD:
  - исчезает ручной парсинг SSE и дублирование логики ошибок;
  - покрытие тестами не ухудшается (или улучшается) при меньшем объёме кода.

**P2.2 Один Qdrant gateway**
- Действия:
  - убрать дублирование `RetrieverService` vs `QdrantService`, оставить один “умный” gateway и использовать его везде в продуктовой ветке.
- DoD:
  - одно место, где реализованы фильтры/Prefetch/Fusion/quantization параметры.

**P2.3 Явно разделить “library vs product”**
- Действия:
  - либо отделить `src/` как библиотеку/эксперименты (без зависимости от `telegram_bot/`), либо унифицировать продуктовый путь и удалить/заморозить лишние реализации.
- DoD:
  - отсутствуют дублирующиеся реализации одних и тех же концепций без явной причины.

---

## 8) Быстрые проверки (чеклист)

- `venv/bin/ruff check src telegram_bot`
- `venv/bin/python -m pytest -q tests/unit/test_settings.py`
- `venv/bin/python -m pytest -q tests/unit/services/test_llm.py`
- `docker compose -f docker-compose.dev.yml ps` (healthchecks)

---

## 9) Docker/Compose контейнеры (дополнение: консолидировано из `DOCKER_CONTAINERS_REPORT.md`)

### 9.1 Снимок окружения (на машине аудита)

- Docker Engine: `28.5.1` (Docker Desktop `4.50.0`)
- Docker Compose: `v2.40.3-desktop.1`
- Docker Scout CLI: `v1.18.3` (для анализа уязвимостей/quickview требует `docker login`)

### 9.2 Инвентаризация: что обнаружено в репозитории

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

### 9.3 Текущее состояние контейнеров (по факту на машине аудита)

Наблюдение из контейнерного отчёта:
- проект в `docker compose ls`: `rag-fresh` — `running(1)` (из всего стека реально запущен только 1 контейнер);
- `dev-bot` — `Up (healthy)`;
- `dev-docling` — `Exited (137)` и `OOMKilled=true` (падение по памяти);
- `dev-langfuse` — `Exited (1)`;
- `dev-redis`, `dev-qdrant`, `dev-postgres`, `dev-bge-m3`, `dev-bm42`, `dev-user-base`, `dev-litellm`, `dev-mlflow`, `dev-lightrag` — `Exited (255)` примерно в один момент времени.

Интерпретация:
- массовый `Exit 255` в один момент часто похоже на “Docker/WSL/Docker Desktop был остановлен/перезапущен”;
- у большинства сервисов compose **нет `restart:`**, поэтому они не поднялись автоматически;
- `dev-bot` имеет `restart: unless-stopped`, поэтому он вернулся.

### 9.4 Порты наружу (поверхность атаки + конфликты)

Проброшены в хост почти все ключевые сервисы (Postgres/Redis/Qdrant/ClickHouse/MinIO/Langfuse/MLflow/LiteLLM и AI сервисы).
Риск: Docker публикует на `0.0.0.0` по умолчанию; при доступном из сети хосте это становится реальной поверхностью атаки, а часть паролей/ключей — dev-дефолты.

### 9.5 Лимиты ресурсов: применяются не везде

В `docker-compose.dev.yml` лимиты памяти заданы через `deploy.resources.limits.memory` для `bge-m3`, `bm42`, `user-base`, `docling`, `litellm`, `bot`, но не заданы для Postgres/Redis/Qdrant/Langfuse/ClickHouse/MinIO/MLflow и т.д.

Следствие:
- возможны OOM/высокое давление на память/IO при поднятии полного стека;
- Docling уже упал по OOM при лимите 4G.

### 9.6 Dev-секреты/дефолты (важно даже в dev)

Примеры значений “по умолчанию” в compose:
- Postgres: `POSTGRES_PASSWORD=postgres`
- MinIO: `MINIO_ROOT_PASSWORD=miniosecret`
- ClickHouse: `CLICKHOUSE_PASSWORD=clickhouse`
- Langfuse: `NEXTAUTH_SECRET=dev-secret-change-in-production`, `SALT=dev-salt-change-in-production`
- LiteLLM: `LITELLM_MASTER_KEY` по умолчанию `sk-litellm-master-dev`

Рекомендация: вынести в `.env` и не публиковать порты наружу (или биндинг на `127.0.0.1`) даже для dev.

### 9.7 Healthchecks и зависимости (`depends_on`)

Наблюдение: `bot` зависит от `redis/qdrant/bm42/user-base/litellm` по `condition: service_healthy`. Это хорошо, но повышает требования к корректности healthcheck’ов.

Риск по MinIO:
- healthcheck задан как `["CMD", "mc", "ready", "local"]`;
- в `minio/minio:latest` утилита `mc` может отсутствовать, из-за чего healthcheck может падать всегда;
- если MinIO будет `unhealthy`, Langfuse v3/worker (и далее LiteLLM) могут не стартовать из-за `depends_on`.

### 9.8 Postgres + LiteLLM: миграции схемы

`docker/postgres/init/00-init-databases.sql` создает базы `langfuse`, `mlflow`, `litellm`, но не применяет миграции схемы LiteLLM.

Вероятная причина ошибок вида `relation ... does not exist`: LiteLLM использует Prisma-схему и требует миграций/инициализации. Обычно для этого включают автоприменение миграций флагом/настройкой в LiteLLM proxy.

### 9.9 `.dockerignore` и риск утечки секретов в build context

`.dockerignore` игнорирует `.env`, но не гарантирует игнорирование `.env.local`, `.env.server`, `.env.*`.

Риск: при `docker build` env-файлы могут попасть в build context и “запечься” в слоях/кэше (особенно если где-то есть `COPY . .`).

### 9.10 Рекомендации (приоритет)

P0 (устойчивость запуска):
1) Устранить drift: пересоздать контейнеры из текущего compose (`down` → `up -d --remove-orphans`).
2) Исправить healthcheck для `minio` (иначе Langfuse v3/worker/LiteLLM могут не запускаться по `depends_on`).
3) Добавить `restart: unless-stopped` для базовых сервисов (`postgres`, `redis`, `qdrant`, `mlflow`, `lightrag` и т.д.), иначе после рестарта Docker все останется `Exited`.

P1 (безопасность и гигиена):
4) Закрыть публикацию портов наружу: биндинг на `127.0.0.1:PORT:PORT` как минимум для Postgres/Redis/ClickHouse/MinIO.
5) Убрать dev-секреты из compose в `.env` (или хотя бы не оставлять опасные дефолты).
6) Усилить `.dockerignore`: добавить `.env.*` и другие чувствительные паттерны, которые не должны попадать в build context.

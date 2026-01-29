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

**P0 (сегодня/завтра)**
- Удалить `.env.server` из git (и истории при необходимости), подтвердить отсутствие реальных ключей в истории/артефактах.
- Включить CI (перенести workflow из `.github/workflows.disabled/`).
- Добавить secret scanning (pre-commit + CI).
- Починить Redis образ для RedisVL (Redis Stack) или выключить SemanticCache.

**P1 (1–2 недели)**
- Убрать import-time `settings = Settings()` и валидацию ключей при импорте.
- Привести dependency management к единому источнику истины + lockfile.
- Убрать eager-import `telegram_bot/services/__init__.py`.
- Сделать unit-тесты герметичными к внешним OTEL/Langfuse отправкам.

**P2 (1–2 месяца)**
- Перевести LLM слой на SDK (OpenAI SDK поверх LiteLLM).
- Свести дублирующиеся gateway/clients (Qdrant/Redis/LLM).
- Явно разделить `src/` и `telegram_bot/` как “library vs product” или унифицировать в один продуктовый путь.

---

## 8) Быстрые проверки (чеклист)

- `venv/bin/ruff check src telegram_bot`
- `venv/bin/python -m pytest -q tests/unit/test_settings.py`
- `venv/bin/python -m pytest -q tests/unit/services/test_llm.py`
- `docker compose -f docker-compose.dev.yml ps` (healthchecks)

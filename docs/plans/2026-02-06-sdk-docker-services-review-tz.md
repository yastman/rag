# ТЗ: SDK-First ревью и настройка всех Docker-сервисов RAG

Дата: 2026-02-06
Контур: `vps-*` стек (`docker-compose.vps.yml`)

## 1. Цель
Убрать кастомные костыли в Docker/сервисах, перейти на SDK-first настройки и зафиксировать правильную конфигурацию для стабильного контура:
Google Drive -> Ingestion -> Qdrant -> Telegram Bot.

## 2. Источники (официальные)
- Context7: `/docling-project/docling-serve`
- Context7: `/websites/qdrant_tech`
- Context7: `/berriai/litellm`
- Runtime-факты текущего стека:
  - `docker inspect` по всем `vps-*` контейнерам
  - OpenAPI `vps-docling` (`/openapi.json`)
  - реальная схема коллекции Qdrant `gdrive_documents_bge`

## 3. Инвентаризация контейнеров (текущий VPS стек)
- `vps-postgres` (pgvector/pg17)
- `vps-redis` (redis:8.4.0)
- `vps-qdrant` (qdrant:1.16)
- `vps-docling` (локальный build, docling-serve 1.11.0)
- `vps-bge-m3` (кастомный FastAPI)
- `vps-bm42` (кастомный FastAPI + fastembed)
- `vps-user-base` (кастомный FastAPI)
- `vps-litellm` (litellm proxy)
- `vps-bot` (telegram bot)
- `vps-ingestion` (unified ingestion)

## 4. Найденные костыли / anti-SDK решения

### 4.1 Общесистемные
1. Прод-стек использует bind-mount кода в ingestion (`./src`, `./telegram_bot`) вместо immutable image.
2. Секреты передаются plain env, без Docker secrets/secret manager.
3. В проекте одновременно живут несколько ingestion-путей (`gdrive_flow` legacy и `unified`) + дублирующиеся make targets.
4. Документация и реальный runtime частично расходятся.

### 4.2 По сервисам
1. `qdrant`:
   - текущая коллекция `gdrive_documents_bge` без payload indexes;
   - без quantization и без sparse modifier;
   - коллекция создаётся вне unified pipeline (явной bootstrap-миграции нет).
2. `docling`:
   - в compose заданы `DOCLING_PDF_BACKEND/DOCLING_TABLE_MODE`, но OpenAPI показывает server default `pdf_backend=dlparse_v4` (признак, что env-переопределение может не применяться);
   - клиент `src/ingestion/docling_client.py` не передаёт `convert_table_mode`, `convert_ocr_engine`, `convert_pipeline`, `convert_document_timeout` и др.;
   - режимы Docling фактически не стандартизированы по типам документов.
3. `litellm`:
   - используется RC image (`v1.81.3.rc.3`) вместо стабильного;
   - alias `gpt-4o-mini` мапится на non-OpenAI модель, что создаёт операционную путаницу;
   - отсутствует жёстко зафиксированная production-секция `general_settings` в конфиге.
4. `ingestion`:
   - `file_id` считается от относительного пути (rename/move может менять идентичность);
   - `.gdrive_manifest.json` в unified flow не используется;
   - профиль GDrive sync (rclone) не встроен в VPS-стек.
5. `redis`:
   - нет ACL/пароля для prod-режима;
   - не зафиксирован durability-профиль для критичных ключей.
6. `bot`:
   - healthcheck проверяет только живость процесса, не проверяет зависимые сервисы.

## 5. Docling: режимы и правильные настройки (по API/SDK)

### 5.1 Поддерживаемые ключевые параметры (OpenAPI + Context7)
- `convert_pdf_backend`: `pypdfium2 | dlparse_v1 | dlparse_v2 | dlparse_v4`
- `convert_table_mode`: `fast | accurate`
- `convert_do_ocr`, `convert_force_ocr`
- `convert_ocr_engine`: `auto | easyocr | rapidocr | tesseract | tesserocr | ocrmac`
- `convert_pipeline`: `standard | vlm`
- `convert_do_table_structure`, `convert_table_cell_matching`
- `convert_document_timeout`, `convert_page_range`
- `chunking_max_tokens`, `chunking_tokenizer`, `chunking_merge_peers`

### 5.2 Обязательные профили парсинга (внедрить)
1. `docling_profile=quality`:
   - `pdf_backend=dlparse_v4`
   - `table_mode=accurate`
   - `do_table_structure=true`
   - `do_ocr=false` (если документ born-digital)
2. `docling_profile=scan`:
   - `pdf_backend=dlparse_v4`
   - `do_ocr=true`
   - `ocr_engine=rapidocr` (или `easyocr` по качеству)
   - `force_ocr=true` только для плохого извлечения текста
3. `docling_profile=speed`:
   - `pdf_backend=dlparse_v2`
   - `table_mode=fast`
   - отключить enrichment-флаги
4. `docling_profile=vlm`:
   - `pipeline=vlm`
   - включать только для кейсов, где действительно нужен vision-language анализ.

### 5.3 Что изменить в коде клиента Docling
1. Расширить `DoclingConfig` и `UnifiedConfig` полями `table_mode/ocr_engine/pipeline/document_timeout/...`.
2. Пробрасывать все `convert_*` и `chunking_*` параметры в `_build_chunking_form_data()`.
3. Ввести profile-based конфиг (`DOCLING_PROFILE`) и map профилей -> параметры.
4. Добавить unit/integration тесты на правильную сериализацию form-data.

## 6. SDK-first целевая конфигурация по контейнерам

### `vps-postgres`
1. Вынести backup/restore регламент (cron + retention).
2. Зафиксировать параметры пула подключений для клиентов.

### `vps-redis`
1. Включить auth/ACL.
2. Разделить volatile cache и state-критичные ключи (policy/DB strategy).

### `vps-qdrant`
1. Ввести idempotent bootstrap миграцию коллекции (через `scripts/setup_*` или новый unified setup).
2. Создать payload indexes для `metadata.file_id`, `metadata.source`, `metadata.file_name`, `metadata.mime_type`, `metadata.modified_time`.
3. Включить quantization-профили (`off/scalar/binary`) и зафиксировать стратегию по окружениям.
4. Настроить snapshots + retention.

### `vps-docling`
1. Пин версии `docling-serve` (без `>=`).
2. Убрать «магические» env, которые не подтверждены API-контрактом.
3. Управлять режимами через явные `convert_*`/`chunking_*` параметры запроса.
4. Установить worker/memory настройки согласно целевой нагрузке.

### `vps-bge-m3`, `vps-bm42`, `vps-user-base`
1. Зафиксировать API-контракт (request/response schema, versioned endpoints).
2. Добавить concurrency/timeouts/rate limits на уровне сервиса.
3. Добавить метрики latency/error-rate по endpoint.

### `vps-litellm`
1. Перейти на stable image.
2. В `config.yaml` добавить production `general_settings` (timeouts, pools, logging, retries).
3. Привести имена model alias к фактическим провайдерам.
4. Жёстко валидировать fallback chain и деградацию.

### `vps-bot`
1. Добавить dependency-preflight в healthcheck (`qdrant`, `litellm`, `redis`).
2. Зафиксировать режимы retrieval/rerank через env-профиль.

### `vps-ingestion`
1. Убрать bind-mount кода в prod.
2. Встроить/подключить manifest-based `file_id` для rename/move stability.
3. Внедрить обязательный preflight:
   - коллекция существует и имеет нужную схему;
   - docling endpoint доступен;
   - embedding endpoints доступны.

## 7. Обязательные задачи (P0/P1/P2)

### P0 (блокирующие)
1. Удалить продовые bind-mount кода из `ingestion`.
2. Ввести secret management + ротацию ключей.
3. Внедрить единственный ingestion-path (unified), legacy-путь пометить deprecated.
4. Ввести collection bootstrap для `gdrive_documents_bge`.

### P1 (функциональная стабильность)
1. Полная поддержка Docling режимов в клиенте и unified config.
2. Manifest-based file identity в unified flow.
3. Qdrant payload indexes + quantization профили + snapshot policy.
4. LiteLLM production hardening.

### P2 (качество эксплуатации)
1. Унификация docs/Makefile под один production workflow.
2. Расширенный smoke/e2e набор для всех сервисов.
3. Финальный отчёт с замером latency/recall/cost по профилям.

## 8. Критерии приёмки
1. Все `vps-*` контейнеры стартуют без ручных правок, health `healthy`.
2. Docling профили переключаются через env/конфиг и реально влияют на request-параметры.
3. Rename/move файла в Drive не создаёт дубликаты в Qdrant.
4. Qdrant коллекция соответствует целевой схеме (indexes + vectors + sparse config).
5. Telegram bot отвечает по документам после ingest/update/delete цикла.
6. Все изменения отражены в `CLAUDE.md` и operational docs.

## 9. Формат отчёта по выполнению
Для каждой задачи:
- `Статус`: `open | in_progress | fixed | verified`
- `Файлы`
- `Проверка` (команда + результат)
- `Риск` (если остался)

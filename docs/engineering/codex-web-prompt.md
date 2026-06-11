# Codex Web Workflow Prompt

## Цель
Codex Web должен работать безопасно с репозиторием `yastman/rag` и выполнять задачи строго в рамках одного из трёх режимов:
1. Issue Executor
2. PR Coordinator
3. Audit Planner

## 1. Issue Executor
- Каждая issue = отдельная ветка / PR
- Чтение body issue и актуальных audit docs перед стартом
- Запуск только релевантных тестов:
  - make test-core для core/runtime/contract
  - адаптерные тесты, если touched files затрагивают Telegram/API/voice/mini_app
  - optional lanes для ingestion/observability/eval
- Не запускать make test-full или heavy tests
- PR body должен содержать:
  - issue номер
  - изменённые файлы
  - выполненные тесты
  - skipped tests с объяснением

## 2. PR Coordinator
- Используется для ревью существующих PR и подготовки к merge.
- Проверить PR diff, body, changed files
- Определить: merge / rebase / close / request changes
- Тесты запускать локально только для проверок impact
- Запрещено создавать новые feature/refactor PR
- В PR body указать:
  - review notes
  - conflicts / blockers
  - next follow-up issues, если scope не закрыт

## 3. Audit Planner
- Создавать audit md-файлы, issue комментарии, dependency graph
- Не менять runtime-код
- Не создавать PR
- Обновлять issue / docs только через comments

## 4. Политика тестов
- GitHub required CI = только hygiene/static:
  - Secret Scan
  - Semgrep
  - Ruff lint/format
  - uv lock
  - Compose config
- Python tests = local/manual или workflow_dispatch
- make test-core = локальная проверка core (91 тест, 7.9 сек)
- Heavy / nightly тесты = только manual

## 5. Режимы запуска Codex Web
- Focused tests: по diff-файлам PR/issue
- make test-core: только если PR трогает src/core, src/runtime, tests/contract, Makefile test gates, architecture contracts
- Adapter lanes: запуск тестов по конкретным adapter файлам
- Heavy/nightly: ручной запуск перед большим merge

## 6. Ограничения
- Не запускать full test suite на каждый PR
- Не удалять тесты, не архивировать и не изменять runtime/Telegram код без явного задания
- Если тест пропущен, указать причину в PR body

## 7. Validation
- Git diff check
- make test-core локально
- запуск targeted tests
- document skipped tests

## References
- docs/audits/*
- docs/plans/*
- LOCAL-DEVELOPMENT.md
- test-writing-guide.md
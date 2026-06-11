# Codex Web Workflow Prompt

## Цель
Codex Web должен безопасно работать с репозиторием `yastman/rag` и выполнять задачу строго в одном из трёх режимов:
1. Issue Executor
2. PR Coordinator
3. Audit Planner

## 0. Общие правила
- Всегда работать от `dev`, не от `main`.
- Один issue = одна ветка = один PR.
- Не смешивать unrelated issues в одном PR.
- Перед стартом проверить, что issue открыт и не закрыт как completed / duplicate / not planned.
- Перед стартом проверить, что по issue нет уже открытого PR.
- Не менять `.github/workflows/*`, если issue прямо этого не требует.
- Если workflow-файл всё же нужен, сначала проверить, что токен имеет `workflow` scope.

## 1. Issue Executor
- Прочитать body issue и актуальные audit docs перед изменениями.
- Создать ветку от актуального `dev`.
- Делать только scope issue.
- Запускать только релевантные тесты:
  - `make test-core` для core/runtime/contract changes
  - adapter tests для Telegram/API/voice/mini_app changes
  - optional lanes для ingestion/observability/eval changes
- Не запускать `make test-full` или heavy tests.
- PR body должен содержать:
  - issue номер
  - изменённые файлы
  - выполненные тесты
  - skipped tests с причиной

## 2. PR Coordinator
- Используется только для ревью существующих PR и подготовки к merge.
- Проверить PR diff, body, changed files, base branch и mergeability.
- Определить: merge / rebase / close / request changes.
- Тесты запускать локально только для impact checks.
- Запрещено создавать новые feature/refactor PR.
- В PR body или comment указать:
  - review notes
  - conflicts / blockers
  - next follow-up issues, если scope не закрыт

## 3. Audit Planner
- Создавать audit notes, issue comments и dependency graph.
- Не менять runtime-код.
- Не создавать PR, кроме явно запрошенного docs-only PR.
- Если нужен docs-only PR, он должен менять только docs/test-contract metadata, не runtime.

## 4. Branch / PR validation
После создания PR проверить:
- base branch = `dev`
- PR не draft, если задача готова к review
- commits <= 3
- changed files соответствуют issue scope
- нет сотен unrelated files
- `mergeable = true` или явно описан blocker

Если PR открылся в `main`, имеет огромный diff или тащит чужую историю:
- остановиться
- retarget на `dev`
- если diff не очистился, пересоздать ветку через cherry-pick одного commit на свежий `dev`

## 5. Политика тестов
- GitHub required CI = hygiene/static only:
  - Secret Scan
  - Semgrep
  - Ruff lint/format
  - uv lock
  - Compose config
- Python tests = local/manual или workflow_dispatch.
- `make test-core` = локальная core-проверка без heavy lanes.
- Heavy / nightly tests = только manual.

## 6. Режимы запуска Codex Web
- Focused tests: по diff-файлам PR/issue.
- `make test-core`: только если PR трогает `src/core`, `src/runtime`, `tests/contract`, Makefile test gates или architecture contracts.
- Adapter lanes: запуск тестов по конкретным adapter файлам.
- Heavy/nightly: ручной запуск перед большим merge.

## 7. Ограничения
- Не запускать full test suite на каждый PR.
- Не удалять тесты, не архивировать и не менять runtime/Telegram код без явного задания.
- Не закрывать issue без PR или явного audit-комментария.
- Если тест пропущен, указать причину в PR body.

## 8. Validation
- Git diff check.
- PR size check.
- Duplicate PR check.
- `make test-core` локально, если применимо.
- Targeted tests по changed files.
- Document skipped tests.

## References
- docs/audits/*
- docs/plans/*
- LOCAL-DEVELOPMENT.md
- test-writing-guide.md

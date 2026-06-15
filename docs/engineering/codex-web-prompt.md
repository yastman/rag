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

## 0.1 Worker Pack / Batch Mode

A worker may receive a pack of 2-5 related issues for context locality and reduced ramp-up time.

Important:
- A worker pack is a queue, not a PR scope.
- Default rule remains: one issue = one branch = one PR.
- Process issues in the pack sequentially unless explicitly instructed otherwise.
- Do not combine multiple issues into one PR unless:
  1. the user explicitly requests one PR,
  2. all issues are part of the same atomic change,
  3. there is no existing open PR for any included issue,
  4. the PR body explains why the issues are inseparable.
- If issue B depends on issue A, create a stacked PR:
  issue A -> branch A -> PR A
  issue B -> branch B based on branch A -> PR B
- If an open PR already exists for an issue, do not create a duplicate PR.
  Switch to PR Coordinator mode for that issue and report the existing PR.

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

### Preflight checklist (before coding each issue in a worker pack)

Before coding each issue in a worker pack:
- Search open PRs for `Fixes #ISSUE`, `Closes #ISSUE`, issue number, and title keywords.
- If an open PR exists, stop this issue and report:
  - existing PR number
  - overlap
  - whether to review, rebase, or close duplicate work
- Confirm the target branch:
  - normal PR base = dev
  - stacked PR base = previous open PR branch, with reason in PR body

## Required Validation Matrix

| Changed area | Required local validation before ready PR |
|---|---|
| Any Python code | `make pre-push` or `uv run ruff check <changed files>` + format check |
| `src/core/**` | `make test-core` |
| `src/runtime/**` | `make test-core` + targeted runtime tests |
| `tests/contract/**` or architecture rules | `make test-contract` |
| `telegram_bot/**` | nearest override applies: `make check` and `PYTEST_ADDOPTS='-n auto --dist=worksteal' make test-unit`, or document why skipped |
| observability/logging | targeted product event / observability tests |
| docs only | markdown/link checks if available; otherwise state docs-only validation |

A PR must not be marked ready if static CI-equivalent checks fail locally.
If checks cannot be run, keep the PR draft or document skipped checks and risk.

## CI-equivalent static checks

For static CI checks, workers must run the exact commands from `.github/workflows/ci.yml`, not approximate per-file variants.

If a PR changes any file under `src/`, `telegram_bot/`, `mini_app/`, `services/`, or `scripts/`, run before Ready PR:

```bash
uvx ruff check src/ telegram_bot/ mini_app/ services/ scripts/ --output-format=github
uvx ruff format --target-version py312 --check src/ telegram_bot/ mini_app/ services/ scripts/
uv lock --locked
```

## Test Failure Triage / Autofix Policy

When validation fails, classify before fixing:

| Failure type | Action |
|---|---|
| PR-caused failure in changed files or changed behavior | Fix in the current PR |
| Static CI-equivalent failure: Ruff, format, lockfile, Semgrep, Compose | Fix in the current PR before marking ready |
| Existing baseline failure outside PR scope | Do not fix in this PR; document as known baseline and create/follow a separate issue |
| Missing optional dependency in broad suite | Do not vendor/install blindly; classify as optional lane/dependency hygiene and create/follow a separate issue |
| Legacy typing failure outside touched files | Do not fix in this PR; document and create/follow TYPE-BASELINE issue |
| Unclear ownership | Stop, report blocker, include failing command and first relevant error |

Never expand a PR just to make a broad suite green unless the user explicitly asks for a baseline cleanup PR.

## Test Coverage Preservation Guard

Before deleting, moving, skipping, xfail-ing, retargeting, or weakening any
test, the worker prompt owner must require a coverage-preservation map in the PR
body. The map must prove whether the old assertion / behavior / contract still
exists on current `dev`, which current adjacent surfaces were checked, and
which replacement or preserved coverage keeps the behavior tested.

Loop-break ownership:
- worker prompt: require the coverage-preservation map before test deletion or
  weakening work starts;
- TDD/focused tests: prove replacement coverage with a focused validation
  command, or keep the PR blocked;
- PR body: record the map fields and any intentionally deferred coverage;
- reviewer: reject missing or vague maps before approving;
- no-code closeout: may close only when the map proves no code/test change is
  needed;
- orchestrator close decision: may close the issue only after merge or accepted
  no-code evidence references the map.

Required map fields:
- deleted test path;
- old assertion / behavior / contract;
- whether behavior still exists on current `dev`;
- current adjacent surfaces checked;
- replacement or preserved coverage;
- focused validation command;
- follow-up issue if coverage is intentionally deferred.

## Pre-PR Validation Loop

Before opening or marking a PR ready:

1. Run the required local validation matrix for touched files.
2. Wait for every command to finish.
3. If a required local check fails, classify it using Test Failure Triage / Autofix Policy.
4. Fix PR-caused and static CI-equivalent failures in the current branch.
5. Re-run the failed command after each fix.
6. Do not open/mark a ready PR until required local checks are green.
7. Exception: if CI visibility is needed, open a Draft PR only and mark it ready after checks are green.
8. Baseline/unrelated failures must be documented in PR body and tracked by follow-up issue, not fixed inside the feature PR.

## Post-PR-Created Verification

After creating a PR, the worker must verify with:

```bash
gh pr view <PR> --repo yastman/rag --json url,state,baseRefName,headRefName,headRefOid,mergeable,statusCheckRollup,body,files
```

And report:
- PR URL
- base = dev
- head branch / head SHA
- mergeable is not false
- statusCheckRollup is not empty or CI is explicitly pending
- PR body matches template
- no unrelated workflow/process files changed

If workflow runs are empty after PR creation, do not report PR as ready.
Report blocker: "CI did not start".

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
  - `ci.yml`: Secret Scan, Semgrep, Ruff lint/format, uv lock, Compose config
  - `codeql.yml`: security analysis
- Manual-only workflows (must not block PRs):
  - `core-tests.yml`
  - `trusted-heavy.yml`
  - `nightly-heavy.yml`
- Python tests = local/manual или workflow_dispatch.
- `make test-core` = локальная core-проверка без heavy lanes.
- Heavy / nightly tests = только manual.
- Workers must not wait for manual workflows unless explicitly asked.
- Workers must still document local tests / skipped tests in PR body.

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

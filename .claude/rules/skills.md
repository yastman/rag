---
paths: "docs/plans/**/*.md"
---

***REMOVED*** Skills Workflow (Best Practices 2026)

***REMOVED******REMOVED*** Выбор workflow по типу задачи

```
┌─────────────────────────────────────────────────────────────────┐
│                    КАКАЯ У ТЕБЯ ЗАДАЧА?                         │
└─────────────────────────────────────────────────────────────────┘
                              │
        ┌─────────────────────┼─────────────────────┐
        ▼                     ▼                     ▼
   МЕЛКАЯ                 СРЕДНЯЯ               БОЛЬШАЯ
   (< 30 мин)            (1-4 часа)            (дни/недели)
        │                     │                     │
        ▼                     ▼                     ▼
   Быстрый fix         Feature/Bugfix          План/ТЗ
```

---

***REMOVED******REMOVED*** 1. МЕЛКАЯ ЗАДАЧА (< 30 минут)

**Примеры:** фикс опечатки, добавить поле, мелкий баг, конфиг

***REMOVED******REMOVED******REMOVED*** Workflow

```
Задача → /test-driven-development → /verification-before-completion → commit
```

***REMOVED******REMOVED******REMOVED*** Скиллы

| Шаг | Скилл | Действие |
|-----|-------|----------|
| 1 | `/test-driven-development` | RED → GREEN → REFACTOR |
| 2 | `/verification-before-completion` | `make test && make check` |
| 3 | `/git-workflow-manager` | `fix(scope): description` |

***REMOVED******REMOVED******REMOVED*** Если баг

```
Баг → /systematic-debugging → найти root cause → /test-driven-development → fix
```

**Правило:** НЕТ фикса без понимания причины.

---

***REMOVED******REMOVED*** 2. СРЕДНЯЯ ЗАДАЧА (1-4 часа)

**Примеры:** новый endpoint, рефакторинг модуля, интеграция сервиса

***REMOVED******REMOVED******REMOVED*** Workflow

```
Задача → /brainstorming (опционально) → /using-git-worktrees → code → /requesting-code-review → /finishing-a-development-branch
```

***REMOVED******REMOVED******REMOVED*** Скиллы

| Шаг | Скилл | Действие |
|-----|-------|----------|
| 1 | `/brainstorming` | (опционально) Уточнить требования |
| 2 | `/using-git-worktrees` | Изолированная ветка |
| 3 | `/test-driven-development` | Писать код с TDD |
| 4 | `/systematic-debugging` | Если что-то сломалось |
| 5 | `/requesting-code-review` | Review перед merge |
| 6 | `/verification-before-completion` | Финальная проверка |
| 7 | `/finishing-a-development-branch` | Merge / PR |

***REMOVED******REMOVED******REMOVED*** Пример

```bash
/using-git-worktrees      ***REMOVED*** → .worktrees/feature-voice-messages
***REMOVED*** ... пишешь код с TDD ...
/requesting-code-review   ***REMOVED*** → subagent проверяет
/verification-before-completion  ***REMOVED*** make test
/finishing-a-development-branch  ***REMOVED*** → merge to main
```

---

***REMOVED******REMOVED*** 3. БОЛЬШАЯ ЗАДАЧА (дни/недели)

**Примеры:** новый milestone, большой рефакторинг, новая подсистема

***REMOVED******REMOVED******REMOVED*** Workflow

```
ТЗ → выбрать milestone → /writing-plans → /executing-plans или /subagent-driven-development → /finishing-a-development-branch
```

***REMOVED******REMOVED******REMOVED*** Полный pipeline

```
┌─────────────────────────────────────────────────────────────────┐
│  ЭТАП 1: ПОДГОТОВКА                                             │
├─────────────────────────────────────────────────────────────────┤
│  /gh-issues              → Создать issue для milestone          │
│  /using-git-worktrees    → Изолированная ветка                  │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│  ЭТАП 2: ПЛАНИРОВАНИЕ                                           │
├─────────────────────────────────────────────────────────────────┤
│  /writing-plans          → Детальный план                       │
│                            (файлы, код, команды, 2-5 мин/шаг)   │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│  ЭТАП 3: ВЫПОЛНЕНИЕ (выбери один)                               │
├─────────────────────────────────────────────────────────────────┤
│  ВАРИАНТ A: /executing-plans                                    │
│  └── Батчи по 3 задачи → отчёт → твой feedback                  │
│  └── Для: максимальный контроль                                 │
│                                                                 │
│  ВАРИАНТ B: /subagent-driven-development                        │
│  └── Субагент на task → spec review → quality review            │
│  └── Для: автоматическое качество                               │
│                                                                 │
│  ВАРИАНТ C: /dispatching-parallel-agents                        │
│  └── Параллельные агенты на независимые задачи                  │
│  └── Для: скорость                                              │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│  ЭТАП 4: КАЧЕСТВО (встроено)                                    │
├─────────────────────────────────────────────────────────────────┤
│  /test-driven-development   → TDD для каждой фичи               │
│  /systematic-debugging      → Методичный дебаг                  │
│  /requesting-code-review    → Review после tasks/батчей         │
│  /receiving-code-review     → Правильно принять feedback        │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│  ЭТАП 5: ЗАВЕРШЕНИЕ                                             │
├─────────────────────────────────────────────────────────────────┤
│  /verification-before-completion → make test && make check      │
│  /finishing-a-development-branch → Merge / PR / Cleanup         │
│  /gh-issues                      → Закрыть issue                │
│  /git-workflow-manager           → Правильный commit/release    │
└─────────────────────────────────────────────────────────────────┘
```

---

***REMOVED******REMOVED*** 4. НОВАЯ ИДЕЯ / ДИЗАЙН

**Примеры:** "хочу добавить фичу X", "как лучше сделать Y"

***REMOVED******REMOVED******REMOVED*** Workflow

```
Идея → /brainstorming → дизайн-документ → /writing-plans → выполнение
```

***REMOVED******REMOVED******REMOVED*** Скиллы

| Шаг | Скилл | Результат |
|-----|-------|-----------|
| 1 | `/brainstorming` | `docs/plans/YYYY-MM-DD-feature-design.md` |
| 2 | `/writing-plans` | `docs/plans/YYYY-MM-DD-feature-plan.md` |
| 3 | Выполнение | См. "Большая задача" |

---

***REMOVED******REMOVED*** 5. ДЕБАГГИНГ

**Примеры:** тесты падают, баг в проде, неожиданное поведение

***REMOVED******REMOVED******REMOVED*** Workflow

```
Баг → /systematic-debugging → root cause → /test-driven-development → fix → /verification-before-completion
```

***REMOVED******REMOVED******REMOVED*** Железные правила

1. **НЕТ фикса без root cause** — сначала понять, потом чинить
2. **НЕТ фикса без теста** — сначала воспроизвести в тесте
3. **3+ неудачных фикса = архитектурная проблема** — остановись, переосмысли

***REMOVED******REMOVED******REMOVED*** Скиллы

| Шаг | Скилл | Действие |
|-----|-------|----------|
| 1 | `/systematic-debugging` | 4 фазы: investigate → analyze → hypothesis → fix |
| 2 | `/test-driven-development` | Написать падающий тест |
| 3 | Минимальный fix | Одно изменение |
| 4 | `/verification-before-completion` | Проверить всё |

---

***REMOVED******REMOVED*** 6. ПАУЗА / HANDOFF

**Примеры:** нужно прерваться, передать задачу, продолжить завтра

***REMOVED******REMOVED******REMOVED*** Workflow

```
Пауза → /gh-issues (save context) → ... → /gh-issues (load context) → продолжить
```

***REMOVED******REMOVED******REMOVED*** AI Context Template

```markdown
<!-- AI-CONTEXT:START -->
***REMOVED******REMOVED*** Context | IN_PROGRESS
**Files:** `src/service.py:45`, `tests/test_service.py:120`
**Done:** task1, task2
**Next:** task3
**Resume:** One-line summary for cold start
<!-- AI-CONTEXT:END -->
```

***REMOVED******REMOVED******REMOVED*** Команды

```bash
***REMOVED*** Сохранить контекст
gh issue comment 45 --body-file .ai-context.md

***REMOVED*** Загрузить контекст
gh issue view 45 --json comments --jq '.comments[] | select(.body | contains("AI-CONTEXT"))'
```

---

***REMOVED******REMOVED*** Сравнение вариантов выполнения

| Вариант | Скилл | Контроль | Качество | Скорость |
|---------|-------|----------|----------|----------|
| **A** | `/executing-plans` | Высокий (feedback каждые 3 задачи) | Среднее | Средняя |
| **B** | `/subagent-driven-development` | Средний (авто-review) | Высокое (2 review) | Средняя |
| **C** | `/dispatching-parallel-agents` | Низкий | Среднее | Высокая |

***REMOVED******REMOVED******REMOVED*** Когда какой

- **A** — критичные задачи, хочешь контролировать
- **B** — доверяешь автоматике, нужно качество
- **C** — много независимых задач, нужна скорость

---

***REMOVED******REMOVED*** Железные правила (2026)

| Скилл | Правило |
|-------|---------|
| `/test-driven-development` | **НЕТ кода без падающего теста сначала** |
| `/systematic-debugging` | **НЕТ фикса без root cause** |
| `/verification-before-completion` | **НЕТ "готово" без `make test`** |
| `/receiving-code-review` | **НЕТ "You're right!" — только техника** |
| `/writing-plans` | **Каждый шаг = 2-5 минут, точные файлы** |

---

***REMOVED******REMOVED*** Quick Reference

***REMOVED******REMOVED******REMOVED*** Мелкая задача
```
/test-driven-development → /verification-before-completion → commit
```

***REMOVED******REMOVED******REMOVED*** Средняя задача
```
/using-git-worktrees → code (TDD) → /requesting-code-review → /finishing-a-development-branch
```

***REMOVED******REMOVED******REMOVED*** Большая задача
```
/gh-issues → /using-git-worktrees → /writing-plans → /executing-plans → /finishing-a-development-branch
```

***REMOVED******REMOVED******REMOVED*** Новая идея
```
/brainstorming → /writing-plans → выполнение
```

***REMOVED******REMOVED******REMOVED*** Баг
```
/systematic-debugging → /test-driven-development → /verification-before-completion
```

***REMOVED******REMOVED******REMOVED*** Пауза
```
/gh-issues (save AI-CONTEXT)
```

---

***REMOVED******REMOVED*** Вспомогательные скиллы

| Скилл | Назначение |
|-------|------------|
| `/gh-issues` | Task management, AI context handoff |
| `/git-workflow-manager` | Conventional commits, releases, changelog |
| `/cc-analytics` | Статистика использования Claude Code |
| `/claude-md-writer` | Рефакторинг CLAUDE.md |

---
paths: "docs/plans/**/*.md"
---

# Skills Workflow (2026)

## Выбор workflow

| Размер | Примеры | Workflow | Overhead |
|--------|---------|---------|----------|
| **Мелкая** (< 30 мин) | fix, config, поле | Inline: TDD -> verify -> commit | ~0 |
| **Средняя** (1-4 часа) | endpoint, рефакторинг | Branch -> TDD -> review -> merge to main | ~0 |
| **Большая** (дни) | milestone, подсистема | Plan inline -> /tmux-swarm-orchestration (Sonnet) -> merge | ~10-20K |
| **Баг** | тесты падают, прод | /systematic-debugging -> TDD -> fix | ~0 |
| **Autonomous** | complex pipeline | agent-mux Codex (30-60 min artifact) | varies |

---

## 1. МЕЛКАЯ ЗАДАЧА (< 30 минут)

```
Задача -> /test-driven-development -> /verification-before-completion -> commit
```

| Шаг | Скилл | Действие |
|-----|-------|----------|
| 1 | /test-driven-development | RED -> GREEN -> REFACTOR |
| 2 | /verification-before-completion | make check && make test-unit |
| 3 | /git-workflow-manager | fix(scope): description |

Если баг: /systematic-debugging -> root cause -> TDD -> fix

---

## 2. СРЕДНЯЯ ЗАДАЧА (1-4 часа)

```
Branch -> code (TDD) -> /requesting-code-review -> merge to main
```

| Шаг | Скилл | Действие |
|-----|-------|----------|
| 1 | git checkout -b feat/... | Изолированная ветка |
| 2 | /test-driven-development | Код с TDD |
| 3 | /requesting-code-review | Review inline (НЕ PR) |
| 4 | /verification-before-completion | make check && make test-unit |
| 5 | git checkout main && git merge feat/... | Прямой merge |

---

## 3. БОЛЬШАЯ ЗАДАЧА (дни/недели)

```
Plan inline -> /tmux-swarm-orchestration (Sonnet workers) -> merge -> verify
```

### Pipeline

1. ПЛАНИРОВАНИЕ: Координатор пишет план inline (~5-10K tokens)
2. ВЫПОЛНЕНИЕ: /tmux-swarm-orchestration (2-4 Sonnet workers, worktrees, webhooks)
3. КАЧЕСТВО: Worker skills (/executing-plans, /requesting-code-review, /verification-before-completion)
4. ЗАВЕРШЕНИЕ: Merge worker branches + make check + make test-unit + merge to main

### Dispatch

| Задача | Dispatch | Модель |
|--------|----------|--------|
| Реализация | tmux-swarm | Sonnet |
| Дебаг root cause | inline | Opus (coordinator) |
| Research | tmux-swarm | Haiku |
| Autonomous pipeline | agent-mux | Codex high |
| Deep audit | agent-mux | Codex xhigh |

### agent-mux trigger criteria (5% задач)

- Sonnet worker дважды не справился
- Нужна ортогональная проверка (другая модель линейка)
- Security/perf audit
- Autonomous 30-60 min pipeline

---

## 4. ДЕБАГГИНГ

```
/systematic-debugging -> root cause -> /test-driven-development -> fix -> /verification-before-completion
```

Железные правила:
1. НЕТ фикса без root cause
2. НЕТ фикса без теста
3. 3+ неудачных фикса = архитектурная проблема

---

## 5. ПАУЗА / HANDOFF

Между сессиями: обновить .planning/STATE.md (что сделано, что дальше).
Следующая сессия: Read STATE.md -> продолжить.

---

## Tracking

- **TODO.md** -- что делать (update после каждого коммита)
- **.planning/STATE.md** -- текущее состояние, pause/resume
- **По умолчанию нет GitHub Issues/PR ceremony.** Solo dev, прямой merge to main.
- **Исключение:** если branch protection требует PR, делаем минимальный PR с теми же gates.

---

## Worker Skills (инжектятся в промт tmux worker)

| Порядок | Скилл | Когда |
|---------|-------|-------|
| 1 | /executing-plans | Перед началом работы |
| 2 | /requesting-code-review | Перед КАЖДЫМ git commit (HARD GATE) |
| 3 | /verification-before-completion | Перед финальным коммитом |

Воркер вызывает skills через Skill tool САМ (не субагент).

---

## Железные правила

| Правило | Контекст |
|---------|----------|
| НЕТ кода без падающего теста | /test-driven-development |
| НЕТ фикса без root cause | /systematic-debugging |
| НЕТ "готово" без make test | /verification-before-completion |
| НЕТ Opus workers для рутины | Sonnet = 99% quality, 5x cheaper |
| НЕТ inline tmux промтов | Всегда .claude/prompts/worker-*.md |
| НЕТ merge без gates | make check + PYTEST -n auto |
| НЕТ лишней GitHub ceremony | Solo dev, TODO.md + direct merge (PR only if branch protection requires) |

---

## Quick Reference

### Мелкая задача
```
/test-driven-development -> /verification-before-completion -> commit
```

### Средняя задача
```
branch -> TDD -> /requesting-code-review -> merge to main
```

### Большая задача
```
plan inline -> /tmux-swarm-orchestration (Sonnet) -> merge + verify
```

### Баг
```
/systematic-debugging -> /test-driven-development -> /verification-before-completion
```

### Пауза
```
Edit .planning/STATE.md (done / next / resume context)
```

---

## Вспомогательные скиллы

| Скилл | Назначение |
|-------|------------|
| /git-workflow-manager | Conventional commits, release notes |
| /cc-analytics | Статистика Claude Code (weekly report) |
| /claude-md-writer | Рефакторинг CLAUDE.md и rules/ |
| /tmux-swarm-orchestration | Parallel Sonnet workers в tmux |
| /agent-teams | 2+ агентов с общим task list |
| /gh-issues | GitHub Issues: создание, поиск, контекст |
| /dependency-updates | Аудит зависимостей, Renovate PRs |
| /test-suite-optimizer | Flaky tests, xdist, sharding |

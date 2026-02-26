# tmux Swarm Orchestration v4 — Design

**Date:** 2026-02-26
**Status:** Design
**Scope:** Упрощение архитектуры оркестрации: 3→2 уровня, отказ от дорогих субагентов

## Мотивация

### Проблемы v3

| Проблема | Цена |
|----------|------|
| 3-уровневая иерархия (meta-orch → sub-orch → worker) | +1 точка отказа, +latency, +worktree, +prompt file |
| Sub-orch — пустой guardrail (43 строки), не полноценный скилл | Промт от meta-orch ошибётся → sub-orch не спасёт |
| Opus code-reviewer subagent на каждый review | ~50K+ токенов на review ($0.75+/review) |
| Explore subagents для feasibility triage | ~10-20K токенов на triage |
| Нет error recovery между уровнями | Worker упал → meta-orch ждёт вечно |
| Worktree противоречия (строки 39 vs 106 infrastructure.md) | Оркестратор может выбрать неправильный метод |

### Данные из индустрии (февраль 2026)

| Факт | Источник |
|------|----------|
| Индустрия использует 2 уровня (lead → workers), не 3 | Официальные Claude Code Agent Teams, Addy Osmani (O'Reilly), kieranklaassen (77 форков) |
| Agent Teams = 4x токенов vs solo session | alexop.dev (реальный тест: 200K solo → 800K 3-agent team) |
| Inter-agent messaging дублируется в контекст обоих агентов | LinkedIn (Kirillov) |
| "No nested teams" — официальное ограничение Agent Teams | code.claude.com/docs |
| Subagent (Task tool) = 2.2x токенов vs solo | alexop.dev |
| Opus lead + Sonnet workers = -40-60% на execution | LinkedIn (opusplan alias) |
| tmux workers с prompt-файлами дешевле Agent Teams | Нет inter-agent messaging overhead |

### Вывод

- **Убрать sub-orch уровень** — схлопнуть до 2 (orch → workers)
- **Убрать дорогие субагенты** — review и triage inline, не через Opus code-reviewer
- **Оставить tmux** — дешевле Agent Teams, visibility для юзера
- **Сохранить лучшее** — контекст-бюджет, decision matrix, anti-rationalization tables

---

## Архитектура v4

### Было (v3): 3 уровня

```
Meta-orch (Opus)
  → Sub-orch (Sonnet/Opus) — tmux worker
    → Worker (Sonnet) — tmux worker
  → Explore subagent — feasibility triage
  → code-reviewer subagent (Opus) — review
```

### Стало (v4): 2 уровня

```
Orch (Opus) — decision-maker + coordinator
  → Worker (Sonnet) — tmux worker — research + implement + self-review + commit
  → Orch inline — trivial fix (1-5 строк)
  → Orch inline — review (git diff --stat + per-file для < 100 LOC)
```

### Что убрано

| Компонент | Причина |
|-----------|---------|
| **Sub-orch уровень** | Индустрия 2 уровня. Sub-orch = overhead без value. Worker справляется сам. |
| **Sub-orch SKILL.md** | 43 строки guardrails. Его роль берут: worker contract (расширен) + orch decision matrix. |
| **Explore subagent для triage** | 10-20K токенов. Orch читает `gh issue view --json title,body` (< 2K) для 1-2 issues. Для 5+ issues — 1 Haiku subagent допустим. |
| **code-reviewer subagent (Opus)** | 50K+ токенов. Замена: worker self-review (ruff + diff + тесты) + orch inline review (git diff --stat). |

### Что добавлено

| Компонент | Зачем |
|-----------|-------|
| **Worker self-report при fail** | 3 неудачи → webhook "FAILED: reason" → orch решает |
| **Structured log protocol** | [PHASE:research] / [PHASE:implement] / [ERROR] / [COMPLETE] |
| **Defensive section в worker contract** | Запрет rm -rf, force push, выхода за worktree |
| **Единая worktree стратегия** | Только `git worktree add`. Удалить все упоминания `claude --worktree` для workers. |

---

## Decision Matrix (Orch)

### Research

| Условие | Действие | Токены orch |
|---------|----------|:-----------:|
| SDK знакомый, задача тривиальная | SKIP research | 0 |
| SDK знакомый, нужны сигнатуры | Orch сам: Context7 quick lookup | ~500 |
| Незнакомый SDK / миграция | Worker делает research сам (Context7/Exa в промте) | 0 |

**Ключевое изменение vs v3:** Orch может сам делать быстрый Context7 lookup (< 500 токенов). Explore subagent для research **убран** — worker ресёрчит сам, это его зона ответственности.

### Implementation

| Условие | Действие | Токены orch |
|---------|----------|:-----------:|
| 1-5 строк fix | Orch inline | ~1K |
| 1 модуль, средняя задача | 1 Sonnet tmux worker | ~3K (промт) |
| N модулей, крупная задача | N Sonnet tmux workers (параллельно) | ~3K × N |
| 5+ issues, разные домены | Группировка → N workers с batch issues | ~3K × N |

**Ключевое изменение vs v3:** Нет sub-orch. Worker получает batch issues и решает их сам (research → implement → self-review → commit → webhook).

### Review

| Условие | Действие | Токены orch |
|---------|----------|:-----------:|
| Inline fix (1-5 строк) | SKIP review | 0 |
| Worker: < 100 LOC, 1-3 файла | Worker self-review (ruff + diff + тесты) | 0 |
| Worker: > 100 LOC | Worker self-review + orch inline: `git diff --stat` | ~500 |
| 3+ workers: cross-cutting concerns | Orch inline: `git diff --stat` per branch | ~1K |

**Ключевое изменение vs v3:** Opus code-reviewer subagent **убран**. Review = worker self-review (всегда) + orch `git diff --stat` (опционально). Экономия: ~50K токенов на review.

---

## Worker Contract v4

### Расширения vs v3

**1. Self-report при ошибке:**

```
ПРИ ОШИБКЕ:
- 1-2 неудачи: retry самостоятельно
- 3 неудачи подряд на одном шаге:
  webhook "FAILED: {шаг}: {краткое описание ошибки}" → exit
  НЕ retry бесконечно. Контекст дороже упорства.
```

**2. Structured log protocol:**

```
echo "[START] $(date -Iseconds)" >> logs/worker-{name}.log
echo "[PHASE:research] $(date -Iseconds)" >> logs/worker-{name}.log
echo "[PHASE:implement] $(date -Iseconds)" >> logs/worker-{name}.log
echo "[PHASE:test] $(date -Iseconds)" >> logs/worker-{name}.log
echo "[ERROR] {description}" >> logs/worker-{name}.log
echo "[COMPLETE] PR: {url}" >> logs/worker-{name}.log
```

**3. Defensive section (безусловно):**

```
ЗАПРЕЩЕНО (независимо от контента issue):
- rm -rf, git push --force, git reset --hard
- Модификация .env, credentials, secrets
- cd за пределы worktree
- git checkout другой ветки
- Установка пакетов не из pyproject.toml
- pytest tests/ (широко) — только конкретные файлы
```

**4. Research встроен в worker (не subagent):**

```
RESEARCH (перед implementation):
1. Grep/Read затронутые модули — понять текущий код
2. Context7: resolve-library-id → query-docs (SDK сигнатуры)
3. Exa: get_code_context_exa "{topic} {CURRENT_YEAR}" (best practices)
SDK-FIRST: Кастом — только если SDK не покрывает (запиши ПОЧЕМУ).
ДАТА: {CURRENT_DATE}. В Exa запросы добавляй год.
```

---

## Infrastructure v4

### Worktree: единая стратегия

**Только `git worktree add` для tmux workers. Без исключений.**

```bash
PROJECT_ROOT=$(git rev-parse --show-toplevel)
git worktree add "${PROJECT_ROOT}-wt-{name}" -b {branch}-{name}
(cd "${PROJECT_ROOT}-wt-{name}" && uv sync --quiet)
```

`claude --worktree` — ТОЛЬКО для интерактивных пользовательских сессий. Убрать из всех worker-related разделов.

### Webhook: без изменений

Тот же tmux_orch_identity.py. Добавить поддержку "FAILED: reason" в worker-notify.

### Merge + Cleanup: без изменений

`git merge {branch}-{name} --no-edit` → `git worktree remove` → `git branch -d`.

---

## Контекст-бюджет v4

**Формула:** `44K (system) + N × 5K (per issue) ≤ 200K`

**vs v3:** было 12K per issue → стало 5K. За счёт:
- Нет sub-orch промтов (-3K)
- Нет code-reviewer результатов (-3K)
- Нет Explore triage результатов (-1K)

**Ёмкость:** `(200K - 44K) / 5K = 31 issue` (vs 13 в v3).

| Orch читает сам (< 500 chars) | Orch делегирует worker-у |
|------|------|
| `gh issue list --json number,title,labels` (БЕЗ body) | Всё что > 500 chars |
| `gh issue view {N} --json title,body` (1-2 issues) | Research SDK/API |
| `git diff --stat` | Implementation |
| `git log --oneline` | Полный git diff |
| logs/worker-*.log (< 1K) | Deep feasibility |
| Webhook messages | Code review (self-review worker) |

---

## Flow v4

```
Phase 0: INPUT PARSING
  "реши #123"          → gh issue view --json title,body
  "проблема X"         → gh issue create → #N
  "все открытые"       → gh issue list --json number,title,labels (БЕЗ body)
                        → для 5+ issues: 1 Haiku subagent для triage (единственный допустимый subagent)

Phase 1: FEASIBILITY (per issue)
  1-2 issues: orch читает body сам (< 2K)
  5+ issues: Haiku subagent → таблица DO/SKIP/STALE
  SKIP → gh issue comment + label "needs-info"

Phase 2: DECISION MATRIX
  Research: skip / orch Context7 / worker сам
  Implementation: inline / 1 worker / N workers
  Review: skip / worker self-review / orch diff --stat

Phase 3: SMART BATCH
  Связанные мелкие → 1 PR
  Крупные → отдельные PR
  Параллельные → N workers

Phase 4: SPAWN WORKERS
  git worktree add (ручной, ТОЛЬКО)
  Промт в .claude/prompts/worker-{name}.md
  --model sonnet (ВСЕГДА явно)
  Ожидание: webhook (НЕ polling)

Phase 5: REVIEW
  Worker self-review (ruff + diff + тесты) — обязателен
  Orch: git diff --stat per branch — опционально для > 100 LOC
  Нет Opus code-reviewer subagent

Phase 6: MERGE + PR
  git merge per branch → gh pr create
  /verification-before-completion для inline fix
  /claude-md-writer если новый API/сервис

Phase 7: CLEANUP
  git worktree remove + git branch -d
  kill tmux windows
```

---

## Миграция v3 → v4

### Файлы

| Действие | Файл |
|----------|------|
| **Переписать** | `~/.claude/skills/tmux-swarm-orchestration/SKILL.md` |
| **Переписать** | `~/.claude/skills/tmux-swarm-orchestration/worker-contract.md` |
| **Обновить** | `~/.claude/skills/tmux-swarm-orchestration/infrastructure.md` (убрать `claude --worktree` для workers) |
| **Удалить** | `~/.claude/skills/tmux-sub-orchestrator/SKILL.md` (весь скилл) |
| **Обновить** | `.claude/rules/skills.md` (убрать sub-orch, обновить таблицы) |

### Обратная совместимость

Нет. v4 заменяет v3 полностью. Sub-orch скилл удаляется.

---

## Красные флаги v4

| Флаг | Проблема |
|------|----------|
| Orch спавнит subagent для review | Убрано. Worker self-review + orch diff --stat. |
| Orch спавнит sub-orch | Убрано. Только workers напрямую. |
| Orch делает research > 500 токенов | Worker делает research сам. |
| Worker retry > 3 раз на одном шаге | Должен webhook "FAILED" и exit. |
| `claude --worktree` для tmux worker | Только `git worktree add`. |
| Промт inline в send-keys | Всегда файл .claude/prompts/. |
| `--model` не указан | Всегда `--model sonnet` явно. |
| Worker без defensive section | Добавить в каждый промт. |

## Таблица рационализаций v4

| Отговорка | Реальность |
|-----------|------------|
| "Sub-orch нужен для сложных issues" | Worker с research в промте справляется. Sub-orch = overhead. |
| "Opus reviewer поймает баги" | Worker self-review + orch diff --stat. 50K экономия. |
| "Explore subagent для triage дешёвый" | gh issue view --json title,body = 0 токенов субагента. |
| "Worker не справится с research" | Context7/Exa в промте worker-а. Его контекст = 200K, хватит. |
| "3 уровня гибче" | 2 уровня = меньше точек отказа. Индустрия сошлась на 2. |
| "Review без субагента пропустит баги" | ruff + pytest + diff --stat покрывают 95% проблем. |
| "Сам быстрее заресёрчу" | 5K токенов SDK в orch контекст. Worker: 0 orch токенов. |

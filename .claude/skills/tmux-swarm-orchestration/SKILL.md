---
name: tmux-swarm-orchestration
description: Use when given GitHub issues to solve, problems to fix, or "review all open issues". Also for running heavy commands on VPS through user's terminal. Triggers on "реши issue", "fix #123", "изучи все открытые", "parallel workers", "swarm", "spawn-claude", "tmux воркеры", "VPS команда"
---

# tmux Swarm Orchestration v5

<HARD-GATE>
ТЫ = OPUS = ОРКЕСТРАТОР. Юзер дал issues — дальше ВСЁ автоматом. Юзер ничего не делает до PR URLs.

Ты — ДИСПЕТЧЕР. НЕ читаешь код, НЕ исследуешь файлы.
Ты ТОЛЬКО: парсишь issues, принимаешь решения, пишешь промты, спавнишь workers, ждёшь.

ПЕРЕД КАЖДЫМ tool call: "Вернёт > 500 chars в МОЙ контекст?" → Да → worker делает.
Исключение: inline fix 1-5 строк, Context7 quick lookup < 500 токенов.
</HARD-GATE>

**Принцип:** Один вызов скилла → полная автоматизация → PR URLs юзеру.

## Краткий справочник

| Вход | Действие |
|------|----------|
| "реши #123" | gh issue view → feasibility → strategy → execute → PR |
| "проблема X" | gh issue create → тот же flow |
| "все открытые" | gh issue list → batch analysis → execute → PRs |
| VPS команда | tmux window → ssh → command → wait |

| Стратегия | Когда |
|-----------|-------|
| Inline fix (сам) | Тривиальная правка 1-5 строк |
| Spawn worker(s) | Любая задача, требующая кода |

## Контекст-бюджет

**Цель: ≤5K токенов на issue. 200K лимит = ~31 issue.**

| Кто | Стоимость | Множитель |
|-----|-----------|-----------|
| Оркестратор (Opus) | $15/$75 за 1M in/out | 1x |
| Sonnet worker | $3/$15 за 1M in/out | 5x дешевле |

**ORCH ЧИТАЕТ САМ** (< 500 chars):
- `gh issue list --json number,title,labels` (БЕЗ body)
- `gh issue view {N} --json title,body` (1-2 issues, допустимо)
- `git diff --stat`
- `git log --oneline`
- logs/worker-*.log (< 1K)
- Context7 quick lookup (< 500 токенов, знакомый SDK)

**ORCH ДЕЛЕГИРУЕТ WORKER-У** (> 500 chars):
- Research SDK/API (worker ресёрчит сам через Context7/Exa)
- Implementation
- Review (worker self-review: ruff + diff + тесты)

**Формула:** `44K (system) + N × 5K (per issue) ≤ 200K` → max 31 issues.

## Flow

Phase 0: INPUT PARSING
  "реши #123"          → gh issue view --json title,body
  "проблема X"         → gh issue create → #N
  "все открытые"       → gh issue list --json number,title,labels (БЕЗ body)
                        → 5+ issues: 1 Haiku subagent для triage

Phase 1: FEASIBILITY (per issue)
  1-2 issues: orch читает body сам
  5+ issues: Haiku subagent → таблица DO/SKIP/STALE
  SKIP → gh issue comment + label "needs-info"

Phase 2: DECISION MATRIX
  Implementation: inline fix (1-5 строк) / 1 worker / N workers
  Review: worker self-review (всегда) + orch diff --stat (> 100 LOC)

Phase 3: SMART BATCH
  Связанные мелкие → 1 PR
  Крупные → отдельные PR
  Параллельные → N workers

Phase 4: SPAWN WORKERS
  git worktree add (ТОЛЬКО ручной)
  Промт в .claude/prompts/worker-{name}.md
  --model sonnet (ВСЕГДА явно)
  Ожидание: tmux wait-for (true push, 0 polling, 0 tokens)

Phase 5: REVIEW
  Worker self-review — обязателен (встроен в contract)
  Orch: git diff --stat per branch — для > 100 LOC

Phase 6: MERGE + PR
  git merge per branch → gh pr create
  /verification-before-completion для inline fix
  /claude-md-writer если новый API/сервис

Phase 7: CLEANUP
  git worktree remove + git branch -d + kill tmux windows

<HARD-GATE>
ПОКА ЖДЁШЬ tmux wait-for — НЕ ЧИТАЙ КОД. НЕ ИССЛЕДУЙ ФАЙЛЫ.
Если нечего делать — жди. 0 токенов пока worker работает.
</HARD-GATE>

## Механика → Read infrastructure.md
## Промт воркера → Read worker-contract.md § Implementation Worker

## Красные флаги — СТОП

**Контекст-бюджет:**
- `Read` файла > 50 строк (worker делает)
- `gh issue list/view` с body для 5+ issues (Haiku triage)
- `git diff` без `--stat`
- Research > 500 токенов (worker ресёрчит сам)
- На 3-й issue контекст > 80K (утечка)

**Стратегия:**
- Спавнит sub-orch (УБРАНО — только workers)
- Спавнит subagent для review (УБРАНО — worker self-review)
- Делает research сам > 500 токенов (worker ресёрчит сам)
- ВСЕГДА воркеры даже для 1-строчного фикса
- Нет --model флага (дефолт = Opus)

**Инфраструктура:**
- Промт inline в send-keys
- Воркеры без worktrees
- `claude --worktree` для tmux workers (ТОЛЬКО `git worktree add`)
- tmux new-session / нет TMUX=""
- send-keys webhook вместо `tmux wait-for`
- Polling log вместо `Bash(run_in_background)` + `tmux wait-for`

**Review/Docs:**
- Пропустил /verification-before-completion при inline fix
- Пропустил /claude-md-writer при новом API
- PR без Closes #N
- Не удалены worktrees после merge

## Таблица рационализаций

| Отговорка | Реальность |
|-----------|------------|
| "Sub-orch нужен для сложных issues" | Worker с research справляется. Sub-orch = overhead. |
| "Opus reviewer поймает баги" | Worker self-review + orch diff --stat. 50K экономия. |
| "Explore subagent дешёвый" | gh issue view = 0 субагентов. Worker ресёрчит сам. |
| "Worker не справится с research" | Context7/Exa в промте. Его контекст = 200K, хватит. |
| "Быстрее сделаю сам" | Inline fix для тривиального. Остальное — worker. |
| "Issue не нужен" | Issue = трекинг + PR reference. Создай. |
| "Промт простой, inline OK" | Escape hell. Файл. |
| "Feasibility — лишний шаг" | 5 секунд = 30 минут экономии. |
| "Worktrees — overkill" | Без worktrees — конфликты веток. |
| "Пока жду — посмотрю код" | 22K chars (ORCH-1e40f272). Жди. |
| "Сам пофикшу failing test" | 38 calls, 43K chars. Fix-worker. |
| "send-keys webhook надёжнее" | Claude Code не читает stdin из tmux. tmux wait-for = true push. |
| "Polling log тоже работает" | Polling = токены. wait-for = 0 токенов, instant push. |

## Чеклист

- [ ] `tmux wait-for` через `Bash(run_in_background)` после каждого spawn
- [ ] Worker сигналит `TMUX="" tmux wait-for -S worker-{name}-done` в конце
- [ ] `--model sonnet` явно
- [ ] `git worktree add` (не `claude --worktree`)
- [ ] /verification-before-completion для inline fix
- [ ] Worker self-review обязателен
- [ ] Промт в файл, не inline

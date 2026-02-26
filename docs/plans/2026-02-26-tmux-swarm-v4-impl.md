# tmux Swarm v4 Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Упростить оркестрацию с 3 до 2 уровней, убрать дорогие субагенты, добавить error recovery и defensive guards.

**Architecture:** 2 уровня (Orch Opus → Sonnet workers). Без sub-orch, без Opus code-reviewer subagent, без Explore subagent (кроме Haiku triage для 5+ issues). tmux runtime сохранён.

**Tech Stack:** Claude Code CLI, tmux, tmux_orch_identity.py, git worktrees

---

## Task 1: Переписать SKILL.md (главный скилл оркестратора)

**Files:**
- Modify: `~/.claude/skills/tmux-swarm-orchestration/SKILL.md` (полная перезапись)

**Step 1: Прочитать текущий SKILL.md**

Run: `cat ~/.claude/skills/tmux-swarm-orchestration/SKILL.md | wc -l`
Expected: 336 строк (v3)

**Step 2: Переписать SKILL.md**

Заменить полное содержимое. Ключевые изменения vs v3:

```markdown
---
name: tmux-swarm-orchestration
description: Use when given GitHub issues to solve, problems to fix, or "review all open issues". Also for running heavy commands on VPS through user's terminal. Triggers on "реши issue", "fix #123", "изучи все открытые", "parallel workers", "swarm", "spawn-claude", "tmux воркеры", "VPS команда"
---

# tmux Swarm Orchestration v4

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
- Webhook messages
- Context7 quick lookup (< 500 токенов, знакомый SDK)

**ORCH ДЕЛЕГИРУЕТ WORKER-У** (> 500 chars):
- Research SDK/API (worker ресёрчит сам через Context7/Exa)
- Implementation
- Review (worker self-review: ruff + diff + тесты)

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
  Ожидание: webhook (НЕ polling)

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
ПОКА ЖДЁШЬ WEBHOOK — НЕ ЧИТАЙ КОД. НЕ ИССЛЕДУЙ ФАЙЛЫ.
Если нечего делать — жди.
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
- НЕ использует хелпер tmux_orch_identity.py
- Промт inline в send-keys
- Воркеры без worktrees
- `claude --worktree` для tmux workers (ТОЛЬКО `git worktree add`)
- tmux new-session / нет TMUX=""

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

## Чеклист

- [ ] ORCH identity через хелпер
- [ ] `--model sonnet` явно
- [ ] `git worktree add` (не `claude --worktree`)
- [ ] /verification-before-completion для inline fix
- [ ] Worker self-review обязателен
- [ ] Промт в файл, не inline
```

**Step 3: Проверить что файл валидный markdown**

Run: `wc -l ~/.claude/skills/tmux-swarm-orchestration/SKILL.md`
Expected: ~180-200 строк (vs 336 в v3 — на 40% компактнее)

**Step 4: Commit**

```bash
git add ~/.claude/skills/tmux-swarm-orchestration/SKILL.md
git commit -m "refactor(skills): tmux-swarm-orchestration v4 — collapse 3→2 levels

Remove sub-orch layer, Opus code-reviewer subagent, and Explore
subagents. Workers now handle research and self-review inline.
Context budget improved from 12K to 5K per issue (31 vs 13 capacity)."
```

---

## Task 2: Переписать worker-contract.md

**Files:**
- Modify: `~/.claude/skills/tmux-swarm-orchestration/worker-contract.md` (полная перезапись)

**Step 1: Прочитать текущий worker-contract.md**

Run: `wc -l ~/.claude/skills/tmux-swarm-orchestration/worker-contract.md`
Expected: 172 строки

**Step 2: Переписать worker-contract.md**

Ключевые изменения vs v3:
- Убрать: Sub-Orchestrator Prompt (§ Phase 3.1) — целиком
- Убрать: Code Review subagent template (§ Phase 6.3) — целиком
- Добавить: Self-report при fail (3 неудачи → webhook FAILED)
- Добавить: Structured log protocol ([PHASE:...] / [ERROR] / [COMPLETE])
- Добавить: Defensive section (запрет rm -rf, force push, cd за worktree)
- Добавить: Research встроен в worker (Context7/Exa, SDK-FIRST)
- Обновить: Implementation Worker — расширить research + self-review + error handling

```markdown
# Worker Templates v4

Reference templates for tmux-swarm-orchestration. Loaded when building prompts.

## Feasibility Triage (Phase 1, только для 5+ issues)

    Task(
        description="Triage: issues #{numbers}",
        prompt="""
        Для каждого issue: gh issue view --json title,body,labels,state
        Изучи кодовую базу (Grep, Read) для проверки актуальности.

        Критерии SKIP:
        - Устарело (уже исправлено в коде)
        - Нечёткое (нет воспроизведения, нет контекста)
        - Высокий риск (breaking change без тестов)
        - Дупликат

        Верни СТРОГО таблицу:
        | Issue | Статус | Сложность | Файлы | Причина |
        Статус: DO / SKIP / STALE
        Сложность: trivial / medium / large
        Файлы: max 3
        Максимум 3 строки на issue.
        """,
        subagent_type="Explore",
        model="haiku"
    )

## Implementation Worker (Phase 4)

    W-{NAME}: {описание}

    РАБОЧАЯ ДИРЕКТОРИЯ: {worktree_absolute_path}
    Ветка: {branch_name} (уже checkout). НЕ ПЕРЕКЛЮЧАЙСЯ.
    НЕ переходи в другие директории (cd). Работай ТОЛЬКО в worktree.

    ISSUE: #{N} — {title}
    {issue_body_or_summary}

    SKILLS (вызови через Skill tool В ЭТОМ ПОРЯДКЕ):
    1. /executing-plans — ПЕРЕД началом работы
    2. /test-driven-development — при написании ЛЮБОГО кода
    3. /verification-before-completion — ПЕРЕД финальным коммитом

    RESEARCH (перед implementation):
    1. Grep/Read затронутые модули — понять текущий код
    2. Context7: resolve-library-id → query-docs (SDK сигнатуры)
    3. Exa: get_code_context_exa "{topic} {CURRENT_YEAR}" (best practices)
    SDK-FIRST: Кастом — только если SDK не покрывает (запиши ПОЧЕМУ).
    ДАТА: {CURRENT_DATE}. В Exa запросы добавляй год.

    ЗАДАЧИ: {Task N: описание}

    SELF-REVIEW (перед коммитом, обязательно):
    1. ruff check --fix {changed_files}
    2. ruff format {changed_files}
    3. uv run pytest {test_files} -v (ТОЛЬКО затронутые, --lf для упавших)
    4. git diff --cached --stat → проверить что коммитишь

    КОММИТ:
    git add {конкретные файлы, НЕ -A}
    git commit -m "{type}({scope}): {description}

    Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"

    ЗАПРЕЩЕНО (безусловно):
    - rm -rf, git push --force, git reset --hard
    - Модификация .env, credentials, secrets
    - cd за пределы worktree
    - git checkout другой ветки
    - Установка пакетов не из pyproject.toml
    - pytest tests/ (широко) — только конкретные файлы
    - Спавн субагентов (Task tool запрещён)
    - Баг не по теме → gh issue create, НЕ фиксить

    ПРИ ОШИБКЕ:
    - 1-2 неудачи: retry самостоятельно
    - 3 неудачи подряд на одном шаге:
      webhook "FAILED: {шаг}: {краткое описание}" → exit
      НЕ retry бесконечно.

    ЛОГ: logs/worker-{name}.log
    echo "[START] $(date -Iseconds)" >> logs/worker-{name}.log
    echo "[PHASE:research] ..." после начала research
    echo "[PHASE:implement] ..." после начала кода
    echo "[PHASE:test] ..." после начала тестов
    echo "[ERROR] {description}" при ошибках
    echo "[COMPLETE] commit: {sha}" после успеха

    WEBHOOK (3 отдельных Bash вызова):
    1: uv run python scripts/tmux_orch_identity.py worker-notify W-{NAME} "COMPLETE"
    2: sleep 1
    3: uv run python scripts/tmux_orch_identity.py worker-enter

    При FAILED:
    1: uv run python scripts/tmux_orch_identity.py worker-notify W-{NAME} "FAILED: {reason}"
    2: sleep 1
    3: uv run python scripts/tmux_orch_identity.py worker-enter
```

**Step 3: Проверить что markdown валидный**

Run: `wc -l ~/.claude/skills/tmux-swarm-orchestration/worker-contract.md`
Expected: ~100-110 строк (vs 172 в v3 — убраны sub-orch и code-review секции)

**Step 4: Commit**

```bash
git add ~/.claude/skills/tmux-swarm-orchestration/worker-contract.md
git commit -m "refactor(skills): worker-contract v4 — add self-report, defensive section, inline research

Remove Sub-Orchestrator Prompt and Code Review subagent templates.
Add: error self-report (3 failures → FAILED webhook), structured logs,
defensive section (no rm -rf/force push), inline research (Context7/Exa)."
```

---

## Task 3: Обновить infrastructure.md

**Files:**
- Modify: `~/.claude/skills/tmux-swarm-orchestration/infrastructure.md:28-67`

**Step 1: Убрать "Автоматический worktree" секцию из Spawn Commands**

Удалить строки 55-59 (Автоматический worktree с `claude --worktree`).
Оставить только "Ручной worktree" (строки 61-66).

**Step 2: Убрать противоречие на строке 106**

Удалить строку 106: "`claude --worktree` НЕ авто-удаляет при headless exit."
(Противоречит строкам 39-40 и вносит путаницу.)

**Step 3: Убрать "Автоматические worktrees" из Merge + Cleanup**

Удалить строки 88-95 (merge для автоматических worktrees).
Оставить только "Ручные worktrees" (строки 97-104).

**Step 4: Добавить FAILED webhook support**

В секцию Webhook добавить:

```
Worker отправляет "FAILED: {reason}" при 3 неудачах подряд.
Orch получает → решает: respawn / skip / manual fix.
```

**Step 5: Commit**

```bash
git add ~/.claude/skills/tmux-swarm-orchestration/infrastructure.md
git commit -m "fix(skills): infrastructure — remove claude --worktree for workers, fix contradiction

Single worktree strategy: git worktree add only for tmux workers.
Remove auto-worktree spawn commands and merge section.
Add FAILED webhook documentation."
```

---

## Task 4: Удалить tmux-sub-orchestrator скилл

**Files:**
- Delete: `~/.claude/skills/tmux-sub-orchestrator/SKILL.md`
- Delete: `~/.claude/skills/tmux-sub-orchestrator/` (вся директория)

**Step 1: Удалить директорию**

```bash
rm -rf ~/.claude/skills/tmux-sub-orchestrator/
```

**Step 2: Проверить что удалено**

Run: `ls ~/.claude/skills/tmux-sub-orchestrator/ 2>&1`
Expected: "No such file or directory"

**Step 3: Commit**

```bash
git add -A ~/.claude/skills/tmux-sub-orchestrator/
git commit -m "refactor(skills): remove tmux-sub-orchestrator — collapsed into 2-level architecture

Sub-orchestrator layer eliminated. Workers now handle research,
implementation, and self-review directly. See v4 design doc."
```

---

## Task 5: Обновить skills.md (rules)

**Files:**
- Modify: `/home/user/projects/rag-fresh/.claude/rules/skills.md`

**Step 1: В таблице "Вспомогательные скиллы" убрать sub-orch**

Нет прямого упоминания sub-orch в skills.md, но проверить и обновить описание /tmux-swarm-orchestration если нужно.

**Step 2: Обновить секцию "3. БОЛЬШАЯ ЗАДАЧА"**

В строке 61 заменить:
```
3. КАЧЕСТВО: Worker skills (/executing-plans, /test-driven-development, /verification-before-completion) + orchestrator /requesting-code-review после merge
```
На:
```
3. КАЧЕСТВО: Worker self-review (ruff + diff + тесты) + orch git diff --stat (> 100 LOC)
```

**Step 3: В строке 122 обновить:**

```
Глубокий code review делает ОРКЕСТРАТОР через /requesting-code-review после merge.
```
На:
```
Orch делает light review через git diff --stat после merge (> 100 LOC).
```

**Step 4: Commit**

```bash
git add /home/user/projects/rag-fresh/.claude/rules/skills.md
git commit -m "docs(rules): update skills.md for v4 orchestration — inline review, no sub-orch"
```

---

## Task 6: Верификация

**Step 1: Проверить что все файлы на месте**

```bash
ls -la ~/.claude/skills/tmux-swarm-orchestration/
# Expected: SKILL.md, worker-contract.md, infrastructure.md (3 файла)

ls ~/.claude/skills/tmux-sub-orchestrator/ 2>&1
# Expected: No such file or directory
```

**Step 2: Проверить что нет broken references**

```bash
grep -r "sub-orch" ~/.claude/skills/tmux-swarm-orchestration/
# Expected: нет результатов (все упоминания убраны)

grep -r "code-reviewer" ~/.claude/skills/tmux-swarm-orchestration/
# Expected: нет результатов

grep -r "tmux-sub-orchestrator" /home/user/projects/rag-fresh/.claude/rules/
# Expected: нет результатов
```

**Step 3: Проверить что CLAUDE.md не нуждается в обновлении**

```bash
grep -n "sub-orch" /home/user/projects/rag-fresh/CLAUDE.md
# Expected: нет результатов (CLAUDE.md не ссылается на sub-orch)
```

**Step 4: Финальный коммит если нужны доп. правки**

```bash
# только если grep нашёл broken references
git commit -m "fix(docs): remove remaining sub-orch references"
```

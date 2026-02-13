# Backlog Hygiene Deep-Review Implementation Plan

> **For Codex:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Провести глубокий ревью всех открытых issue, синхронизировать их с фактическим состоянием кода и привести бэклог к исполнимому состоянию (owners, приоритет, execution order).

**Architecture:** Работа идет в 3 параллельных доменах (Infra/Platform, Eval+Memory+Observability, Agentic Epic) с единым шаблоном ревью. Для каждого issue формируется verdict (keep/update/close/supersede), затем вносятся изменения в сам issue (body/comment/labels/assignee). Итогом является консистентный roadmap с топ-3 следующими задачами.

**Tech Stack:** GitHub Issues (`gh` CLI), локальный аудит кода (`git`, `grep`/`rg`), markdown-отчеты в `docs/reports`.

---

### Task 1: Зафиксировать baseline по open issues

**Files:**
- Create: `docs/reports/2026-02-12-issue-backlog-deep-review.md`
- Modify: `docs/plans/2026-02-12-backlog-hygiene-issue-review-plan.md`

**Step 1: Снять список open issue**

Run:
```bash
gh api 'repos/yastman/rag/issues?state=open&per_page=100' --paginate > /tmp/rag_open_issues.json
jq -r 'map(select(.pull_request|not)) | sort_by(.number)[] | [.number,.title,([.labels[].name]|join(",")),.updated_at] | @tsv' /tmp/rag_open_issues.json
```

Expected: полный список открытых issue без PR.

**Step 2: Зафиксировать baseline в отчет**

Записать в `docs/reports/2026-02-12-issue-backlog-deep-review.md`:
- total open issues
- issues without assignee
- grouped by domain labels.

**Step 3: Commit**

```bash
git add docs/reports/2026-02-12-issue-backlog-deep-review.md docs/plans/2026-02-12-backlog-hygiene-issue-review-plan.md
git commit -m "docs(triage): add backlog deep-review baseline"
```

### Task 2: Применить единый шаблон deep-review (rubric)

**Files:**
- Modify: `docs/reports/2026-02-12-issue-backlog-deep-review.md`

**Step 1: Добавить rubric для каждого issue**

Шаблон секции:
- Context
- Code reality check (файл/строка)
- Gaps
- Risks
- Decision: `keep` / `update` / `close` / `supersede`
- Next action.

**Step 2: Проверить, что rubric покрывает критерии #161**

Run:
```bash
grep -n "Decision:" docs/reports/2026-02-12-issue-backlog-deep-review.md
```

Expected: decision field есть для каждого issue.

**Step 3: Commit**

```bash
git add docs/reports/2026-02-12-issue-backlog-deep-review.md
git commit -m "docs(triage): add deep-review rubric for issue-level decisions"
```

### Task 3: Domain A review — Infra/Platform issues

**Files:**
- Modify: `docs/reports/2026-02-12-issue-backlog-deep-review.md`

**Scope Issues:** `#11, #54, #70, #71, #72, #73, #74, #75, #100, #102`

**Step 1: Проверить claim vs code**

Run targeted checks (пример):
```bash
grep -R -n -- '--mount=type=cache,target=/root/.cache/uv' Dockerfile* telegram_bot/Dockerfile services/*/Dockerfile
grep -R -n "BGE_M3_TIMEOUT" telegram_bot src
```

**Step 2: Для каждого issue заполнить verdict в отчете**

Expected outcomes:
- stale claims отмечены как `update/close`
- актуальные оставлены `keep` с конкретным next step.

**Step 3: Commit**

```bash
git add docs/reports/2026-02-12-issue-backlog-deep-review.md
git commit -m "docs(triage): review infra/platform issue domain"
```

### Task 4: Domain B review — Eval/Memory/Observability

**Files:**
- Modify: `docs/reports/2026-02-12-issue-backlog-deep-review.md`

**Scope Issues:** `#126, #127, #147, #152, #155, #157, #159`

**Step 1: Проверить дубли/конфликты roadmap**

Run:
```bash
grep -R -n "llm_queue_ms\|llm_decode_ms\|llm_tps\|streaming_enabled\|llm_timeout" telegram_bot tests src
nl -ba telegram_bot/integrations/memory.py | sed -n '1,120p'
```

**Step 2: Заполнить per-issue verdict + dependency chain**

Expected:
- явно зафиксирован execution order `#155 -> #157 -> #159` (или обновленный)
- зафиксирован единый memory direction для `#74/#152/#140/#159`.

**Step 3: Commit**

```bash
git add docs/reports/2026-02-12-issue-backlog-deep-review.md
git commit -m "docs(triage): review eval-memory-observability issue domain"
```

### Task 5: Domain C review — Agentic epic chain

**Files:**
- Modify: `docs/reports/2026-02-12-issue-backlog-deep-review.md`

**Scope Issues:** `#130, #132, #133, #134, #135, #136, #137, #138, #139, #140, #141, #142`

**Step 1: Проверить readiness каждого issue**

Критерии:
- есть acceptance criteria
- есть dependency clarity
- есть measurable DoD
- нет blocked-by ambiguity.

**Step 2: Сформировать dependency graph и milestones**

Expected:
- roadmap phase order и critical path зафиксированы в отчете.

**Step 3: Commit**

```bash
git add docs/reports/2026-02-12-issue-backlog-deep-review.md
git commit -m "docs(triage): review agentic epic issue domain"
```

### Task 6: Обновить issue bodies/comments по verdict

**Files:**
- Modify: GitHub issues (`#11, #54, #70, ... #159`)

**Step 1: Для issue с `update` — правка body**

Run (пример):
```bash
gh issue edit 72 --repo yastman/rag --body-file /tmp/issue72-updated.md
```

**Step 2: Для issue с `close/supersede` — комментарий + закрытие**

Run (пример):
```bash
gh issue comment 72 --repo yastman/rag --body "Superseded by ..."
gh issue close 72 --repo yastman/rag --reason completed
```

**Step 3: Для `keep` — добавить actionable comment**

Expected: каждый open issue имеет актуальный next action.

### Task 7: Назначить owners и priority labels

**Files:**
- Modify: GitHub issues

**Step 1: Assign P0/P1 issues**

Run (пример):
```bash
gh issue edit 155 --repo yastman/rag --add-assignee yastman
```

**Step 2: Проверить, что нет приоритетных issue без owner**

Run:
```bash
gh issue list --repo yastman/rag --state open --limit 200 --json number,title,labels,assignees
```

Expected: все high-priority issue с owner.

### Task 8: Зафиксировать execution order и закрыть #161

**Files:**
- Modify: issue `#161`
- Modify: `docs/reports/2026-02-12-issue-backlog-deep-review.md`

**Step 1: Добавить final summary в #161**

Содержимое:
- что закрыли/обновили,
- какие issue остались,
- топ-3 задачи next.

**Step 2: Проверить acceptance criteria #161**

Checklist:
- owners назначены,
- stale descriptions устранены,
- memory strategy зафиксирована,
- next 3 tasks определены.

**Step 3: Закрыть #161**

```bash
gh issue close 161 --repo yastman/rag --reason completed
```

### Task 9: Verification Before Completion

**Files:**
- Modify: none

**Step 1: Проверка целостности итогов**

Run:
```bash
gh issue list --repo yastman/rag --state open --limit 200 --json number,title,assignees,labels > /tmp/open_after_triage.json
```

**Step 2: Проверка локальных изменений**

Run:
```bash
git status --short
```

Expected: только ожидаемые docs-изменения.

**Step 3: Финальный commit**

```bash
git add docs/reports/2026-02-12-issue-backlog-deep-review.md
git commit -m "docs(triage): finalize backlog hygiene execution and issue decisions"
```

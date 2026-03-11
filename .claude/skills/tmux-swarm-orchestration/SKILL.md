---
name: tmux-swarm-orchestration
description: Use when given GitHub issues to solve, problems to fix, or "review all open issues". Also for running heavy commands on VPS through user's terminal. Triggers on "реши issue", "fix #123", "изучи все открытые", "parallel workers", "swarm", "spawn-claude", "tmux воркеры", "VPS команда"
---

# tmux Swarm Оркестрация v10

<HARD-GATE>
ТЫ = OPUS = ДИСПЕТЧЕР. Юзер дал issues — дальше ВСЁ автоматом до PR URLs.
НЕ исследуешь файлы напрямую, НЕ пишешь код. ЛЮБАЯ задача → worker.
ПОСЛЕ worker: ЛИЧНО читаешь diff (Фаза 5.0) — это твоя ответственность, не worker'а.
Opus inline = $15, Sonnet worker = $3.
КООРДИНАЦИЯ: Task List (CLAUDE_CODE_TASK_LIST_ID) — orch видит статус worker'ов через system-reminder автоматически. БЕЗ polling, БЕЗ sleep.
</HARD-GATE>

## Конвейер

| Сложность | Поток | Модель |
|-----------|-------|--------|
| TRIVIAL/CLEAR | SDK исследование? → Sonnet A → PR | `--model sonnet` |
| MEDIUM | Haiku фильтрация → SDK исследование? → Sonnet A → PR | Haiku + `--model sonnet` |
| COMPLEX | SDK? → Opus C → план → **Opus решает** → 1 или N Sonnet B → PR | default + `--model sonnet` |
| VERY COMPLEX (группы) | SDK? → Opus C → план → **Opus решает** → 1 или N Sonnet B → PRs | default + N × `--model sonnet` |
| VERY COMPLEX (solo) | SDK? → Opus D → полный цикл → PR | default (Opus) |

## Поток

```dot
digraph flow {
  rankdir=TB; node [shape=box, fontsize=10];
  init [label="Фаза 0: ВВОД\ngh issue view + mkdir -p .signals"];
  codebase [label="Фаза 2.3: CODEBASE КОНТЕКСТ\nGrepAI + LSP + context-mode"];
  classify [label="Фаза 2: КЛАССИФИКАЦИЯ\nRead classification.md"];
  parallel [label="Фаза 2.5: ПАРАЛЛЕЛИЗАЦИЯ\nfile overlap + резервации"];
  sdk [label="Фаза 2.7: SDK КОНТЕКСТ\nОБЯЗАТЕЛЬНО если sdk-registry.md\nматч triggers → Sonnet субагент"];
  spawn [label="Фаза 3: ЗАПУСК\nRead infrastructure.md\nRead worker-contract.md\nTaskCreate + DAG + TASK_LIST_ID"];
  wait [label="Фаза 4: EVENT-DRIVEN\norch продолжает работу\nsystem-reminder пушит статус задач"];
  review [label="Фаза 5.0: CODE REVIEW\norch лично читает diff\nчерез context-mode"];
  verify [label="Фаза 5.1: ВЕРИФИКАЦИЯ\nартефакты + маркеры"];
  sdkupd [label="Фаза 5.2: SDK РЕЕСТР\nобновить паттерны/gotchas\nновые SDK из diff"];
  report [label="Фаза 6: ОТЧЁТ\nPR URLs + метрики → юзеру\nочистка"];

  init -> codebase -> classify -> parallel -> sdk -> spawn -> wait -> review -> verify -> sdkupd -> report;
  review -> spawn [label="diff неверный\nэскалация 1x", style=dashed];
  verify -> spawn [label="артефакты провал\nэскалация 1x", style=dashed];
}
```

**Фаза 2.7: SDK КОНТЕКСТ** — **ОБЯЗАТЕЛЬНА** если `.claude/rules/sdk-registry.md` существует:

    # 1. Проверить наличие реестра:
    test -f .claude/rules/sdk-registry.md || echo "NO_REGISTRY → skip to Phase 3"

    # 2. Если есть — прочитать и матчить triggers:
    Read .claude/rules/sdk-registry.md
    Для каждого SDK: сравнить triggers с issue body keywords
    Матч = SDK затронут → запомнить context7_id + как_у_нас + gotchas

    # 3. При матче — Sonnet субагент для актуальной документации:
    Agent(model="sonnet", subagent_type="general-purpose",
      prompt="РЕЕСТР: {sdk_registry_excerpt_for_matched_sdk}
      Context7: resolve-library-id('{context7_id}') → query-docs('{topic из issue}')
      Exa: get_code_context_exa('{library} {topic} 2026')
      Сравни с как_у_нас из реестра — отметь если паттерн устарел.
      Резюме (300 слов) верни мне. Полный контекст → .claude/cache/sdk-{lib}-{N}.md")

    # 4. Собрать {sdk_registry_excerpt} — релевантные блоки из реестра для промта worker'а
    # Включает: как_у_нас + паттерны + gotchas для каждого совпавшего SDK

    # 5. Даже без матча — список SDK (имена + triggers) для awareness в промте worker'а
    # 6. Нет реестра → поведение как раньше (по усмотрению orch)

Переиспользование: одно исследование → N воркеров.

**Фаза 3: ЗАПУСК — ОБЯЗАТЕЛЬНЫЙ ЧЕКЛИСТ (HARD-GATE):**

<HARD-GATE>
ПЕРЕД спавном КАЖДОГО worker'а orch ОБЯЗАН выполнить ВСЕ 4 шага. Пропуск = сломанный worker.

    # ШАГ 1: Создать задачи в Task List
    TaskCreate(subject="...", description="...", metadata={issue: N, contract: "A"})
    # DAG если нужно:
    TaskUpdate(taskId="2", addBlockedBy=["1"])

    # ШАГ 2: Найти TASK_LIST_ID
    TASK_LIST_ID=$(ls -t ~/.claude/tasks/ | head -1)

    # ШАГ 3: Написать промт в файл (см. worker-contract.md)
    # Промт ОБЯЗАН содержать секцию "## TASK LIST" с taskId и алгоритмом

    # ШАГ 4: Спавнить через tmux (см. infrastructure.md)
    TMUX="" tmux new-window -n "W-{NAME}" -c "$WT_PATH"
    sleep 5
    TMUX="" tmux send-keys -t "W-{NAME}" C-c
    sleep 0.5
    TMUX="" tmux send-keys -t "W-{NAME}" "env CLAUDE_CODE_TASK_LIST_ID=${TASK_LIST_ID} claude --model sonnet --dangerously-skip-permissions \"\$(cat ${PROJECT_ROOT}/.claude/prompts/worker-{name}.md)\"" Enter

БЕЗ `env CLAUDE_CODE_TASK_LIST_ID` worker НЕ видит задачи → координация сломана.
БЕЗ `C-c` перед командой → мусорные символы от shell init → `ienv`/`вexport` → команда не найдена.
БЕЗ секции "## TASK LIST" в промте → worker не знает свой taskId → не обновляет статус.
</HARD-GATE>

**Фаза 3 (продолжение): ЗАПОЛНЕНИЕ SDK-плейсхолдеров в промте worker'а:**

При записи промта в `.claude/prompts/worker-{name}.md` orch ОБЯЗАН заполнить:

    {sdk_summary}           → Резюме (300 слов) от Sonnet субагента из Фазы 2.7 (или пусто)
    {sdk_registry_excerpt}  → Релевантные блоки из .claude/rules/sdk-registry.md:
                               для каждого SDK с совпавшими triggers — скопировать:
                               - как_у_нас (файлы + паттерны)
                               - gotchas (антипаттерны)
                               Без матча → краткий список всех SDK (имя + triggers) для awareness

Пример {sdk_registry_excerpt} для issue "добавить кнопку в меню":

    ## aiogram-dialog
    как_у_нас: telegram_bot/dialogs/ — Window+Select+Button, states.py централизованно
    паттерны: SwitchTo для навигации, Start для дочерних, getter= для данных
    gotchas: НЕ писать кастомные InlineKeyboard — использовать Select/Button/SwitchTo

    ## Другие SDK в проекте (awareness):
    aiogram, langgraph, qdrant-client, instructor, redisvl, langfuse, langmem,
    apscheduler, fluentogram, cocoindex, livekit-agents, asyncpg

**Фаза 2.3: CODEBASE КОНТЕКСТ** — orch использует 3 системы:

    # 1. GrepAI — semantic search + call graph:
    grepai_search(query="{issue_description}", limit=5, format="toon", compact=true)
    grepai_trace_callers(symbol="{affected_function}", format="toon", compact=true)
    grepai_trace_graph(symbol="{key_symbol}", depth=1, format="toon")  # полный граф
    grepai_index_status(format="toon")  # проверить актуальность

    # 2. LSP — точные типы, сигнатуры, references:
    LSP(operation="documentSymbol", filePath="{file}")  # структура файла
    LSP(operation="hover", filePath="{file}", line=N, character=M)  # тип + docstring
    LSP(operation="findReferences", filePath="{file}", line=N, character=M)  # все ссылки
    LSP(operation="incomingCalls", filePath="{file}", line=N, character=M)  # кто вызывает

    # 3. context-mode — сбор контекста без засорения окна:
    batch_execute(commands=[
      {label: "project_scope", command: "head -20 README.md && ls src/"},
      {label: "recent_commits", command: "git log --oneline -5"},
      {label: "open_prs", command: "gh pr list --limit 5 --json number,title"}
    ], queries=["project structure", "recent changes"])

| Система | Когда | Что даёт |
|---------|-------|----------|
| GrepAI | Понять scope issue | Семантический поиск + call graph (edges, callers) |
| LSP | Точные типы/сигнатуры | documentSymbol, hover, findReferences, incomingCalls |
| context-mode | Любой output >20 строк | execute/batch_execute — output в sandbox, summary в контекст |
| Context7/Exa | SDK/библиотека | Документация, примеры (через субагент в Фазе 2.7) |

**Двухволновой запуск (COMPLEX+) — Opus решает:**

Opus C анализирует задачи и выдаёт в сигнале `"execution": "sequential"` или `"parallel"`.

    # Orch читает сигнал:
    execution=$(cat .signals/worker-{name}.json | python3 -c "import sys,json; print(json.load(sys.stdin).get('execution','sequential'))")

| Решение Opus | Действие orch |
|--------------|---------------|
| `sequential` | 1 Sonnet B с полным планом → 1 PR |
| `parallel` | Парсить группы из плана → N Sonnet B, каждый со своей группой задач |

При `parallel` orch создаёт **волны**:
1. **Независимые группы** → параллельные Sonnet B в отдельных worktree (`{branch}-part-{N}`)
2. **Зависимые группы** → после завершения тех, от кого зависят
3. **Финальная группа** → последний worker ребейзит все ветки в `{branch}`, создаёт 1 PR

Orch НЕ переопределяет решение Opus. Opus видел код, зависимости и файлы — он решает.

**Фаза 5: ВЕРИФИКАЦИЯ** — трёхуровневая:

### Уровень 0: Code Review (orch лично — ОБЯЗАТЕЛЬНО)

Orch **лично** читает diff через context-mode. Worker может пройти тесты, но решить не ту проблему.

    # Для кодовых контрактов (A/B/D) — diff в sandbox, summary в контекст:
    mcp execute(language="shell", code="""
      cd '{WT_PATH}' && git diff dev...HEAD 2>&1
    """, intent="code review: verify changes match issue #{N} requirements")

    # Для контракта C — план в sandbox:
    mcp execute_file(path="docs/plans/{DATE}-issue-{N}-plan.md", language="shell",
      code="cat \"$FILE_CONTENT_PATH\"",
      intent="plan review: verify completeness and correctness")

| Проверка | Вопрос |
|----------|--------|
| Соответствие issue | Изменения решают именно то, что описано? |
| Scope creep | Нет лишних изменений? |
| Корректность | Логика правильная? Нет очевидных багов? |

    diff OK → Уровень 1
    diff WRONG → FAIL → эскалация
    diff PARTIAL → PASS + WARNING

**HARD-GATE:** Orch НЕ МОЖЕТ пропустить Уровень 0. "Тесты прошли = всё ок" — ЗАПРЕЩЕНО.

### Уровень 1: Артефактная проверка

Через **context-mode execute** (output не засоряет контекст):

    mcp execute(language="shell", code="""
      WT='{WT_PATH}'
      echo "=== New tests ===" && find "$WT" -name "test_*" -newer "$WT/.git/HEAD" 2>/dev/null | wc -l
      echo "=== Lint + types ===" && cd "$WT" && make check 2>&1 | tail -5
      echo "=== Unit tests ===" && cd "$WT" && PYTEST_ADDOPTS='-n auto' make test-unit 2>&1 | tail -10
      echo "=== PR ===" && gh pr list --head "{branch}" --json url,title
    """, intent="verification: tests, lint, PR status")

    # Для контракта C:
    mcp execute(language="shell", code="wc -w < 'docs/plans/{DATE}-issue-{N}-plan.md'")

| Контракт | Артефакты |
|----------|-----------|
| A/B/D | Новые тесты + `make check` чисто + `make test-unit` pass + PR создан |
| C | План >200 слов + содержит секции: файлы, подход, задачи |

### Уровень 2: Маркеры скиллов (дополнительный)

    grep '\[SKILL:' logs/worker-{name}.log

| Контракт | Мин. маркеры |
|----------|--------------|
| A | tdd, review, verify (3) |
| B | executing-plans, tdd, review, verify (4) |
| C | writing-plans (1) |
| D | все 5 |

**Артефакты = решение.** Маркеры = быстрая проверка. Артефакты есть, маркеров нет → PASS с WARNING. Артефактов нет → FAIL независимо от маркеров.

### Решение при провале

    Code Review OK + Артефакты OK + маркеры OK → PASS
    Code Review OK + Артефакты OK + маркеры MISSING → PASS + WARNING в отчёте
    Code Review OK + Артефакты FAIL → FAIL → эскалация (код верный, но CI не проходит)
    Code Review FAIL → FAIL → эскалация (артефакты не проверяем)

### Фаза 5.2: Обновление SDK реестра (orch лично)

После PASS верификации — **orch сам** анализирует diff и обновляет реестр. Worker'ы НЕ участвуют (Sonnet ненадёжен для мета-анализа).

    # 1. Orch анализирует diff через context-mode (уже прочитан в Phase 5.0):
    mcp execute(language="shell", code="""
      cd '{WT_PATH}'
      echo '=== Новые импорты ==='
      git diff dev...HEAD | grep -E '^\+.*from .* import|^\+.*import ' | sort -u
      echo '=== pyproject.toml ==='
      git diff dev...HEAD -- pyproject.toml 2>/dev/null | grep -E '^\+' | head -20
      echo '=== Новые файлы ==='
      git diff dev...HEAD --name-only --diff-filter=A
    """, intent="SDK registry update: detect new imports, deps, patterns in worker diff")

    # 2. Orch ЛИЧНО сверяет с реестром:
    Read .claude/rules/sdk-registry.md
    # Для каждого нового import/dep:
    #   - Есть в реестре? → проверить: новый паттерн использования?
    #   - Нет в реестре? → добавить секцию по шаблону
    # Для изменённых файлов:
    #   - Новый паттерн SDK (отличается от как_у_нас)? → обновить

    # 3. При обнаружении обновлений — orch редактирует реестр в dev:
    git stash  # если есть незакоммиченное в dev
    Edit .claude/rules/sdk-registry.md
    git add .claude/rules/sdk-registry.md
    git commit -m "docs(sdk): update registry — {краткое описание}"
    git stash pop  # вернуть если было

| Что orch ищет в diff | Действие |
|----------------------|----------|
| Новый `from X import` где X — известный SDK | Обновить `как_у_нас` + `паттерны` |
| Новый `from X import` где X — неизвестный SDK | Новая секция по шаблону |
| Новая dep в pyproject.toml | Новая секция по шаблону |
| Удалённая dep из pyproject.toml | Удалить/пометить deprecated |
| Новый файл в известной SDK-директории | Обновить `как_у_нас` (новый модуль) |
| Паттерн отличается от `как_у_нас` | Обновить `паттерны` + добавить `gotcha` если старый был неверный |

**Правила:**
- Orch делает это **лично** — worker'ы не трогают реестр
- Обновление в **dev** ветке, НЕ в worktree worker'а
- Коммит отдельный от PR worker'а
- Нет обновлений → пропустить (не коммитить пустое)
- Реестр не существует → пропустить фазу

## Эскалация

    CLEAR провалился   → MEDIUM  (orch добавляет {project_scope} в промт → перезапуск)
    MEDIUM провалился  → COMPLEX (Opus C → план → Sonnet B)
    COMPLEX провалился → D       (Opus solo — полный цикл)
    D провалился       → gh issue comment "needs-human" → пропуск

## Контекст-бюджет

≤5K токенов на issue (до review). Code review через context-mode execute — diff остаётся в sandbox, в контекст попадает только summary от intent. Orch читает: `gh issue view`, `.signals/*.json` (<1K), diff через context-mode (~0 контекста).

## Фаза 6: Финальный отчёт

После завершения всех воркеров orch генерирует:

    ## Отчёт сессии

    | Issue | Уровень | Контракт | Worker | Время | ~Стоимость | PR | Статус |
    |-------|---------|----------|--------|-------|-----------|-----|--------|
    | #{N}  | CLEAR   | A        | W-{name} | {m}m{s}s | ~$3 | #{pr} | done |
    | #{N}  | COMPLEX | C→B      | W-{name} | {m}m | ~$8 | #{pr} | done |
    | #{N}  | MEDIUM  | A        | W-{name} | — | ~$3 | — | timeout→escalate |

    **Итого:** {X} issues, {Y} PRs, {Z} эскалаций, ~${total}, {wall_time} wall-time

    **PR URLs:**
    - #{pr1}: {title1}
    - #{pr2}: {title2}

Стоимость: оценка (Sonnet A ≈ $3, Opus C ≈ $5, C→B ≈ $8, C→N×B ≈ $3+N×$3, Opus D ≈ $15). Время: из `orch-log.jsonl`.

## Вспомогательные файлы

- **classification.md** — блок-схема классификации + маркеры + file overlap + sizing
- **worker-contract.md** — 4 контракта + общий финал + sandbox + резервации
- **infrastructure.md** — tmux, worktree, сигналы, таймауты, orch-log, VPS
- **red-flags.md** — чеклист + рационализации

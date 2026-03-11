# Инфраструктура

Механика tmux, worktree, сигналов, таймаутов, очистки.

## Идентификация оркестратора

    ORCH_NAME="ORCH-{N}"
    tmux rename-window -t "$TMUX_PANE" "$ORCH_NAME"

**КРИТИЧНО:** `display-message` без `-t "$TMUX_PANE"` → АКТИВНОЕ окно юзера, не ваше.

## Инициализация

    PROJECT_ROOT=$(git rev-parse --show-toplevel)
    mkdir -p logs .signals

## Task List координация (cross-session)

Shared Task List — основной канал координации orch ↔ workers. Работает через `CLAUDE_CODE_TASK_LIST_ID`.

    # Orch обычно запускается БЕЗ CLAUDE_CODE_TASK_LIST_ID → получает случайный UUID.
    # Шаг 1: Создать хотя бы 1 задачу (чтобы task list появился на диске):
    TaskCreate(subject="...", description="...", metadata={issue: N, contract: "A"})

    # Шаг 2: Обнаружить свой task list ID (самая свежая директория):
    TASK_LIST_ID=$(ls -t ~/.claude/tasks/ | head -1)

    # Шаг 3: DAG зависимости:
    TaskUpdate(taskId="2", addBlockedBy=["1"])

    # Шаг 4: Worker спавнится с тем же ID (см. Запуск воркеров)
    # Worker видит задачи через TaskList, берёт через TaskUpdate(in_progress)
    # Orch АВТОМАТИЧЕСКИ видит изменения через system-reminder — БЕЗ polling

    # АЛЬТЕРНАТИВА: если orch запущен С CLAUDE_CODE_TASK_LIST_ID (named):
    # TASK_LIST_ID="$CLAUDE_CODE_TASK_LIST_ID"  # уже задан

### Как orch узнаёт о прогрессе

System-reminder **автоматически** пушит состояние task list в контекст orch:

    # Orch НЕ вызывает TaskList — система сама показывает:
    # > #1 [completed] Fix auth bug
    # > #2 [in_progress] Add tests  [owner: W-AUTH]
    # > #3 [pending] Integration check  [blocked by #1, #2]

    # Orch видит completed → сразу переходит к Phase 5 (code review)
    # Orch видит in_progress → продолжает свою работу (другие workers, SDK research)

**Completed задачи удаляются с диска.** Поэтому:
- Task List = **live координация** (статус, DAG, owner, real-time UI через Ctrl+T)
- `.signals/` = **persist** (PR url, learnings, quality metrics — нужны после завершения)

### Named task lists (для multi-session)

    # Вместо UUID — именованный ID:
    export CLAUDE_CODE_TASK_LIST_ID="sprint-42"
    # Хранится в ~/.claude/tasks/sprint-42/
    # Полезно для: возобновление после крэша, аудит

## Worktree

| Контракт | Метод |
|----------|-------|
| A/B/D (код) | `git worktree add "${PROJECT_ROOT}-wt-{name}" -b {branch}` + `mkdir -p "${PROJECT_ROOT}-wt-{name}/logs"` + `cd "${PROJECT_ROOT}-wt-{name}" && uv sync --quiet \|\| { echo "uv sync failed"; exit 1; }` |
| C (исследование) | Без worktree. `${PROJECT_ROOT}` на main. |

**КРИТИЧНО:** `mkdir -p logs` в worktree ОБЯЗАТЕЛЬНО — worktree не копирует gitignored директории (`logs/`).

**НИКОГДА `claude --worktree`** для tmux workers — удаляет worktree при exit, коммиты ПОТЕРЯНЫ.

### Изоляция секретов

`.env` gitignored → НЕ копируется в worktree автоматически. Это правильно.

    # Для тестов — только тестовые значения:
    cp .env.test "${PROJECT_ROOT}-wt-{name}/.env"

**ЗАПРЕЩЕНО** копировать production `.env` в worktree. Worker не должен иметь доступ к prod-секретам.

## Запуск воркеров

Промты → `.claude/prompts/worker-{name}.md`. **НИКОГДА** inline.

**КРИТИЧНО:** `env VAR=val command` вместо `VAR=val command` — tmux send-keys может разбить длинную строку, и shell увидит `VAR=val` как отдельную команду. `env` решает это.

    # Sonnet (Контракт A/B) — worktree:
    TMUX="" tmux new-window -n "W-{NAME}" -c "$WT_PATH"
    sleep 5
    TMUX="" tmux send-keys -t "W-{NAME}" C-c
    sleep 0.5
    TMUX="" tmux send-keys -t "W-{NAME}" "env CLAUDE_CODE_TASK_LIST_ID=${TASK_LIST_ID} claude --model sonnet --dangerously-skip-permissions \"\$(cat ${PROJECT_ROOT}/.claude/prompts/worker-{name}.md)\"" Enter

    # Opus (Контракт C) — корень проекта:
    TMUX="" tmux new-window -n "W-{NAME}" -c "$PROJECT_ROOT"
    sleep 5
    TMUX="" tmux send-keys -t "W-{NAME}" C-c
    sleep 0.5
    TMUX="" tmux send-keys -t "W-{NAME}" "env CLAUDE_CODE_TASK_LIST_ID=${TASK_LIST_ID} claude --dangerously-skip-permissions \"\$(cat ${PROJECT_ROOT}/.claude/prompts/worker-{name}.md)\"" Enter

    # Opus Соло (Контракт D) — worktree:
    TMUX="" tmux new-window -n "W-{NAME}" -c "$WT_PATH"
    sleep 5
    TMUX="" tmux send-keys -t "W-{NAME}" C-c
    sleep 0.5
    TMUX="" tmux send-keys -t "W-{NAME}" "env CLAUDE_CODE_TASK_LIST_ID=${TASK_LIST_ID} claude --dangerously-skip-permissions \"\$(cat ${PROJECT_ROOT}/.claude/prompts/worker-{name}.md)\"" Enter

**КРИТИЧНО:**
- `sleep 5` + `C-c` + `sleep 0.5` перед командой (shell gruzится, zshrc фонит background jobs — `C-c` чистит буфер от мусорных символов)
- `--dangerously-skip-permissions` обязателен
- `TMUX=""` перед `tmux` обязателен (вложенные операции)
- `env VAR=val` вместо `VAR=val` (tmux send-keys ломает bare assignment при длинных строках)

**НЕ ИСПОЛЬЗОВАТЬ:**
- `| tee` — claude CLI использует TUI, pipe ломает рендеринг
- `export VAR && command` через send-keys — tmux может подхватить активную раскладку и добавить мусорные символы
- `VAR=val command` (без `env`) — при длинных строках tmux разбивает на линии, shell видит `VAR=val` как отдельную команду

## Сигнализация

### Файловые сигналы (основной метод)

Worker → orch через JSON-файлы в `.signals/`. **Атомарная запись** (write .tmp → mv) предотвращает partial reads:

    # Worker пишет при завершении:
    echo '{"status":"done","worker":"W-{NAME}","pr":"{url}","ts":"'$(date -Iseconds)'"}' \
      > ${PROJECT_ROOT}/.signals/worker-{name}.json.tmp \
      && mv ${PROJECT_ROOT}/.signals/worker-{name}.json.tmp ${PROJECT_ROOT}/.signals/worker-{name}.json

    # Worker пишет при провале:
    echo '{"status":"failed","worker":"W-{NAME}","error":"{msg}","ts":"'$(date -Iseconds)'"}' \
      > ${PROJECT_ROOT}/.signals/worker-{name}.json.tmp \
      && mv ${PROJECT_ROOT}/.signals/worker-{name}.json.tmp ${PROJECT_ROOT}/.signals/worker-{name}.json

    # Контракт C — путь к плану + execution решение:
    echo '{"status":"done","worker":"W-{NAME}","plan":"{path}","execution":"{sequential|parallel}","groups":{N},"ts":"'$(date -Iseconds)'"}' \
      > ${PROJECT_ROOT}/.signals/worker-{name}.json.tmp \
      && mv ${PROJECT_ROOT}/.signals/worker-{name}.json.tmp ${PROJECT_ROOT}/.signals/worker-{name}.json

### Orch мониторинг (event-driven через Task List)

**Основной метод:** system-reminder автоматически пушит состояние task list в контекст orch. Orch **не поллит** — он продолжает работу (SDK research, спавн других workers), и система сама уведомляет о смене статусов.

    # Orch НЕ делает sleep/polling. Вместо этого:
    # 1. Спавнит worker'ов
    # 2. Продолжает свою работу (Phase 2.7 для следующего issue, etc.)
    # 3. System-reminder показывает: "#1 [completed]" → orch переходит к Phase 5
    #
    # Если orch хочет явно проверить:
    TaskList  # → текущее состояние всех задач

**Fallback (`.signals/`):** для rich metadata (PR url, learnings, execution plan) worker по-прежнему пишет `.signals/worker-{name}.json`. Orch читает при Phase 5 review.

**КРИТИЧНО:** orch обработал `.signals/` → переименовать файл (`done-*`) чтобы не обработать повторно.

### Чтение сигналов через context-mode

При обработке сигнала — используй context-mode для верификации (output не засоряет контекст):

    # Проверить все сигналы за один вызов:
    mcp batch_execute(commands=[
      {label: "signals", command: "cat .signals/worker-*.json 2>/dev/null"},
      {label: "logs", command: "tail -20 logs/worker-*.log 2>/dev/null"}
    ], queries=["worker status done or failed", "skill markers"])

    # Code review diff через context-mode (Фаза 5.0):
    mcp execute(language="shell", code="""
      cd '{WT_PATH}' && git diff dev...HEAD 2>&1
    """, intent="code review: verify changes match issue #{N}")

### tmux send-keys (запасной метод)

Если файловые сигналы невозможны (VPS, нет общей FS):

    TMUX="" tmux send-keys -t "{ORCH_NAME}" "[DONE] W-{NAME}: PR {url}"
    TMUX="" tmux send-keys -t "{ORCH_NAME}" Enter

## Таймауты

Watchdog запускается параллельно с каждым worker:

    # Запуск watchdog (сразу после запуска worker):
    ( sleep ${TIMEOUT} && \
      [ ! -f .signals/worker-{name}.json ] && [ ! -f .signals/done-worker-{name}.json ] && \
      echo '{"status":"timeout","worker":"W-{NAME}","ts":"'$(date -Iseconds)'"}' > ${PROJECT_ROOT}/.signals/worker-{name}.json && \
      TMUX="" tmux send-keys -t "W-{NAME}" C-c ) &

| Контракт | Таймаут | Обоснование |
|----------|---------|-------------|
| A (TRIVIAL/CLEAR) | 15 мин (900) | Простая задача, TDD + review |
| B (план → код) | 30 мин (1800) | Выполнение плана с TDD |
| B-part (часть плана) | 20 мин (1200) | Часть плана, без PR |
| B-final (интеграция) | 15 мин (900) | Merge + make check + PR |
| C (исследование) | 20 мин (1200) | Только чтение + план |
| D (Opus соло) | 45 мин (2700) | Полный цикл |

**Таймаут → эскалация**, не повтор. Застрявший worker = неверная классификация.

## Маркеры скиллов в логах

Workers логируют `[SKILL:*]` → `logs/worker-{name}.log`:

    echo "[SKILL:{skill_name}] $(date -Iseconds)" >> logs/worker-{name}.log

Orch проверяет (Фаза 5): `grep '\[SKILL:' logs/worker-{name}.log`

| Контракт | Мин. маркеры |
|----------|--------------|
| A | tdd, review, verify (3) |
| B | executing-plans, tdd, review, verify (4) |
| C | writing-plans (1) |
| D | все 5 |

**Маркеры = быстрая проверка.** Основная верификация — по артефактам (см. SKILL.md Фаза 5).

## Центральный лог оркестратора

Orch логирует ВСЕ события в `.signals/orch-log.jsonl`:

    # Хелпер (в начале сессии):
    orch_log() { echo "{\"ts\":\"$(date -Iseconds)\",\"event\":\"$1\",$2}" >> .signals/orch-log.jsonl; }

    # Использование:
    orch_log "classify" "\"issue\":${N},\"level\":\"CLEAR\",\"contract\":\"A\""
    orch_log "spawn"    "\"worker\":\"W-{NAME}\",\"worktree\":\"${WT_PATH}\",\"timeout\":900"
    orch_log "done"     "\"worker\":\"W-{NAME}\",\"pr\":\"${url}\",\"duration_s\":${dur}"
    orch_log "timeout"  "\"worker\":\"W-{NAME}\",\"escalate\":\"MEDIUM\""
    orch_log "failed"   "\"worker\":\"W-{NAME}\",\"reason\":\"${msg}\""
    orch_log "skip"     "\"issue\":${N},\"reason\":\"stale\""

Просмотр: `cat .signals/orch-log.jsonl | python3 -m json.tool --no-ensure-ascii`

## Двухволновой запуск (COMPLEX+)

1. **Волна 1:** Opus C → план → сигнал с `execution` решением
2. **Волна 2:** Orch читает сигнал и действует:

### execution: sequential (по умолчанию)

    # 1 Sonnet B с полным планом:
    git worktree add "${PROJECT_ROOT}-wt-${issue}" -b "fix/${issue}-impl"
    # Запуск Контракт B → 1 PR

### execution: parallel (Opus решил)

    # Orch парсит группы из плана и запускает волнами:

    # Волна 2a: независимые группы — параллельно
    git worktree add "${PROJECT_ROOT}-wt-${issue}-grpA" -b "fix/${issue}-part-a"
    git worktree add "${PROJECT_ROOT}-wt-${issue}-grpB" -b "fix/${issue}-part-b"
    # Sonnet B в каждом worktree со СВОЕЙ частью плана

    # Волна 2b: зависимые группы — после завершения тех, от кого зависят
    # Orch ждёт сигналы от grpA/grpB → запускает grpC

    # Волна 2c: финальная интеграция
    # Последний worker: rebase всех part-веток в основную ветку
    git worktree add "${PROJECT_ROOT}-wt-${issue}-final" -b "fix/${issue}"
    # В промте финального worker:
    #   git merge --no-ff origin/fix/${issue}-part-a
    #   git merge --no-ff origin/fix/${issue}-part-b
    #   Разрешить конфликты если есть → make check → 1 PR

**КРИТИЧНО:** part-workers используют **Контракт B-part** (НЕ обычный B):
- Коммит + push — ДА
- `gh pr create` — НЕТ (только финальный worker создаёт PR)
- Сигнал: `{"status":"done","worker":"W-{NAME}","branch":"{branch}"}` (без `"pr"`)

В промте part-worker добавить: `ФИНАЛ: git add + commit + push. НЕ создавай PR. НЕ используй {Общий финал}.`

## Очистка

    TMUX="" tmux kill-window -t "W-{NAME}" 2>/dev/null
    git worktree remove "${PROJECT_ROOT}-wt-{name}" 2>/dev/null
    git branch -d {branch_name} 2>/dev/null
    rm -f .signals/done-worker-{name}.json 2>/dev/null

**Orch НЕ мержит. Workers сами push + PR.**

## Безопасность tmux

- НИКОГДА `tmux new-session` (отключает юзера)
- ВСЕГДА `TMUX=""` (вложенные операции)
- Сокет сломался: `pkill -USR1 tmux`

## VPS удалённый запуск

    SESSION=$(TMUX="" tmux list-sessions -F "#{session_name}" | head -1)
    TMUX="" tmux new-window -t "$SESSION" -n "W-VPS"
    TMUX="" tmux send-keys -t "$SESSION:W-VPS" 'ssh vps' Enter
    sleep 2
    TMUX="" tmux send-keys -t "$SESSION:W-VPS" 'cd /opt/rag-fresh && {command} 2>&1 | tee logs/{name}.log; echo "[COMPLETE]"' Enter

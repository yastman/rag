# Инфраструктура

Механика tmux, worktree, сигналов, таймаутов, очистки.

## Идентификация оркестратора

    ORCH_NAME="ORCH-{N}"
    tmux rename-window -t "$TMUX_PANE" "$ORCH_NAME"

**КРИТИЧНО:** `display-message` без `-t "$TMUX_PANE"` → АКТИВНОЕ окно юзера, не ваше.

### OpenCode: pane оркестратора

Если пользователь вызвал skill в текущем окне оркестратора и worker'ы запускаются через `opencode`, НЕ полагайся на имя или номер окна. Сохрани точный pane id:

    ORCH_PANE=$(tmux display-message -p '#{pane_id}')
    tmux display-message -p -t "$ORCH_PANE" '#{pane_id}'

Передавай worker'ам именно `$ORCH_PANE` (`%0`, `%14`, ...). Это работает даже если оркестратор не первое окно. Если оркестратор полностью перезапущен — получить новый `ORCH_PANE` перед новым запуском worker'ов.

## Инициализация

    PROJECT_ROOT=$(git rev-parse --show-toplevel)
    mkdir -p logs .signals

## Координация orch ↔ workers

Основной канал — worker-local `{WORKTREE}/.signals/worker-{name}.json` + короткий `[DONE] ...json` wake-up в pane оркестратора.

    ORCH_PANE=$(tmux display-message -p '#{pane_id}')
    SIGNAL_FILE="${WT_PATH}/.signals/worker-{name}.json"
    mkdir -p "${WT_PATH}/.signals"

Worker пишет JSON атомарно (`.tmp` → `mv`), затем отправляет в pane оркестратора:

    tmux send-keys -t "$ORCH_PANE" "[DONE] W-{NAME} ${SIGNAL_FILE}"
    sleep 1
    tmux send-keys -t "$ORCH_PANE" Enter

Orch не читает transcript и не поллит pane output. Источник истины — JSON.

## Worktree

| Контракт | Метод |
|----------|-------|
| A/B/D (код) | `git worktree add "${PROJECT_ROOT}-wt-{name}" -b {branch}` + `mkdir -p "${PROJECT_ROOT}-wt-{name}/logs"` + `cd "${PROJECT_ROOT}-wt-{name}" && uv sync --quiet \|\| { echo "uv sync failed"; exit 1; }` |
| C (исследование/план) | `git worktree add "${PROJECT_ROOT}-wt-{name}" -b {branch}` + `mkdir -p "${PROJECT_ROOT}-wt-{name}/logs"`; production код запрещён, но план/артефакты пишутся изолированно |

**КРИТИЧНО:** каждый worker получает отдельный worktree. Нельзя запускать двух worker'ов в одном worktree, в основном checkout, или с одной веткой.

**КРИТИЧНО:** orch обязан зарезервировать файлы ДО запуска. Если reserved files пересекаются — эти worker'ы идут последовательными волнами, а не параллельно.

**КРИТИЧНО:** `mkdir -p logs` в worktree ОБЯЗАТЕЛЬНО — worktree не копирует gitignored директории (`logs/`).

**КРИТИЧНО:** Untracked файлы (планы, промты) НЕ попадают в worktree. `git worktree add` копирует только tracked (committed) файлы. Если промт ссылается на untracked файл — скопировать вручную:

    # После создания worktree — копировать untracked файлы, на которые ссылается промт:
    WT="${PROJECT_ROOT}-wt-{name}"
    cp "${PROJECT_ROOT}/docs/plans/{plan}.md" "${WT}/docs/plans/" 2>/dev/null
    # Или: закоммитить план ДО создания worktree (предпочтительно)

**НИКОГДА не запускай worker в основном checkout.** Только `git worktree add` + отдельная ветка.

### Изоляция секретов

`.env` gitignored → НЕ копируется в worktree автоматически. Это правильно.

    # Для тестов — только тестовые значения:
    cp .env.test "${PROJECT_ROOT}-wt-{name}/.env"

**ЗАПРЕЩЕНО** копировать production `.env` в worktree. Worker не должен иметь доступ к prod-секретам.

## Запуск воркеров

Промты → `.codex/prompts/worker-{name}.md`. **НИКОГДА** inline.

### OpenCode worker

Единственный worker runtime в этом skill. Не указывай модель natural-language текстом внутри prompt. Если нужен конкретный исполнитель, задавай `OPENCODE_AGENT`/`OPENCODE_MODEL` в launcher или используй OpenCode agent config.
Основной режим — видимый OpenCode TUI, сразу стартующий через native `--prompt`, но `--prompt` содержит только короткий file-handoff. Полный prompt остается в файле и не попадает в process args.
`opencode run --file` используется только как fallback, если TUI `--prompt` не работает.

    PROJECT_ROOT=$(git rev-parse --show-toplevel)
    ORCH_PANE=$(tmux display-message -p '#{pane_id}')
    WT_PATH="${PROJECT_ROOT}-wt-{name}"
    PROMPT_FILE="${PROJECT_ROOT}/.codex/prompts/worker-{name}.md"

    # Primary: visible TUI with a short prompt-file handoff.
    /home/USER/.codex/skills/tmux-swarm-orchestration/scripts/launch_opencode_tui_worker.sh \
      "W-{NAME}" "$WT_PATH" "$PROMPT_FILE"

Implementation worker role:

    OPENCODE_AGENT=pr-worker \
    OPENCODE_MODEL=opencode-go/kimi-k2.6 \
    /home/USER/.codex/skills/tmux-swarm-orchestration/scripts/launch_opencode_tui_worker.sh \
      "W-{NAME}" "$WT_PATH" "$PROMPT_FILE"

PR review-fix worker role:

    OPENCODE_AGENT=pr-review-fix \
    OPENCODE_MODEL=opencode-go/deepseek-v4-pro \
    /home/USER/.codex/skills/tmux-swarm-orchestration/scripts/launch_opencode_tui_worker.sh \
      "W-{NAME}-review-fix" "$WT_PATH" "$PROMPT_FILE"

Fallback only if `opencode --prompt` is impossible:

    TMUX="" tmux new-window -t "$(tmux display-message -p '#{session_name}')" -n "W-{NAME}" -c "$WT_PATH" \
      "opencode run --file '$PROMPT_FILE' --dir '$WT_PATH' 'Execute the attached worker prompt completely. Do not stop until DONE JSON is written.' 2>&1 | tee logs/opencode-run-{name}.log; exec zsh"

Paste fallback only if both native prompt modes are impossible. Target the exact pane id and use bracketed paste:

    PANE=$(TMUX="" tmux new-window -P -F '#{pane_id}' -t "$(tmux display-message -p '#{session_name}')" -n "W-{NAME}" -c "$WT_PATH" 'opencode')
    sleep 8
    PROMPT_BUFFER="prompt-W-{NAME}-$(date +%s%N)"
    TMUX="" tmux load-buffer -b "$PROMPT_BUFFER" "$PROMPT_FILE"
    TMUX="" tmux paste-buffer -p -d -b "$PROMPT_BUFFER" -t "$PANE"
    TMUX="" tmux send-keys -t "$PANE" Enter

Worker prompt ОБЯЗАН содержать:

    ORCH_PANE={ORCH_PANE}
    WORKTREE={PROJECT_ROOT}-wt-{name}
    SIGNAL_FILE={WORKTREE}/.signals/worker-{name}.json
    BRANCH={branch_name}
    RESERVED_FILES={reserved_files}

    В конце:
    1. Запиши SIGNAL_FILE атомарно: SIGNAL_FILE.tmp → mv.
    2. Выполни:
       tmux send-keys -t "{ORCH_PANE}" "[DONE] W-{NAME} {absolute_signal_file}"
       sleep 1
       tmux send-keys -t "{ORCH_PANE}" Enter

НЕ создавай отдельное inbox-окно на каждого worker. Реальная схема: 1 окно оркестратора + N окон worker.
НЕ читай `capture-pane`, `logs/opencode-tui-*.log` и НЕ делай `opencode export` для штатного мониторинга. Читай только JSON path из `[DONE]`. Большой transcript — только при `status=failed`, missing/invalid JSON, timeout, или противоречивом отчете; даже тогда максимум 80 sanitized lines по 180 chars.

**КРИТИЧНО:**
- `TMUX=""` перед `tmux` обязателен (вложенные операции)
- default runtime = visible TUI `opencode --prompt "Read and execute /abs/prompt.md..."` в отдельном tmux window
- `opencode run --file` только fallback, если native TUI prompt неприменим
- paste fallback: только target pane id (`new-window -P -F '#{pane_id}'`) + `paste-buffer -p`
- НЕ использовать общий unnamed buffer/window-name targeting при fallback: только named buffer per worker + pane id
- launcher копирует prompt в worker worktree, пишет `.signals/launch-{name}.json` с `prompt_sha256`, `pane_id`, `pane_pid`
- raw TUI log выключен по умолчанию; включать только `OPENCODE_TUI_LOG=1` для диагностики
- не добавлять неизвестные model/profile flags; использовать только поддержанные текущим `opencode --help` флаги. Для TUI в текущем OpenCode гарантированы `--agent` и `--model`; `OPENCODE_VARIANT` launcher передает только если текущий TUI help реально содержит `--variant`.

## Сигнализация

### Файловые сигналы (основной метод)

Worker → orch через JSON-файлы в `.signals/`. **Атомарная запись** (write .tmp → mv) предотвращает partial reads:

    # Worker пишет при завершении:
    echo '{"status":"done","worker":"W-{NAME}","pr":"{url}","ts":"'$(date -Iseconds)'"}' \
      > "$SIGNAL_FILE.tmp" \
      && mv "$SIGNAL_FILE.tmp" "$SIGNAL_FILE"

    # Worker пишет при провале:
    echo '{"status":"failed","worker":"W-{NAME}","error":"{msg}","ts":"'$(date -Iseconds)'"}' \
      > "$SIGNAL_FILE.tmp" \
      && mv "$SIGNAL_FILE.tmp" "$SIGNAL_FILE"

    # Контракт C — путь к плану + execution решение:
    echo '{"status":"done","worker":"W-{NAME}","plan":"{path}","execution":"{sequential|parallel}","groups":{N},"ts":"'$(date -Iseconds)'"}' \
      > "$SIGNAL_FILE.tmp" \
      && mv "$SIGNAL_FILE.tmp" "$SIGNAL_FILE"

### OpenCode wake-up (основной метод)

Worker пишет JSON как источник истины, затем будит оркестратора короткой строкой в его pane:

    cat > "${SIGNAL_FILE}.tmp" <<'JSON'
    {"status":"done","worker":"W-{NAME}","summary":"...","ts":"..."}
    JSON
    mv "${SIGNAL_FILE}.tmp" "$SIGNAL_FILE"
    tmux send-keys -t "$ORCH_PANE" "[DONE] W-{NAME} $SIGNAL_FILE"
    sleep 1
    tmux send-keys -t "$ORCH_PANE" Enter

`tmux wait-for -S` НЕ является обязательным. Не полагайся на него как на источник истины: edge-сигнал можно пропустить, а worker может зависнуть после записи JSON. Persisted JSON + wake-up в pane достаточно.

### Orch мониторинг (event-driven через signals)

**Основной метод:** worker пишет worker-local `SIGNAL_FILE` и будит orch строкой `[DONE] W-{NAME} {absolute_signal_file}`. Orch читает JSON, сразу закрывает tmux window worker'а, затем переходит к Phase 5 по worktree/files.

`status=done` означает "готово к orch review", а не "можно merge". Финальный PASS требует orch diff review, artifact verification и локальной required verification. GitHub CI — необязательный дополнительный сигнал, если он реально доступен и релевантен.

**КРИТИЧНО:** orch обработал `.signals/` → переименовать файл (`done-*`) чтобы не обработать повторно.
**Artifact timeout:** через 5-7 минут после spawn проверь `git status --short`, expected first artifact и `.signals/worker-*.json`. Если пусто — `kill-window`, запиши feedback ledger, перезапусти exact-action prompt.

Если Phase 5 или локальная required verification падает, не переиспользуй старый `done` как PASS. Запусти review-fix loop: feedback prompt с `receiving-code-review`, исправление в той же PR branch, новый DONE JSON и повтор Phase 5.

### Чтение сигналов через context-mode

При обработке сигнала — используй context-mode для верификации (output не засоряет контекст):

    # Проверить все сигналы за один вызов:
    mcp batch_execute(commands=[
      {label: "signals", command: "find . -path '*/.signals/worker-*.json' -print -exec cat {} \\; 2>/dev/null"},
      {label: "logs", command: "tail -20 logs/worker-*.log 2>/dev/null"}
    ], queries=["worker status done or failed", "skill markers"])

    # Code review diff через context-mode (Фаза 5.0):
    mcp execute(language="shell", code="""
      cd '{WT_PATH}'
      base=$(gh pr view "{pr}" --json baseRefName --jq .baseRefName)
      git fetch origin "$base"
      git diff "origin/$base"...HEAD 2>&1
    """, intent="code review: verify changes match issue #{N}")

### Context budget guardrails

Worker logs are diagnostic-only. After valid DONE JSON, review artifacts, not transcripts:
`SIGNAL_FILE`, `.signals/launch-*.json`, PR metadata/files, `git diff --name-only`, `git diff --stat`, and fresh focused commands.

Forbidden in normal monitoring:

    ps aux
    ps -ef
    pgrep -af opencode
    tail logs/opencode-tui-*.log
    cat logs/opencode-tui-*.log

Safe process check only when needed:

    ps -o pid,ppid,etime,stat,pcpu,pmem,comm -p "$PID"

Staged PR review:

    base=$(gh pr view "{pr}" --json baseRefName --jq .baseRefName)
    git fetch origin "$base"
    git diff --name-only "origin/$base"...HEAD
    git diff --stat "origin/$base"...HEAD

Only after file-list/stat checks pass, read bounded diffs for changed files.

### tmux send-keys wake-up

Если файловые сигналы невозможны (VPS, нет общей FS):

    TMUX="" tmux send-keys -t "{ORCH_NAME}" "[DONE] W-{NAME}: PR {url}"
    TMUX="" tmux send-keys -t "{ORCH_NAME}" Enter

Для OpenCode всегда предпочитай pane id:

    TMUX="" tmux send-keys -t "$ORCH_PANE" "[DONE] W-{NAME} $SIGNAL_FILE"
    sleep 1
    TMUX="" tmux send-keys -t "$ORCH_PANE" Enter

## Таймауты

Watchdog запускается параллельно с каждым worker:

    # Запуск watchdog (сразу после запуска worker):
    ( sleep ${TIMEOUT} && \
      [ ! -f "${WT_PATH}/.signals/worker-{name}.json" ] && [ ! -f "${WT_PATH}/.signals/done-worker-{name}.json" ] && \
      echo '{"status":"timeout","worker":"W-{NAME}","ts":"'$(date -Iseconds)'"}' > "${WT_PATH}/.signals/worker-{name}.json" && \
      TMUX="" tmux send-keys -t "W-{NAME}" C-c ) &

| Контракт | Таймаут | Обоснование |
|----------|---------|-------------|
| A (TRIVIAL/CLEAR) | 15 мин (900) | Простая задача, TDD + review |
| B (план → код) | 30 мин (1800) | Выполнение плана с TDD |
| B-part (часть плана) | 20 мин (1200) | Часть плана, без PR |
| B-final (интеграция) | 30 мин (1800) | Merge + make check + локальный broad run + PR |
| C (исследование) | 20 мин (1200) | Только чтение + план |
| D (solo) | 45 мин (2700) | Полный цикл |

**Таймаут → эскалация**, не повтор. Застрявший worker = неверная классификация.

## Маркеры скиллов в логах

Workers логируют `[SKILL:*]` → `logs/worker-{name}.log`:

    echo "[SKILL:{skill_name}] $(date -Iseconds)" >> logs/worker-{name}.log

Orch проверяет (Фаза 5): `grep '\[SKILL:' logs/worker-{name}.log`

| Контракт | Мин. маркеры |
|----------|--------------|
| A | test-driven-development, requesting-code-review, verification-before-completion, finishing-a-development-branch (4) |
| B | executing-plans, test-driven-development, requesting-code-review, verification-before-completion, finishing-a-development-branch (5) |
| B-part | executing-plans, test-driven-development, requesting-code-review, verification-before-completion (4), без finishing/PR |
| C | writing-plans, verification-before-completion (2) |
| D | writing-plans, executing-plans, test-driven-development, requesting-code-review, verification-before-completion, finishing-a-development-branch (6) |
| review-fix | receiving-code-review, test-driven-development, verification-before-completion (3), push в тот же PR |

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

## Feedback ledger

После каждого run append в `${CODEX_HOME:-$HOME/.codex}/swarm-feedback/{repo}.md`: stalls, bad prompts, worker mistakes, local env blockers, and exact skill/prompt fixes.

## Двухволновой запуск (COMPLEX+)

1. **Волна 1:** Codex пишет/уточняет план и решает `execution`
2. **Волна 2:** Orch запускает OpenCode workers по плану:

### execution: sequential (по умолчанию)

    # 1 OpenCode B с полным планом:
    git worktree add "${PROJECT_ROOT}-wt-${issue}" -b "fix/${issue}-impl"
    # Запуск Контракт B → 1 PR

### execution: parallel (Codex решил)

    # Orch парсит группы из плана и запускает волнами:

    # Волна 2a: независимые группы — параллельно
    git worktree add "${PROJECT_ROOT}-wt-${issue}-grpA" -b "fix/${issue}-part-a"
    git worktree add "${PROJECT_ROOT}-wt-${issue}-grpB" -b "fix/${issue}-part-b"
    # OpenCode B-part в каждом worktree со СВОЕЙ частью плана

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

После DONE: сразу закрыть tmux window worker'а, чтобы OpenCode не держал память. После Phase 5 PASS/FAIL/timeout удалить worktree/branch.

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

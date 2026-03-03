# Инфраструктура

Механика tmux, worktree, сигналов, таймаутов, очистки.

## Идентификация оркестратора

    ORCH_NAME="ORCH-{N}"
    tmux rename-window -t "$TMUX_PANE" "$ORCH_NAME"

**КРИТИЧНО:** `display-message` без `-t "$TMUX_PANE"` → АКТИВНОЕ окно юзера, не ваше.

## Инициализация

    PROJECT_ROOT=$(git rev-parse --show-toplevel)
    mkdir -p logs .signals

## Worktree

| Контракт | Метод |
|----------|-------|
| A/B/D (код) | `git worktree add "${PROJECT_ROOT}-wt-{name}" -b {branch}` + `mkdir -p "${PROJECT_ROOT}-wt-{name}/logs"` + `uv sync --quiet` |
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

    # Sonnet (Контракт A/B) — worktree:
    TMUX="" tmux new-window -n "W-{NAME}" -c "$WT_PATH"
    sleep 3
    TMUX="" tmux send-keys -t "W-{NAME}" 'claude --model sonnet --dangerously-skip-permissions "$(cat {PROJECT_ROOT}/.claude/prompts/worker-{name}.md)"' Enter

    # Opus (Контракт C) — корень проекта:
    TMUX="" tmux new-window -n "W-{NAME}" -c "$PROJECT_ROOT"
    sleep 3
    TMUX="" tmux send-keys -t "W-{NAME}" 'claude --dangerously-skip-permissions "$(cat {PROJECT_ROOT}/.claude/prompts/worker-{name}.md)"' Enter

    # Opus Соло (Контракт D) — worktree:
    # Как Контракт C, но -c "$WT_PATH"

**КРИТИЧНО:** `sleep 3` обязателен. `--dangerously-skip-permissions` обязателен. `TMUX=""` перед `send-keys` обязателен.

**НЕ ИСПОЛЬЗОВАТЬ `| tee`** — claude CLI использует TUI (интерактивный терминал), pipe ломает рендеринг. Worker сам пишет в лог через `echo >> logs/worker-{name}.log`.

## Сигнализация

### Файловые сигналы (основной метод)

Worker → orch через JSON-файлы в `.signals/`:

    # Worker пишет при завершении:
    echo '{"status":"done","worker":"W-{NAME}","pr":"{url}","ts":"'$(date -Iseconds)'"}' \
      > {PROJECT_ROOT}/.signals/worker-{name}.json

    # Worker пишет при провале:
    echo '{"status":"failed","worker":"W-{NAME}","error":"{msg}","ts":"'$(date -Iseconds)'"}' \
      > {PROJECT_ROOT}/.signals/worker-{name}.json

    # Контракт C — вместо PR указывает путь к плану:
    echo '{"status":"done","worker":"W-{NAME}","plan":"{path}","ts":"'$(date -Iseconds)'"}' \
      > {PROJECT_ROOT}/.signals/worker-{name}.json

### Orch мониторинг

    # Вариант 1: inotifywait (мгновенный, если доступен)
    Bash(command="inotifywait -m -e create .signals/ --format '%f' 2>/dev/null | while read f; do cat '.signals/$f'; done", run_in_background=true)

    # Вариант 2: polling (универсальный, 30 сек)
    Bash(command="while true; do for f in .signals/worker-*.json; do [ -f \"$f\" ] && cat \"$f\" && mv \"$f\" \".signals/done-$(basename $f)\"; done; sleep 30; done", run_in_background=true)

**КРИТИЧНО:** orch обработал сигнал → переименовать файл (`done-*`) чтобы не обработать повторно.

### tmux send-keys (запасной метод)

Если файловые сигналы невозможны (VPS, нет общей FS):

    TMUX="" tmux send-keys -t "{ORCH_NAME}" "[DONE] W-{NAME}: PR {url}"
    TMUX="" tmux send-keys -t "{ORCH_NAME}" Enter

## Таймауты

Watchdog запускается параллельно с каждым worker:

    # Запуск watchdog (сразу после запуска worker):
    ( sleep ${TIMEOUT} && \
      [ ! -f .signals/worker-{name}.json ] && [ ! -f .signals/done-worker-{name}.json ] && \
      echo '{"status":"timeout","worker":"W-{NAME}","ts":"'$(date -Iseconds)'"}' > .signals/worker-{name}.json && \
      TMUX="" tmux send-keys -t "W-{NAME}" C-c ) &

| Контракт | Таймаут | Обоснование |
|----------|---------|-------------|
| A (TRIVIAL/CLEAR) | 15 мин (900) | Простая задача, TDD + review |
| B (план → код) | 30 мин (1800) | Выполнение плана с TDD |
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

**КРИТИЧНО:** каждый part-worker создаёт свои коммиты и push'ит, но НЕ создаёт PR. Только финальный worker создаёт PR.

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

# Infrastructure Reference

tmux mechanics, spawn, merge, VPS for tmux-swarm-orchestration.

## ORCH Identity (Phase 5.1)

    # ОДИН вызов — discover + generate + rename + save:
    ORCH_ID=$(uv run python scripts/tmux_orch_identity.py init)
    # → ORCH-a1b2c3d4 (stdout) + .claude/orch-identity.json (state)

    # Позже:
    uv run python scripts/tmux_orch_identity.py get              # → ORCH-a1b2c3d4

Хелпер решает tmux-баги:
- `$TMUX_PANE` + `-t` для определения СВОЕГО окна (не активного юзера)
- `TMUX=""` + `-t session:window` при rename (не переименовывает чужое окно)
- `automatic-rename off` (tmux не перезапишет имя по процессу node)

**Каждый запуск** = уникальное имя. Несколько оркестраторов не конфликтуют.

**НЕ используй хелпер для webhook/signal** — `worker-notify`/`worker-enter` команды deprecated.
Signal через `tmux wait-for` (см. секцию Signal ниже).

## Worktree Setup (Phase 5.2)

    PROJECT_ROOT=$(git rev-parse --show-toplevel)
    mkdir -p logs

| Когда | Метод |
|-------|-------|
| **tmux headless workers** | `git worktree add` (РУЧНОЙ) — **ВСЕГДА** для tmux workers |
| Интерактивные сессии пользователя | `claude --worktree` (автоматический) — OK для user sessions |

**CRITICAL: НЕ используй `claude --worktree` для tmux workers!**
- `claude --worktree` удаляет worktree + branch при headless exit
- Workers завершаются → worktree удаляется → коммиты ПОТЕРЯНЫ
- Используй ТОЛЬКО `git worktree add` (ручной) для tmux workers

**Ручной** (`git worktree add`):

    git checkout -b {feature-branch}
    git worktree add "${PROJECT_ROOT}-wt-{name1}" -b {feature-branch}-{name1}
    git worktree add "${PROJECT_ROOT}-wt-{name2}" -b {feature-branch}-{name2}
    (cd "${PROJECT_ROOT}-wt-{name1}" && uv sync --quiet)
    (cd "${PROJECT_ROOT}-wt-{name2}" && uv sync --quiet)

## Spawn Commands (Phase 5.4)

Промты: `.claude/prompts/worker-{name}.md` — **НИКОГДА** inline в send-keys. Без бэктиков в промт-файлах.

**Worktree (ЕДИНСТВЕННЫЙ метод для tmux workers):**

    WT_PATH="${PROJECT_ROOT}-wt-{name}"
    TMUX="" tmux new-window -t "$SESSION" -n "W-{NAME}" -c "$WT_PATH"
    sleep 3
    TMUX="" tmux send-keys -t "$SESSION:W-{NAME}" "claude --model {model} --dangerously-skip-permissions \"\$(cat ${PROJECT_ROOT}/.claude/prompts/worker-{name}.md)\"" Enter

**CRITICAL:** `sleep 3` (не 1) — shell prompt должен появиться до send-keys.

**Сразу после spawn — wait-for в background:**

    Bash(
        command='TMUX="" tmux wait-for worker-{name}-done && echo "W-{NAME} COMPLETE"',
        run_in_background=True
    )

Для N workers — N параллельных wait-for. Все `<task-notification>` придут при завершении.

## Signal: tmux wait-for (Phase 4→5 bridge)

**Механизм:** true push IPC через tmux. 0 polling, 0 tokens, instant notification.

**Orch сторона** (после каждого spawn):

    # Блокирующий wait в background — Claude получит <task-notification> при сигнале
    Bash(
        command='TMUX="" tmux wait-for worker-{name}-done && echo "W-{NAME} COMPLETE"',
        run_in_background=True
    )

**Worker сторона** (в конце работы, встроен в worker-contract.md):

    # Успех:
    TMUX="" tmux wait-for -S worker-{name}-done
    # Неудача:
    TMUX="" tmux wait-for -S worker-{name}-done

Worker отправляет "FAILED: {reason}" в лог при 3 неудачах подряд.
Orch получает signal → читает log tail → решает: respawn / skip / manual fix.

**Почему НЕ send-keys webhook:**
- Claude Code не читает stdin из tmux (send-keys → терминал, но не в Claude)
- orch-identity.json может быть stale (другая сессия перезаписала)
- tmux wait-for = kernel-level IPC, гарантированная доставка

## Cleanup после signal

    TMUX="" tmux kill-window -t "$SESSION:W-{NAME}" 2>/dev/null

## Merge + Cleanup

    git checkout {feature-branch}
    git merge {feature-branch}-{name1} --no-edit
    git merge {feature-branch}-{name2} --no-edit
    git worktree remove "${PROJECT_ROOT}-wt-{name1}"
    git worktree remove "${PROJECT_ROOT}-wt-{name2}"
    git branch -d {feature-branch}-{name1} {feature-branch}-{name2}

При конфликтах: resolve вручную или спавни Claude worker.

## Железное правило

Любая работа кроме inline fix → `claude --model {model} --dangerously-skip-permissions "$(cat prompt.md)"`.
Bare shell, ручной pytest, дебаг после merge — через worker. Баг после merge = fix-worker (Sonnet $3), НЕ оркестратор (Opus $15).

## tmux Safety

- НИКОГДА `tmux new-session` (перезаписывает сокет, отключает юзера)
- ВСЕГДА `TMUX=""` префикс (вложенные операции)
- ВСЕГДА хелпер для identity (`display-message` без `-t $TMUX_PANE` = баг)
- Сокет сломался: `pkill -USR1 tmux`

## Environment

- tmux 3.4 WSL2 (/usr/bin/tmux), сессия `claude`
- Claude Code внутри tmux ($TMUX задан) → все команды с `TMUX=""`

## VPS Remote Execution

    SESSION=$(TMUX="" tmux list-sessions -F "#{session_name}" | head -1)
    TMUX="" tmux new-window -t "$SESSION" -n "W-VPS"
    TMUX="" tmux send-keys -t "$SESSION:W-VPS" 'ssh vps' Enter
    sleep 2
    TMUX="" tmux send-keys -t "$SESSION:W-VPS" 'cd /opt/rag-fresh && {command} 2>&1 | tee logs/{name}.log; echo "[COMPLETE]"' Enter

| Задача | Команда |
|--------|---------|
| Docker build | docker compose -f docker-compose.vps.yml build --no-cache {service} |
| Deploy | docker compose -f docker-compose.vps.yml up -d |
| Логи | docker logs vps-{service} --tail 100 |
| Рестарт | docker compose -f docker-compose.vps.yml restart {service} |

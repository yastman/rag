---
name: tmux-swarm-orchestration
description: Use when executing multiple independent tasks in parallel via tmux workers OR running heavy commands on VPS through user's terminal. Triggers on "parallel workers", "swarm", "spawn-claude", "tmux воркеры", "VPS команда", "терминал #3", "тяжёлая команда".
---

# tmux Swarm Orchestration

Orchestrate parallel Claude workers in tmux windows with auto-monitoring.

**Core principle:** Workers do work, orchestrator coordinates and validates.

## When to Use

- 3+ independent tasks (don't share files)
- Plan with parallelizable milestones
- Need visibility into worker progress

**Don't use:** dependent tasks, same files, tight coordination needed.

## Workflow

```
1. mkdir -p logs && echo $TMUX
2. Create worktrees: git worktree add .worktrees/milestone-a -b milestone/a main
3. Create WINDOWS (not sessions): tmux new-window -n "W-A" -c /path/to/worktree
4. Spawn workers with Context7 (see template below)
5. Start auto-monitor: nohup ./monitor-workers.sh > logs/monitor.log 2>&1 &
6. When all [COMPLETE]: /verification-before-completion → commit → push
```

## Worker Spawn Template

```bash
tmux send-keys -t "W-A" "claude --dangerously-skip-permissions 'W-A: {description}.

ПЛАН: {path}
ЗАДАЧИ: {milestone}

⚠️ BEST PRACTICES 2026:
1. ПЕРЕД реализацией внешних API используй Context7:
   - mcp__context7__resolve-library-id для {library}
   - mcp__context7__query-docs для актуальной документации
2. НЕ используй устаревшие паттерны — только актуальные данные 2026
3. ТЕСТЫ — только свои: pytest tests/unit/test_{module}.py -v
   НЕ запускай все 1000+ тестов. Используй --lf для упавших.

SKILLS: superpowers:executing-plans, superpowers:verification-before-completion

ЛОГИРОВАНИЕ в {absolute_path}/logs/worker-a.log:
[START] timestamp Task
[DONE] timestamp Task
[COMPLETE] timestamp Worker finished

НЕ делай git commit.'" Enter
```

## Context7 Lookups

| Task | Library |
|------|---------|
| Langfuse | langfuse → @observe |
| Qdrant | qdrant-client → BinaryQuantization |
| DeepEval | deepeval → metrics API |
| Loki | grafana loki → config |

## Auto-Monitor

Create `scripts/monitor-workers.sh`, edit WINDOW_MAP:

```bash
#!/bin/bash
declare -A WINDOW_MAP=(["worker-a"]="W-A" ["worker-b"]="W-B")
while true; do
  for k in "${!WINDOW_MAP[@]}"; do
    grep -q '\[COMPLETE\]' "logs/${k}.log" 2>/dev/null && tmux kill-window -t "${WINDOW_MAP[$k]}" 2>/dev/null
  done
  sleep 30
done
```

Run: `nohup ./scripts/monitor-workers.sh > logs/monitor.log 2>&1 &`

## Red Flags — STOP

- Using `tmux new-session` (use `new-window`)
- Missing Context7 in prompt
- Relative log paths
- No auto-monitor
- "I'll check manually"
- Missing "НЕ делай git commit"
- Running `pytest tests/` (all tests) instead of specific module

## Rationalization Table

| Excuse | Reality |
|--------|---------|
| "Workers know APIs" | APIs change. Context7 = 10 seconds. |
| "I'll monitor manually" | You'll forget. |
| "Sessions are fine" | No tabs visible. |
| "Relative paths work" | Break on cd. |
| "Context7 is overkill" | Outdated API = wasted time. |
| "Run all tests to be safe" | 25 min wasted. Test your module only. |

## VPS Remote Execution

**Паттерн:** Сам создаю tmux window → ssh на VPS → команда.

**Принцип:** Запустил → пользователь видит → жду feedback (не трачу токены на polling).

### Workflow

```bash
# 1. Создаю новое окно W-VPS
tmux new-window -n "W-VPS"

# 2. SSH на VPS (алиас из ~/.ssh/config)
tmux send-keys -t "W-VPS" 'ssh vps' Enter

# 3. Жду подключения (~2 сек), потом команда
sleep 2
tmux send-keys -t "W-VPS" 'cd /opt/rag-fresh && docker compose -f docker-compose.vps.yml up -d 2>&1 | tee logs/deploy.log; echo "[COMPLETE]"' Enter
```

### One-Liner Template

```bash
tmux new-window -n "W-VPS" && sleep 1 && tmux send-keys -t "W-VPS" 'ssh vps' Enter && sleep 2 && tmux send-keys -t "W-VPS" 'cd /opt/rag-fresh && {command} 2>&1 | tee logs/{name}.log; echo "[COMPLETE]"' Enter
```

### Типовые команды

| Task | Command |
|------|---------|
| Docker build | `docker compose -f docker-compose.vps.yml build --no-cache {service}` |
| Deploy | `docker compose -f docker-compose.vps.yml up -d` |
| Logs | `docker logs vps-{service} --tail 100` |
| Restart | `docker compose -f docker-compose.vps.yml restart {service}` |
| Ingestion | `docker compose -f docker-compose.vps.yml --profile ingest up -d ingestion` |

### После запуска

```
1. Пользователь переключается на W-VPS (видит вывод)
2. Я ЖДУ — не polling'у логи, не трачу токены
3. Пользователь говорит: "[COMPLETE]" или "ошибка: ..."
4. Я продолжаю работу
```

### Red Flags — VPS

- Запускаю через `run_in_background: true` вместо tmux window
- Polling логов каждые 30 секунд
- Не жду feedback, сразу продолжаю
- Забыл `echo "[COMPLETE]"` в конце
- Отправляю команду без `ssh vps` сначала

## Checklist

**Before:**
- [ ] `mkdir -p logs`, in tmux
- [ ] Worktrees created
- [ ] Context7 lookups identified

**Prompt includes:**
- [ ] Context7 instructions
- [ ] Absolute log path
- [ ] "НЕ делай git commit"

**After all [COMPLETE]:**
- [ ] /verification-before-completion
- [ ] make test && make check
- [ ] Single commit, push

**VPS Remote:**
- [ ] Терминал #3 SSH на VPS
- [ ] Команда через `tmux send-keys -t claude:3`
- [ ] `| tee logs/{name}.log; echo "[COMPLETE]"`
- [ ] Жду feedback от пользователя

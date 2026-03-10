---
description: "Peon-ping sound notification management"
---

# Peon-Ping: быстрое управление

## Конфиг

Файл: `~/.claude/hooks/peon-ping/config.json`

| Действие | Как |
|----------|-----|
| Выкл звук | `"enabled": false` в config.json |
| Вкл звук | `"enabled": true` в config.json |
| Только попапы выкл | `"desktop_notifications": false` |

## Хуки в settings.json

Хуки peon-ping — записи в `~/.claude/settings.json` → `hooks.*` где command содержит `peon-ping/peon.sh` или `peon-ping/scripts/`.

### Удалить все хуки

Убрать из settings.json все entries с `peon-ping` в command. Оставить остальные хуки (claudio, grepai-ensure, context-mode).

Затронутые события: Stop, SessionStart, SessionEnd, SubagentStart, UserPromptSubmit, Notification, PermissionRequest, PostToolUseFailure, PreCompact.

### Восстановить все хуки

Добавить в settings.json → hooks:

```json
"Stop": [{ "matcher": "", "hooks": [{ "type": "command", "command": "~/.claude/hooks/peon-ping/peon.sh", "timeout": 10, "async": true }] }],
"SessionStart": [{ "matcher": "", "hooks": [{ "type": "command", "command": "~/.claude/hooks/peon-ping/peon.sh", "timeout": 10 }] }],
"SessionEnd": [{ "matcher": "", "hooks": [{ "type": "command", "command": "~/.claude/hooks/peon-ping/peon.sh", "timeout": 10, "async": true }] }],
"SubagentStart": [{ "matcher": "", "hooks": [{ "type": "command", "command": "~/.claude/hooks/peon-ping/peon.sh", "timeout": 10, "async": true }] }],
"UserPromptSubmit": [
  { "matcher": "", "hooks": [{ "type": "command", "command": "~/.claude/hooks/peon-ping/peon.sh", "timeout": 10, "async": true }] },
  { "matcher": "", "hooks": [
    { "type": "command", "command": "~/.claude/hooks/peon-ping/scripts/hook-handle-use.sh", "timeout": 5 },
    { "type": "command", "command": "~/.claude/hooks/peon-ping/scripts/hook-handle-rename.sh", "timeout": 5 }
  ]}
],
"Notification": [{ "matcher": "", "hooks": [{ "type": "command", "command": "~/.claude/hooks/peon-ping/peon.sh", "timeout": 10, "async": true }] }],
"PermissionRequest": [{ "matcher": "", "hooks": [{ "type": "command", "command": "~/.claude/hooks/peon-ping/peon.sh", "timeout": 10, "async": true }] }],
"PostToolUseFailure": [{ "matcher": "Bash", "hooks": [{ "type": "command", "command": "~/.claude/hooks/peon-ping/peon.sh", "timeout": 10, "async": true }] }],
"PreCompact": [{ "matcher": "", "hooks": [{ "type": "command", "command": "~/.claude/hooks/peon-ping/peon.sh", "timeout": 10, "async": true }] }]
```

**Важно:** не затирать существующие хуки (claudio в Stop, grepai-ensure в SessionStart) — добавлять peon-ping записи в массивы рядом с ними.

## Полное отключение (звук + хуки)

1. `"enabled": false` в `~/.claude/hooks/peon-ping/config.json`
2. Удалить все peon-ping entries из `~/.claude/settings.json` (см. выше)

## Полное включение (звук + хуки)

1. `"enabled": true` в `~/.claude/hooks/peon-ping/config.json`
2. Восстановить хуки в `~/.claude/settings.json` (см. выше)

## Быстрые команды

- `/peon-ping-toggle` — вкл/выкл звук (меняет enabled в config.json)
- `/peon-ping-config` — тонкая настройка (громкость, категории, попапы)
- "убери хуки peon-ping" / "верни хуки peon-ping" — ручное редактирование settings.json
- "выкл peon-ping полностью" — и config.json, и settings.json
- "вкл peon-ping полностью" — восстановить всё

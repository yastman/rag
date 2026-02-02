# Shared Task List в Claude Code

Руководство по использованию общего списка задач между несколькими терминалами Claude Code.

## Быстрый старт

```bash
# Все терминалы должны использовать одинаковый ID
export CLAUDE_CODE_TASK_LIST_ID=my-project
claude
```

## Концепция

```
~/.claude/tasks/<TASK_LIST_ID>/
            │
            ▼
    ┌───────────────┐
    │  Общие файлы  │
    │   задач       │
    └───────────────┘
      ▲    ▲    ▲
      │    │    │
      │    │    └─── Воркер 2
      │    └──────── Воркер 1
      └───────────── Оркестратор
```

## Настройка

### Вариант 1: Export в терминале

```bash
# Терминал 1 (оркестратор)
export CLAUDE_CODE_TASK_LIST_ID=feature-auth
claude

# Терминал 2 (воркер)
export CLAUDE_CODE_TASK_LIST_ID=feature-auth
claude
```

### Вариант 2: Inline при запуске

```bash
CLAUDE_CODE_TASK_LIST_ID=feature-auth claude
```

### Вариант 3: В .bashrc/.zshrc (для постоянного проекта)

```bash
# ~/.bashrc или ~/.zshrc
export CLAUDE_CODE_TASK_LIST_ID=rag-fresh
```

## Роли и workflow

### Оркестратор

```
1. Создаёт задачи: TaskCreate(subject, description)
2. Мониторит статусы: TaskList()
3. Координирует зависимости: TaskUpdate(addBlockedBy, addBlocks)
```

### Воркер

```
1. Смотрит доступные задачи: TaskList()
2. Берёт задачу в работу: TaskUpdate(taskId, status: "in_progress")
3. Выполняет работу
4. Завершает: TaskUpdate(taskId, status: "completed")
```

## Команды

| Действие | Инструмент |
|----------|-----------|
| Создать задачу | `TaskCreate` |
| Список всех задач | `TaskList` |
| Детали задачи | `TaskGet(taskId)` |
| Обновить статус | `TaskUpdate(taskId, status)` |
| Toggle UI | `Ctrl+T` |

## Статусы задач

```
pending → in_progress → completed
                     ↘ deleted
```

## Зависимости между задачами

```python
# Задача 2 блокируется задачей 1
TaskUpdate(taskId="2", addBlockedBy=["1"])

# Задача 1 блокирует задачи 2 и 3
TaskUpdate(taskId="1", addBlocks=["2", "3"])
```

## Пример сессии

### Оркестратор создаёт план

```
> Создай задачи для реализации auth системы

TaskCreate:
  - "Создать модель User" (id: 1)
  - "Реализовать JWT токены" (id: 2, blockedBy: 1)
  - "Добавить middleware auth" (id: 3, blockedBy: 2)
  - "Написать тесты" (id: 4, blockedBy: 3)
```

### Воркер 1 берёт задачу

```
> Покажи задачи и возьми первую доступную

TaskList → видит задачу 1 (pending, не заблокирована)
TaskUpdate(taskId="1", status="in_progress")
... работает ...
TaskUpdate(taskId="1", status="completed")
```

### Оркестратор видит прогресс

```
> Покажи статус задач

TaskList:
  [✓] 1. Создать модель User (completed)
  [ ] 2. Реализовать JWT токены (pending, unblocked now!)
  [ ] 3. Добавить middleware auth (blocked by 2)
  [ ] 4. Написать тесты (blocked by 3)
```

## Ограничения

| Аспект | Описание |
|--------|----------|
| **Синхронизация** | File-based, не real-time push |
| **Конфликты** | Возможны при одновременной записи |
| **Уведомления** | Нет автоматических, нужен poll через TaskList |

## Продвинутая координация (tmux hooks)

Для real-time уведомлений между агентами используй multi-agent swarm:

```markdown
# .claude/multi-agent-swarm.local.md
---
agent_name: auth-worker
task_number: 1
coordinator_session: main-orchestrator
enabled: true
dependencies: []
---

# Current Task
Implement user authentication
```

Hook в `.claude/hooks/post-tool-use.sh` может отправлять уведомления через tmux.

## Откат к старой системе (TodoWrite)

```bash
CLAUDE_CODE_ENABLE_TASKS=false claude
```

## См. также

- `.claude/rules/skills.md` — workflow для планов и выполнения
- `docs/PARALLEL-WORKERS.md` — параллельные воркеры

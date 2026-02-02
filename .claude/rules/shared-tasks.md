***REMOVED*** Shared Task List в Claude Code

Руководство по использованию общего списка задач между несколькими терминалами Claude Code.

***REMOVED******REMOVED*** Быстрый старт

```bash
***REMOVED*** Все терминалы должны использовать одинаковый ID
export CLAUDE_CODE_TASK_LIST_ID=my-project
claude
```

***REMOVED******REMOVED*** Концепция

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

***REMOVED******REMOVED*** Настройка

***REMOVED******REMOVED******REMOVED*** Вариант 1: Export в терминале

```bash
***REMOVED*** Терминал 1 (оркестратор)
export CLAUDE_CODE_TASK_LIST_ID=feature-auth
claude

***REMOVED*** Терминал 2 (воркер)
export CLAUDE_CODE_TASK_LIST_ID=feature-auth
claude
```

***REMOVED******REMOVED******REMOVED*** Вариант 2: Inline при запуске

```bash
CLAUDE_CODE_TASK_LIST_ID=feature-auth claude
```

***REMOVED******REMOVED******REMOVED*** Вариант 3: В .bashrc/.zshrc (для постоянного проекта)

```bash
***REMOVED*** ~/.bashrc или ~/.zshrc
export CLAUDE_CODE_TASK_LIST_ID=rag-fresh
```

***REMOVED******REMOVED*** Роли и workflow

***REMOVED******REMOVED******REMOVED*** Оркестратор

```
1. Создаёт задачи: TaskCreate(subject, description)
2. Мониторит статусы: TaskList()
3. Координирует зависимости: TaskUpdate(addBlockedBy, addBlocks)
```

***REMOVED******REMOVED******REMOVED*** Воркер

```
1. Смотрит доступные задачи: TaskList()
2. Берёт задачу в работу: TaskUpdate(taskId, status: "in_progress")
3. Выполняет работу
4. Завершает: TaskUpdate(taskId, status: "completed")
```

***REMOVED******REMOVED*** Команды

| Действие | Инструмент |
|----------|-----------|
| Создать задачу | `TaskCreate` |
| Список всех задач | `TaskList` |
| Детали задачи | `TaskGet(taskId)` |
| Обновить статус | `TaskUpdate(taskId, status)` |
| Toggle UI | `Ctrl+T` |

***REMOVED******REMOVED*** Статусы задач

```
pending → in_progress → completed
                     ↘ deleted
```

***REMOVED******REMOVED*** Зависимости между задачами

```python
***REMOVED*** Задача 2 блокируется задачей 1
TaskUpdate(taskId="2", addBlockedBy=["1"])

***REMOVED*** Задача 1 блокирует задачи 2 и 3
TaskUpdate(taskId="1", addBlocks=["2", "3"])
```

***REMOVED******REMOVED*** Пример сессии

***REMOVED******REMOVED******REMOVED*** Оркестратор создаёт план

```
> Создай задачи для реализации auth системы

TaskCreate:
  - "Создать модель User" (id: 1)
  - "Реализовать JWT токены" (id: 2, blockedBy: 1)
  - "Добавить middleware auth" (id: 3, blockedBy: 2)
  - "Написать тесты" (id: 4, blockedBy: 3)
```

***REMOVED******REMOVED******REMOVED*** Воркер 1 берёт задачу

```
> Покажи задачи и возьми первую доступную

TaskList → видит задачу 1 (pending, не заблокирована)
TaskUpdate(taskId="1", status="in_progress")
... работает ...
TaskUpdate(taskId="1", status="completed")
```

***REMOVED******REMOVED******REMOVED*** Оркестратор видит прогресс

```
> Покажи статус задач

TaskList:
  [✓] 1. Создать модель User (completed)
  [ ] 2. Реализовать JWT токены (pending, unblocked now!)
  [ ] 3. Добавить middleware auth (blocked by 2)
  [ ] 4. Написать тесты (blocked by 3)
```

***REMOVED******REMOVED*** Ограничения

| Аспект | Описание |
|--------|----------|
| **Синхронизация** | File-based, не real-time push |
| **Конфликты** | Возможны при одновременной записи |
| **Уведомления** | Нет автоматических, нужен poll через TaskList |

***REMOVED******REMOVED*** Продвинутая координация (tmux hooks)

Для real-time уведомлений между агентами используй multi-agent swarm:

```markdown
***REMOVED*** .claude/multi-agent-swarm.local.md
---
agent_name: auth-worker
task_number: 1
coordinator_session: main-orchestrator
enabled: true
dependencies: []
---

***REMOVED*** Current Task
Implement user authentication
```

Hook в `.claude/hooks/post-tool-use.sh` может отправлять уведомления через tmux.

***REMOVED******REMOVED*** Откат к старой системе (TodoWrite)

```bash
CLAUDE_CODE_ENABLE_TASKS=false claude
```

***REMOVED******REMOVED*** См. также

- `.claude/rules/skills.md` — workflow для планов и выполнения
- `docs/PARALLEL-WORKERS.md` — параллельные воркеры

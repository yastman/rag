# Parallel Claude Workers (tmux + spawn-claude)

Запуск нескольких Claude-агентов одновременно для ускорения работы.

## Архитектура

```
tmux session "claude"
├── Окно 1: Основной Claude (оркестратор)
│   └── Создаёт план и запускает воркеров через spawn-claude
├── Окно 2: Worker 1 (независимая Claude сессия)
├── Окно 3: Worker 2 (независимая Claude сессия)
├── Окно 4: Worker 3 (независимая Claude сессия)
└── Окно 5+: Дополнительные воркеры по мере необходимости
```

**Результат:** N Claude-агентов работают **параллельно**, каждый на своей задаче, в одной tmux сессии.

## Быстрый старт (3 шага)

**1. Открыть tmux сессию в проекте**
```bash
cd /mnt/c/Users/user/Documents/Сайты/rag-fresh
tmux new -s claude
# Или через WezTerm (Ctrl+Shift+M) → выбрать проект
```

**2. Запустить основную Claude сессию**
```bash
claude
```

**3. Из Claude запустить воркеров**
```bash
spawn-claude "W1: Task description" "$(pwd)"
spawn-claude "W2: Another task" "$(pwd)"
spawn-claude "W3: Third task" "$(pwd)"
```

## Переключение между воркерами (tmux)

| Комбо | Действие |
|-------|----------|
| `Ctrl+A, 1` | Основной Claude (оркестратор) |
| `Ctrl+A, 2/3/4` | Worker 1/2/3 |
| `Ctrl+A, n/p` | Следующее/предыдущее окно |
| `Ctrl+A, w` | Список всех окон |
| `Ctrl+A, d` | Отсоединиться (session stays) |

## Синтаксис spawn-claude

```bash
spawn-claude "ПРОМПТ" "ПУТЬ"
```

| Параметр | Значение | Пример |
|----------|----------|--------|
| **ПРОМПТ** | Задача для Claude | `"W1: Implement feature X"` |
| **ПУТЬ** | Путь к проекту | `"$(pwd)"` или абсолютный путь |

**ОБЯЗАТЕЛЬНО:** Всегда передавай путь к проекту вторым аргументом.

## Правила параллелизации (ВАЖНО)

**Главный принцип:** 1 воркер = 1 набор независимых файлов. Никогда не делить один файл между воркерами.

| Правило | Хорошо | Плохо |
|---------|--------|-------|
| 1 воркер = 1 модуль | W1: cache.py, W2: qdrant.py | W1: cache.py строки 1-100, W2: cache.py строки 101-200 |
| Группируй мелкое | W1: metrics + otel + eval | W1: metrics, W2: otel, W3: eval (оверхед) |
| Тесты с кодом | W1: auth.py + test_auth.py | W1: auth.py, W2: test_auth.py |
| Общий файл — только чтение | Все читают план | Все пишут в один файл |

## Шаблон промпта для воркера

```bash
spawn-claude "W{N}: {Краткое описание задачи}.

REQUIRED SKILLS:
- superpowers:executing-plans
- superpowers:verification-before-completion

План: docs/plans/YYYY-MM-DD-task.md
Задачи: Task N

НЕ ДЕЛАЙ git commit - коммиты делает оркестратор" "$(pwd)"
```

**Важно:**
- Не дублируй содержимое плана в промпте — воркер сам прочитает
- Указывай только номера задач, не пересказывай шаги
- Скилл `executing-plans` обеспечит правильное выполнение

## Пример: 4 воркера

```bash
PROJECT="/mnt/c/Users/user/Documents/Сайты/rag-fresh"

spawn-claude "W1: Task 3 - Test Scenarios.
REQUIRED SKILLS:
- superpowers:executing-plans
- superpowers:verification-before-completion
План: docs/plans/2026-01-27-e2e-bot-testing-impl.md
Задача: Task 3
НЕ ДЕЛАЙ git commit" $PROJECT

spawn-claude "W2: Task 4 - Telethon Client.
REQUIRED SKILLS:
- superpowers:executing-plans
- superpowers:verification-before-completion
План: docs/plans/2026-01-27-e2e-bot-testing-impl.md
Задача: Task 4
НЕ ДЕЛАЙ git commit" $PROJECT
```

## Короткий синтаксис для оркестратора

Вместо длинных инструкций пиши:

```
/parallel docs/plans/2026-01-28-feature.md
W1: 1,2,5
W2: 3,4
```

**Claude понимает:**
- Прочитать план
- Запустить `spawn-claude` для каждого воркера с правильными скиллами
- Я (Claude) — оркестратор: не делаю задачи сам, только коммичу после воркеров
- Воркеры НЕ делают коммиты

## Мониторинг прогресса

```bash
# git log (обновляется каждые 2 сек)
watch -n 2 "git log --oneline -10"

# Какие файлы изменены
git diff --name-only HEAD~5

# Финальная проверка
. venv/bin/activate && pytest tests/unit/ -q
```

## Обработка ошибок

| Проблема | Решение |
|----------|---------|
| "Not inside tmux session" | `Ctrl+Shift+M` (войти в tmux) или `tmux new -s claude` |
| Worker зависает | `Ctrl+A, {номер}` → `Ctrl+C` → `claude` |
| Конфликт в git | `git status` → `git add .` → `git commit -m "Merge workers"` |

## Шпаргалка tmux

| Комбо | Действие |
|-------|----------|
| `Ctrl+A, c` | Новое окно |
| `Ctrl+A, n/p` | Следующее/предыдущее |
| `Ctrl+A, 1/2/3` | Перейти на окно |
| `Ctrl+A, w` | Список окон |
| `Ctrl+A, d` | Отсоединиться (session stays) |
| `Ctrl+A, \|` | Вертикальный сплит |
| `Ctrl+A, -` | Горизонтальный сплит |

## Когда использовать

**Используй:** много независимых задач (3+), каждому свои файлы, план готов

**Не используй:** зависимые задачи, один файл для всех, нужна координация

**Расположение скрипта:** `/mnt/c/Users/user/bin/spawn-claude`

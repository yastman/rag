# Documentation Restructure Design

**Date:** 2026-01-21
**Status:** Approved
**Author:** Claude Code + User

---

## Overview

Реструктуризация документации проекта Contextual RAG по фреймворку Diátaxis с добавлением:
- Трекинга задач (active/todo/done)
- Статуса проекта (local vs production)
- Контекста для Claude Code

---

## Current State (Проблемы)

### 1. Дублирование
- README.md в docs/ и корне перекрываются на ~60%
- QUICK_START.md и docs/guides/QUICK_START.md — разные версии
- SETUP.md существует в двух местах

### 2. Устаревшие версии
- Разброс версий: 2.0.1 - 2.4.0 в разных файлах
- Даты: от 2024-10-29 до 2025-11-05

### 3. Смешение языков
- PIPELINE_OVERVIEW.md на русском
- API_REFERENCE.md на английском
- Нет консистентности

### 4. Отсутствующее
- Нет единого Getting Started
- Нет Troubleshooting guide
- Нет ясности local vs production

### 5. Организация
- 16 файлов в корне — слишком много
- INDEX.md ссылается на несуществующие файлы

---

## Target Structure (Целевая структура)

```
docs/
│
├── index.md                        ← Главная навигация
│
├── status/                         ← СТАТУС ПРОЕКТА
│   ├── current-state.md            ← Что работает (local ✓ / prod ?)
│   └── local-vs-production.md      ← Чеклист: что нужно для prod
│
├── tasks/                          ← ЗАДАЧИ
│   ├── active.md                   ← В работе сейчас
│   ├── todo.md                     ← Бэклог
│   └── done.md                     ← Выполнено
│
├── context/                        ← ДЛЯ CLAUDE CODE
│   ├── project-brief.md            ← Краткий контекст проекта
│   └── coding-standards.md         ← Стандарты кода
│
├── tutorials/                      ← ОБУЧЕНИЕ (для новичков)
│   ├── first-search.md             ← Первый поиск за 5 мин
│   └── adding-documents.md         ← Добавление документов
│
├── how-to/                         ← КАК СДЕЛАТЬ (конкретные задачи)
│   ├── setup-local.md              ← Настройка локально
│   ├── deploy-production.md        ← Деплой на VPS
│   ├── change-llm-provider.md      ← Смена LLM
│   └── troubleshooting.md          ← Решение проблем
│
├── reference/                      ← СПРАВОЧНИК
│   ├── api.md                      ← API Reference
│   ├── configuration.md            ← Все параметры
│   └── cli-commands.md             ← Команды
│
├── explanation/                    ← ПОНИМАНИЕ (почему так)
│   ├── architecture.md             ← Архитектура системы
│   └── hybrid-search.md            ← RRF vs DBSF
│
└── archive/                        ← Устаревшее
```

---

## Diátaxis Framework

| Категория | Цель | Формат | Аудитория |
|-----------|------|--------|-----------|
| **tutorials/** | Обучение | Пошаговые инструкции | Новички |
| **how-to/** | Решение задач | Рецепты | Опытные |
| **reference/** | Информация | Сухой справочник | Все |
| **explanation/** | Понимание | Концепции | Архитекторы |

---

## Additional Sections

### status/ — Статус проекта
- **current-state.md**: Что работает локально, что на проде
- **local-vs-production.md**: Чеклист готовности к продакшену

### tasks/ — Трекинг задач
- **active.md**: Задачи в работе сейчас
- **todo.md**: Бэклог (что нужно сделать)
- **done.md**: Выполненные задачи (история)

### context/ — Для Claude Code
- **project-brief.md**: Краткий контекст проекта для AI
- **coding-standards.md**: Стандарты кода и паттерны

---

## Migration Plan

### Phase 1: Создание структуры
1. Создать папки: status/, tasks/, context/, tutorials/, how-to/, reference/, explanation/
2. Создать index.md с навигацией

### Phase 2: Критические файлы
1. status/current-state.md — статус компонентов
2. status/local-vs-production.md — чеклист для прода
3. tasks/active.md, todo.md, done.md — задачи

### Phase 3: Миграция контента
1. Объединить QUICK_START файлы → tutorials/first-search.md
2. Объединить ARCHITECTURE файлы → explanation/architecture.md
3. Обновить API_REFERENCE → reference/api.md
4. Создать how-to/ гайды из существующих

### Phase 4: Очистка
1. Переместить устаревшее в archive/
2. Удалить дубликаты
3. Обновить ссылки

### Phase 5: Финализация
1. Обновить корневой README.md
2. Обновить .claude.md
3. Коммит и проверка

---

## Files to Create

| File | Priority | Source |
|------|----------|--------|
| docs/index.md | P0 | New |
| docs/status/current-state.md | P0 | New |
| docs/status/local-vs-production.md | P0 | New |
| docs/tasks/active.md | P0 | ROADMAP.md + TODO.md |
| docs/tasks/todo.md | P0 | ROADMAP.md |
| docs/tasks/done.md | P0 | CHANGELOG.md |
| docs/context/project-brief.md | P1 | .claude.md |
| docs/context/coding-standards.md | P1 | CONTRIBUTING.md |
| docs/tutorials/first-search.md | P1 | QUICK_START.md |
| docs/how-to/setup-local.md | P1 | SETUP.md |
| docs/how-to/troubleshooting.md | P1 | Various |
| docs/reference/api.md | P2 | API_REFERENCE.md |
| docs/explanation/architecture.md | P2 | ARCHITECTURE.md |

---

## Success Criteria

- [ ] Единая точка входа (index.md)
- [ ] Ясный статус проекта (local vs prod)
- [ ] Задачи структурированы (active/todo/done)
- [ ] Нет дубликатов
- [ ] Все версии синхронизированы
- [ ] Claude Code может эффективно использовать context/

---

## Language Decision

**Решение:** Русский язык для всех новых документов.
- Проект на русском (use case — украинские юридические документы)
- Код и API на английском (стандарт)
- Комментарии в коде на английском

---

**Approved:** 2026-01-21

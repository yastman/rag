# Session Prompt - Local Project Setup

Скопируй этот промпт в новую сессию Claude Code:

---

```
/superpowers:executing-plans

## Контекст

Проект: RAG Pipeline с Telegram ботом для поиска по документам.
Текущее состояние: Docker сервисы работают, но есть проблемы с конфигурацией.

## Твоя задача

Выполнить план из `docs/plans/2026-01-21-local-project-setup.md` — 17 задач в 7 фазах.

Цель: заставить проект полностью работать локально.

## Важные файлы

- **План:** `docs/plans/2026-01-21-local-project-setup.md` — детальные шаги
- **Задачи:** `TODO.md` — отслеживание прогресса
- **Роадмап:** `ROADMAP.md` — общий статус

## Правила выполнения

1. Выполняй задачи по порядку (Phase 1 → Phase 7)
2. После каждой задачи:
   - Отметь ✅ в плане
   - Обнови статус в TODO.md (⏳ → ✅)
   - Обнови прогресс-бар в TODO.md
3. Если нашёл новую проблему:
   - Добавь в секцию "Discovered Issues" в TODO.md
   - Добавь задачу в план
4. Коммить после каждой логической группы задач

## Текущий статус

Phase 1-7: 0/17 задач выполнено

Начни с Phase 1, Task 1.1: Fix BGE_M3_URL in .env.local

## Проверка перед стартом

Убедись что Docker сервисы запущены:
docker ps --format "table {{.Names}}\t{{.Status}}"

Должны быть: dev-qdrant, dev-redis, dev-bge-m3, dev-mlflow, dev-langfuse, dev-postgres, dev-docling, dev-lightrag
```

---

**Использование:**

1. Открой новую сессию Claude Code в директории проекта
2. Скопируй промпт выше
3. Claude начнёт выполнять план с Task 1.1

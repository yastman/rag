# Claude Code Setup Optimization — Design Document

**Дата:** 2026-03-05
**Статус:** Approved
**Scope:** Оптимизация конфигурации Claude Code для rag-fresh

---

## Контекст

Аудит текущего setup показал: конфигурация на ~80% оптимальна. Rules имеют `paths:` frontmatter,
skills не дублируются, плагины работают. Документ фиксирует найденные проблемы и план их устранения.

## Текущий стек (проверено тестами)

| Компонент | Версия | Статус | Назначение |
|-----------|--------|--------|------------|
| superpowers | 4.3.1 | OK | TDD, brainstorming, debugging, plans |
| context-mode | 0.9.22 | OK | Sandbox для output, экономия контекста |
| pyright LSP | 0.1.0 | OK | Type checking, навигация по символам |
| context7 MCP | latest | OK | API docs lookup (qdrant, cocoindex, fastapi) |
| sequential-thinking | latest | OK | Структурированное рассуждение |
| langfuse MCP | latest | НЕ СТАРТУЕТ | Процесс не запускается |

## Найденные проблемы

### P0 — Критичные

#### 1. caching.md glob не матчит реальные файлы
- **Проблема:** `paths: "src/cache/**"` → директории `src/cache/` не существует
- **Реальное расположение:** `telegram_bot/integrations/cache.py`, `telegram_bot/services/*cache*`
- **Влияние:** Rule не грузится когда работаешь с кэшем
- **Фикс:** Обновить glob на `"**/cache*.py, telegram_bot/integrations/cache.py"`

### P1 — Важные

#### 2. Дубликат "Parallel Sessions" в CLAUDE.md и CLAUDE.local.md
- **Проблема:** Одна и та же информация в двух местах
- **Фикс:** Консолидировать в CLAUDE.md, убрать из CLAUDE.local.md

#### 3. Langfuse MCP не стартует
- **Проблема:** Credentials в `.mcp.json`, но процесс не запускается
- **Варианты:** (a) исправить конфиг (b) удалить если не используется
- **Рекомендация:** Проверить нужен ли — Langfuse web UI доступен на localhost:3001

#### 4. Langfuse credentials захардкожены в .mcp.json
- **Проблема:** `sk-lf-*` и `pk-lf-*` ключи в plain text в файле
- **Фикс:** Переместить в `.env`, использовать `$LANGFUSE_PUBLIC_KEY` и т.д.

### P2 — Улучшения

#### 5. Бинарные правила как rules вместо hooks
- **Проблема:** Правила типа "никогда не использовать `.search()`" — soft constraint, Claude может забыть
- **Примеры:**
  - `.search()` запрещён → только `.query_points()` (в search.md)
  - `asyncio.run()` запрещён в `mutate()` (в ingestion.md)
  - Прямой `OpenAI()` запрещён → только `langfuse.openai.AsyncOpenAI` (в llm-integration.md)
- **Фикс:** PostToolUse hooks с grep-проверками
- **Решение:** Отложить — текущие rules работают, hooks добавят сложность

#### 6. context-mode doctor показывает FAIL на hooks
- **Проблема:** Doctor ищет hooks в `settings.json`, а они в plugin-managed `hooks.json`
- **Влияние:** Нулевое — hooks реально работают через plugin mechanism
- **Фикс:** Не требуется, false-negative

## Что НЕ делаем (обоснование)

| Идея | Почему нет |
|------|-----------|
| GrepAI MCP | Для 50K LOC grep + Explore agent достаточно. +токены каждый turn |
| Claude-Mem | Уже есть store_learning / recall через CC v3. Дублирование |
| Agent Teams | 3-7x стоимость, для 1 разработчика tmux-swarm покрывает |
| Image context compression | Экспериментальное, не для прод setup |
| ast-grep MCP | LSP pyright покрывает навигацию, ast-grep skill уже есть |
| Больше MCP серверов | Каждый = +100-200 токенов/turn |
| Удаление sequential-thinking | Используется редко но полезен для архитектурных решений |

## Проверенные возможности (тесты 2026-03-05)

### LSP pyright
- `documentSymbol` — все символы файла
- `hover` — полные сигнатуры + docstring
- `findReferences` — 11 ссылок в 4 файлах за 1 вызов
- `goToDefinition` — переход к определению типа
- Auto-diagnostics — нашёл 2 type errors + 3 deprecation в rag_core.py

### context-mode
- `batch_execute` — 5 команд + 4 поиска за 1 вызов, output в sandbox
- `execute` — sandbox для JS/Python/Shell
- `search` — BM25 по индексированным данным
- Hooks работают через plugin mechanism (SessionStart, PreToolUse)

### context7
- `resolve-library-id` — нашёл CocoIndex (1017 сниппетов)
- `query-docs` — актуальные примеры add_source + collector

## План реализации

| # | Действие | Время | Приоритет |
|---|----------|-------|-----------|
| 1 | Фикс glob в caching.md | 1 мин | P0 |
| 2 | Консолидация "Parallel Sessions" | 5 мин | P1 |
| 3 | Диагностика langfuse MCP | 10 мин | P1 |
| 4 | Перенос langfuse credentials в .env | 5 мин | P1 |

**Общее время:** ~20 минут

---
description: Code search and navigation tools
globs: ["**/*.py", "**/*.md"]
---

# Code Search Tools

3 системы, каждая для своего:

| Задача | Инструмент | Пример |
|--------|-----------|--------|
| "Найди код кеширования" | **GrepAI** `grepai_search` | Semantic — понимает intent, не literal match |
| "Кто вызывает X" | **GrepAI** `grepai_trace_callers` | Call graph из индекса символов |
| "Что вызывает X" | **GrepAI** `grepai_trace_callees` | Зависимости функции |
| Полный call graph | **GrepAI** `grepai_trace_graph` | `depth: 1-2`, визуализация связей |
| Тип/сигнатура функции | **LSP** `hover` | Точные типы из Pyright |
| Go-to-definition | **LSP** `goToDefinition` | Навигация к определению |
| Все символы файла | **LSP** `documentSymbol` | Структура модуля |
| Точный текст/regex | **Grep** | `TODO`, imports, конкретный паттерн |
| Найти файл | **Glob** | `**/*cache*.py`, `src/**/*.yaml` |

## GrepAI tips

- `format: "toon"` + `compact: true` — экономия токенов
- `grepai_index_status` — проверить что индекс актуален
- Daemon: `grepai watch --background` (запускать вручную после перезагрузки)
- Config: `.grepai/config.yaml` (gitignored, локальный)

## Debugging workflow

```
1. grepai_search "описание бага"          → найти релевантный код
2. grepai_trace_callers "broken_func"     → понять кто вызывает
3. LSP hover → проверить типы/сигнатуры
4. Grep "error_pattern" → найти все occurrences
5. LSP findReferences → точные references для refactoring
```

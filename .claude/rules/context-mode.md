---
description: "Context-mode MCP plugin — context window economy"
---

# Context-Mode (MCP plugin)

Экономия контекста ~87%. Сырой output остаётся в sandbox, в контекст — только резюме.

| Вместо | Используй | Когда |
|--------|-----------|-------|
| `Bash` (>20 строк output) | `execute(language, code)` | make check, git log, docker ps, pytest |
| `Read` (анализ) | `execute_file(path, language, code)` | Логи, JSON, CSV, большие файлы |
| N × Bash | `batch_execute(commands, queries)` | Исследование, сбор контекста |
| `WebFetch` | `fetch_and_index(url)` + `search(queries)` | Документация, API reference |

**Read** — только для файлов, которые будешь **Edit**-ить. **Bash** — только git, mkdir, mv, rm, echo.

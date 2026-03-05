# GrepAI + Ollama (nomic-embed-text-v2-moe) Setup Design

Date: 2026-03-05

## Цель

Добавить semantic code search в Claude Code workflow через GrepAI MCP с локальными embeddings (Ollama + `nomic-embed-text-v2-moe` на GTX 1070).

## Контекст

- GrepAI установлен и работает: `grepai version 0.34.0`.
- Ollama установлен: `ollama version 0.17.6`.
- Локально скачаны обе embedding-модели: `nomic-embed-text-v2-moe` и `bge-m3`.
- Фактически активная конфигурация `.grepai/config.yaml` использует `nomic-embed-text-v2-moe` (768 dims, `parallelism: 8`).
- Индекс уже собран и обновляется watcher-ом: `Files indexed: 652`, `Total chunks: 6893`.

## Решение

### Архитектура

```text
GTX 1070 (8GB VRAM)
  +-- Ollama daemon (nomic-embed-text-v2-moe, ~957MB)
        +-- GrepAI watch daemon (background)
              |-- rag-fresh (main)           -> .grepai/index.gob
              |-- rag-fresh-wt-* (worktrees) -> .grepai/index.gob (per worktree)
              |
              +-- MCP Server (stdio) -> Claude Code
```

### Почему nomic-embed-text-v2-moe

- Мультиязычность (русские комментарии + английский код).
- Быстрый inference и стабильные результаты в code search.
- 768 dimensions: хороший баланс качество/скорость.
- Вписывается в доступную VRAM на GTX 1070.

### Worktree handling

GrepAI поддерживает worktrees как first-class сценарий:
- Автодетект linked worktrees для watch-процесса.
- Отдельный локальный GOB-индекс на каждый worktree.
- Локальный Ollama снимает внешние rate limits для параллельной работы в нескольких worktree.

### Конфиг `.grepai/config.yaml` (актуальный)

```yaml
version: 1
embedder:
    provider: ollama
    model: nomic-embed-text-v2-moe
    endpoint: http://localhost:11434
    dimensions: 768
    parallelism: 8
store:
    backend: gob
chunking:
    size: 256
    overlap: 32
watch:
    debounce_ms: 500
search:
    boost:
        enabled: true
        penalties:
            - pattern: /tests/
              factor: 0.5
            - pattern: /docs/
              factor: 0.6
            - pattern: /evaluation/
              factor: 0.3
            - pattern: /k8s/
              factor: 0.4
        bonuses:
            - pattern: /src/
              factor: 1.15
            - pattern: /telegram_bot/services/
              factor: 1.2
            - pattern: /telegram_bot/agents/
              factor: 1.2
    hybrid:
        enabled: false
        k: 60
trace:
    mode: fast
    enabled_languages:
        - .py
    exclude_patterns:
        - test_*.py
        - '*_test.py'
update:
    check_on_startup: false
external_gitignore: /home/user/projects/rag-fresh/.grepaiignore
```

### MCP server template (`.mcp.example.json`)

```json
{
  "mcpServers": {
    "grepai": {
      "command": "grepai",
      "args": ["mcp-serve"]
    }
  }
}
```

Важно:
- рабочий файл с секретами должен быть только локальным: `.mcp.json`;
- в git коммитится только шаблон `.mcp.example.json`;
- `.mcp.json` уже игнорируется в `.gitignore`.

MCP tools (через `grepai mcp-serve`):
- `grepai_search`
- `grepai_trace_callers`
- `grepai_trace_callees`
- `grepai_trace_graph`
- `grepai_index_status`

## Шаги реализации

1. Установить Ollama + `ollama pull nomic-embed-text-v2-moe`.
2. Обновить `.grepai/config.yaml` и указать `external_gitignore` на `.grepaiignore`.
3. Добавить GrepAI в `.mcp.example.json`, создать локальный `.mcp.json` из шаблона.
4. Запустить `grepai watch --background` и дождаться индексации.
5. Протестировать semantic search и trace через CLI.
6. Проверить MCP tools через Claude Code.
7. Добавить `.grepai/` в `.gitignore` (если ещё не добавлен).

## Ресурсы

- VRAM: ~957MB под `nomic-embed-text-v2-moe`.
- Диск: ~37MB для текущего индекса (`index.gob` + `symbols.gob`).
- Время первичной индексации: ~20-25 минут на полный репозиторий и worktree.
- CPU в фоне: низкий, burst при file change.

## Тестирование (проведено)

| Тест | Результат |
|---|---|
| `ollama list` | Есть `nomic-embed-text-v2-moe` и `bge-m3` |
| `curl -s http://localhost:11434/api/embed ...` | `dims=768` |
| `grepai status --no-ui` | `Files indexed: 652`, `Total chunks: 6893`, provider = `nomic-embed-text-v2-moe` |
| `grepai trace callers "create_search_engine"` | 8 callers |
| `grepai mcp-serve --help` | MCP tools доступны |

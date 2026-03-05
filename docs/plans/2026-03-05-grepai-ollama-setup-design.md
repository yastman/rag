# GrepAI + Ollama (bge-m3) Setup Design

Date: 2026-03-05

## Цель

Добавить semantic code search в Claude Code workflow через GrepAI MCP с локальными embeddings (Ollama + bge-m3 на GTX 1070).

## Контекст

- GrepAI v0.34.0 установлен (`~/.local/bin/grepai`), протестирован на `src/` (73 файла, 436 chunks)
- Pyright LSP уже работает — дополняет GrepAI (типы, diagnostics, references)
- Проект: ~8800 chunks, 3 git worktrees (main + 2 agent worktrees)
- OpenAI embeddings невозможны: 3 worktrees x TPM limit = постоянные 429 rate limits

## Решение

### Архитектура

```
GTX 1070 (8GB VRAM)
  +-- Ollama daemon (bge-m3, 1.2GB VRAM)
        +-- GrepAI watch daemon (background)
              |-- rag-fresh (main)           -> .grepai/index.gob
              |-- rag-fresh-wt-* (worktrees) -> .grepai/index.gob (per worktree)
              |
              +-- MCP Server (stdio) -> Claude Code
```

### Почему bge-m3

- Multilingual (русские комменты + английский код)
- 1024 dims, excellent quality
- Уже используется в RAG pipeline проекта (Docker контейнер на :8000)
- 567M параметров = 1.2GB VRAM = легко на GTX 1070

### Worktree handling

GrepAI поддерживает worktrees как first-class фичу:
- PR #115 (v0.31.0): `discoverWorktreesForWatch()` — автодетект linked worktrees
- PR #142 (v0.33.0): content-hash dedup для PostgreSQL/Qdrant backends
- С GOB backend: каждый worktree получает отдельный индекс (нормально)
- С Ollama локально: нет rate limits, 3x embedding = ~3 мин вместо 1 мин

### Конфиг `.grepai/config.yaml`

```yaml
version: 1
embedder:
    provider: ollama
    model: bge-m3
    endpoint: http://localhost:11434
    dimensions: 1024
    parallelism: 0
store:
    backend: gob
chunking:
    size: 512
    overlap: 50
watch:
    debounce_ms: 500
search:
    boost:
        enabled: true
        penalties:
            - pattern: /tests/
              factor: 0.5
            - pattern: test_
              factor: 0.5
            - pattern: /mocks/
              factor: 0.4
            - pattern: /fixtures/
              factor: 0.4
            - pattern: .md
              factor: 0.6
            - pattern: /docs/
              factor: 0.6
        bonuses:
            - pattern: /src/
              factor: 1.1
            - pattern: /telegram_bot/
              factor: 1.1
    hybrid:
        enabled: false
        k: 60
trace:
    mode: fast
    enabled_languages:
        - .py
    exclude_patterns:
        - 'test_*.py'
        - '*_test.py'
ignore:
    - .git
    - .grepai
    - __pycache__
    - .venv
    - venv
    - node_modules
    - qdrant_storage
    - logs
    - data
    - .mypy_cache
    - .ruff_cache
    - .pytest_cache
    - htmlcov
    - "*.egg-info"
    - .claude/worktrees
update:
    check_on_startup: false
```

### MCP Server (`.mcp.json`)

```json
"grepai": {
    "type": "stdio",
    "command": "grepai",
    "args": ["mcp-serve"],
    "env": {
        "PATH": "/home/user/.local/bin:/usr/local/bin:/usr/bin:/bin"
    }
}
```

MCP tools:
- `grepai_search` — semantic code search
- `grepai_trace_callers` — кто вызывает символ
- `grepai_trace_callees` — что вызывает символ
- `grepai_trace_graph` — call graph вокруг символа
- `grepai_index_status` — статус индекса

## Шаги реализации

1. Установить Ollama + `ollama pull bge-m3`
2. Обновить `.grepai/config.yaml` (провайдер, ignore, trace languages)
3. Добавить grepai в `.mcp.json`
4. Запустить `grepai watch --background` и дождаться индексации
5. Протестировать semantic search и trace через CLI
6. Протестировать MCP tools через Claude Code
7. Добавить `.grepai/` в `.gitignore` (если не добавлен)

## Ресурсы

- VRAM: 1.2GB (из 8GB)
- Диск: ~10-20MB на индекс
- Время первой индексации: ~2-3 мин (8800 chunks)
- CPU в фоне: минимально (file watcher)

## Тестирование (проведено)

| Тест | Результат |
|---|---|
| `grepai search "hybrid search with RRF fusion"` | Точно нашёл `HybridRRFSearchEngine`, score 0.62 |
| `grepai search "voice transcription speech to text"` | Точно нашёл `src/voice/transcript_store.py` |
| `grepai trace callers "create_search_engine"` | 8 callers с контекстом строки |
| `grepai trace callees "create_search_engine"` | 7 callees |
| `grepai search --json --compact` | JSON output для MCP интеграции |

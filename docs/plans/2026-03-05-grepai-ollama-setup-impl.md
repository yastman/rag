# GrepAI + Ollama Setup Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Настроить semantic code search через GrepAI MCP с локальными embeddings (Ollama + `nomic-embed-text-v2-moe`).

**Architecture:** Ollama daemon (`nomic-embed-text-v2-moe`, ~957MB VRAM) -> GrepAI watch daemon (background) -> MCP server (stdio) -> Claude Code.

**Tech Stack:** Ollama 0.17.6, GrepAI v0.34.0, `nomic-embed-text-v2-moe` (768 dims).

**Design doc:** `docs/plans/2026-03-05-grepai-ollama-setup-design.md`

---

### Task 1: Установить Ollama

**Step 1: Установить Ollama**

```bash
curl -fsSL https://ollama.com/install.sh | sh
```

**Step 2: Проверить установку**

```bash
ollama --version
```
Expected: `ollama version 0.x.x`

**Step 3: Проверить GPU**

```bash
nvidia-smi | grep -i "MiB"
```
Expected: GPU видна, достаточно VRAM

---

### Task 2: Скачать embedding-модель

**Step 1: Pull основной модели**

```bash
ollama pull nomic-embed-text-v2-moe
```
Expected: скачается ~957MB, сообщение `success`

**Step 2 (optional): Pull fallback/альтернативы**

```bash
ollama pull bge-m3
```

**Step 3: Проверить модели**

```bash
ollama list | grep -E 'nomic-embed-text-v2-moe|bge-m3'
```
Expected: в списке есть `nomic-embed-text-v2-moe:latest`

**Step 4: Проверить embedding endpoint (актуальный API)**

```bash
curl -s http://localhost:11434/api/embed \
  -d '{"model":"nomic-embed-text-v2-moe","input":"test"}' \
  | python3 -c 'import sys,json; d=json.load(sys.stdin); print("dims="+str(len(d["embeddings"][0])))'
```
Expected: `dims=768`

---

### Task 3: Обновить `.grepai/config.yaml`

**File:** Modify: `.grepai/config.yaml`

**Step 1: Очистить старый индекс (если нужен clean rebuild)**

```bash
rm -f .grepai/index.gob .grepai/index.gob.lock .grepai/symbols.gob
```

**Step 2: Записать конфиг**

Заменить содержимое `.grepai/config.yaml` на:

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
            - pattern: /evaluation/
              factor: 0.3
            - pattern: /scripts/
              factor: 0.7
            - pattern: /docker/
              factor: 0.4
            - pattern: /k8s/
              factor: 0.4
        bonuses:
            - pattern: /src/
              factor: 1.15
            - pattern: /telegram_bot/
              factor: 1.1
            - pattern: /telegram_bot/services/
              factor: 1.2
            - pattern: /telegram_bot/agents/
              factor: 1.2
            - pattern: /src/ingestion/
              factor: 1.15
            - pattern: /src/retrieval/
              factor: 1.15
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
ignore:
    - .git
    - .grepai
    - .github
    - .idea
    - .vscode
    - __pycache__
    - .mypy_cache
    - .ruff_cache
    - .pytest_cache
    - .cache
    - .tox
    - htmlcov
    - .coverage
    - '*.egg-info'
    - '*.dist-info'
    - .venv
    - venv
    - telegram_bot/.venv
    - uv.lock
    - package-lock.json
    - '*.lock'
    - data
    - datasets
    - drive-sync
    - docs/documents
    - docs/processed
    - docs/test_data
    - logs
    - reports
    - docs/reports
    - docs/artifacts
    - evaluation/reports
    - evaluation/data
    - mlruns
    - langfuse_logs
    - tests/data
    - tests/fixtures
    - legacy
    - docs/archive
    - docs/archive_*
    - qdrant_storage
    - node_modules
    - k8s
    - deploy
    - docker/rclone
    - docker/monitoring
    - docker/postgres
    - docker/mlflow
    - .claude
    - .signals
    - .planning
    - coverage.json
    - coverage_report_final.txt
    - AUDIT_REPORT.md
    - TODO.md
    - DOCKER.md
    - CHANGELOG.md
    - AGENTS.md
    - test_output_*.txt
    - test_coverage_*.txt
    - debug_*.py
    - verify_*.py
    - .test_durations
    - =*
    - telegram_bot/static
    - '*.jpg'
    - '*.jpeg'
    - '*.png'
    - '*.gif'
    - '*.tar.gz'
    - '*.backup'
    - '*.session'
    - '*.mp3'
    - '*.wav'
    - '*.ogg'
    - '*.pdf'
    - '*.so'
    - '*.whl'
external_gitignore: /home/user/projects/rag-fresh/.grepaiignore
```

**Step 3: Проверить конфиг**

```bash
head -8 .grepai/config.yaml
rg -n 'model:|dimensions:|parallelism:|external_gitignore:' .grepai/config.yaml
```
Expected: `model: nomic-embed-text-v2-moe`, `dimensions: 768`, `parallelism: 8`, `external_gitignore` задан

---

### Task 4: Добавить GrepAI MCP server безопасно

По оф. докам: https://yoanbernabeu.github.io/grepai/mcp/

**Step 1: Убедиться что grepai в PATH**

```bash
grep -q 'local/bin' ~/.zshrc && echo "OK" || echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.zshrc
```

**Step 2: Зарегистрировать через CLI (user-level)**

```bash
claude mcp add grepai -s user -- grepai mcp-serve
```
Expected: `Added grepai MCP server`

**Step 3: Коммитить только шаблон `.mcp.example.json`**

Создать `.mcp.example.json`:

```json
{
  "mcpServers": {
    "sequential-thinking": {
      "type": "stdio",
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-sequential-thinking"]
    },
    "langfuse": {
      "type": "stdio",
      "command": "uvx",
      "args": ["--python", "3.11", "langfuse-mcp"],
      "env": {
        "LANGFUSE_PUBLIC_KEY": "<REPLACE_WITH_LANGFUSE_PUBLIC_KEY>",
        "LANGFUSE_SECRET_KEY": "<REPLACE_WITH_LANGFUSE_SECRET_KEY>",
        "LANGFUSE_HOST": "http://localhost:3001"
      }
    },
    "grepai": {
      "command": "grepai",
      "args": ["mcp-serve"]
    }
  }
}
```

**Step 4: Создать локальный `.mcp.json` из шаблона (НЕ коммитить)**

```bash
cp -n .mcp.example.json .mcp.json
```

Далее вручную заменить плейсхолдеры на реальные ключи только в локальном `.mcp.json`.

**Step 5: Проверить JSON**

```bash
python3 -c "import json; json.load(open('.mcp.example.json')); print('example OK')"
python3 -c "import json; json.load(open('.mcp.json')); print('local OK')"
```

---

### Task 5: Проверить ignore-файлы

**Step 1: Проверить `.grepai/` в `.gitignore`**

```bash
grep -q '^\.grepai/$' .gitignore && echo "ALREADY_IGNORED" || echo "NEED_TO_ADD"
```

**Step 2: Проверить `.mcp.json` в `.gitignore`**

```bash
grep -q '^\.mcp\.json$' .gitignore && echo "MCP_IGNORED" || echo "MCP_NOT_IGNORED"
```

**Step 3: Проверить `.grepaiignore`**

```bash
rg -n '^\.mcp\.json$|^\.mcp\.example\.json$' .grepaiignore
```

---

### Task 6: Запустить индексацию и дождаться завершения

**Step 1: Запустить `grepai watch` в tmux**

```bash
mkdir -p logs
tmux new-window -n "W-GREPAI" -c /home/user/projects/rag-fresh
tmux send-keys -t "W-GREPAI" "grepai watch --no-ui 2>&1 | tee logs/grepai-watch.log; echo '[COMPLETE]'" Enter
```

**Step 2: Мониторить прогресс**

```bash
tail -f logs/grepai-watch.log
```
Expected: `Embedding ... 100%`, затем `Initial scan complete`

**Step 3: Проверить статус**

```bash
grepai status --no-ui
```
Expected: `Files indexed: >600`, `Total chunks: >6800`, `Provider: ollama (nomic-embed-text-v2-moe)`

---

### Task 7: Тестирование CLI

**Step 1: Semantic search**

```bash
grepai search "hybrid search with RRF fusion and reranking"
```
Expected: результаты из `src/retrieval/search_engines.py`

**Step 2: Trace callers**

```bash
grepai trace callers "create_search_engine"
```
Expected: найдено несколько callers (включая `src/core/pipeline.py` и tests)

**Step 3: Trace callees**

```bash
grepai trace callees "create_search_engine"
```
Expected: список вызываемых engine-конструкторов

Если прилетает `failed to decode symbol index: unexpected EOF`, перезапустить watcher:

```bash
grepai watch --stop
grepai watch --background
```

**Step 4: Search JSON compact**

```bash
grepai search "voice transcription" --json --compact \
  | python3 -c 'import sys,json; r=json.load(sys.stdin); n=len(r) if isinstance(r,list) else len(r.get("results",[])); print(f"results={n}")'
```

---

### Task 8: Тестирование MCP через Claude Code

**Step 1: Перезапустить Claude Code**

Проверить `/mcp`, что сервер `grepai` виден.

**Step 2: Проверить доступные tools**

Должны быть:
- `grepai_search`
- `grepai_trace_callers`
- `grepai_trace_callees`
- `grepai_trace_graph`
- `grepai_index_status`

**Step 3: Тестовый запрос**

Попросить Claude Code: `используй grepai_search чтобы найти код кеширования`.

---

### Task 9: Запустить daemon в background

**Step 1: Остановить foreground watch**

```bash
tmux send-keys -t "W-GREPAI" C-c
```

**Step 2: Запустить background daemon**

```bash
grepai watch --background
```
Expected: `Background watcher started`

**Step 3: Проверить**

```bash
grepai watch --status
```
Expected: `running`

---

### Task 10: Commit

**Step 1: Проверить изменения**

```bash
git diff --stat
git status -s
```

**Step 2: Коммит**

```bash
git add .gitignore .grepaiignore .mcp.example.json docs/plans/2026-03-05-grepai-ollama-setup-design.md docs/plans/2026-03-05-grepai-ollama-setup-impl.md
git rm --cached .mcp.json 2>/dev/null || true
git commit -m "feat(tools): add safe GrepAI MCP template and align Ollama setup docs"
```

Note:
- `.mcp.json` не коммитим (секреты только локально).
- `.mcp.example.json` — единственный файл для репозитория.
- `.grepai/` не коммитим (локальный индекс/конфиг).

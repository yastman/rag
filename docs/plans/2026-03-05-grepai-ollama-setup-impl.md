# GrepAI + Ollama Setup Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Настроить semantic code search через GrepAI MCP с локальными embeddings (Ollama + bge-m3).

**Architecture:** Ollama daemon (bge-m3, 1.2GB VRAM на GTX 1070) -> GrepAI watch daemon (background) -> MCP server (stdio) -> Claude Code.

**Tech Stack:** Ollama, GrepAI v0.34.0, bge-m3 (567M params, 1024 dims)

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
Expected: `ollama version X.X.X`

**Step 3: Проверить GPU**

```bash
nvidia-smi | grep -i "MiB"
```
Expected: GPU видна, достаточно VRAM

---

### Task 2: Скачать bge-m3

**Step 1: Pull модель**

```bash
ollama pull bge-m3
```
Expected: скачается ~1.2GB, сообщение `success`

**Step 2: Проверить модель**

```bash
ollama list | grep bge-m3
```
Expected: `bge-m3:latest  567m  ...`

**Step 3: Проверить embedding endpoint**

```bash
curl -s http://localhost:11434/api/embeddings -d '{"model":"bge-m3","prompt":"test"}' | python3 -c "import sys,json; d=json.load(sys.stdin); print(f'dims={len(d[\"embedding\"])}')"
```
Expected: `dims=1024`

---

### Task 3: Обновить .grepai/config.yaml

**File:** Modify: `.grepai/config.yaml`

**Step 1: Очистить старый индекс**

```bash
rm -f .grepai/index.gob .grepai/index.gob.lock .grepai/symbols.gob
```

**Step 2: Записать конфиг**

Заменить содержимое `.grepai/config.yaml` на:

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
    # VCS & tooling
    - .git
    - .grepai
    - .idea
    - .vscode

    # Python caches (533MB+ .mypy_cache alone)
    - __pycache__
    - .mypy_cache
    - .ruff_cache
    - .pytest_cache
    - .cache
    - .tox
    - htmlcov
    - .coverage
    - "*.egg-info"

    # Virtual environments
    - .venv
    - venv
    - telegram_bot/.venv

    # Dependency locks (not code)
    - uv.lock
    - package-lock.json

    # Data & user content (not code)
    - data
    - datasets
    - drive-sync
    - docs/documents
    - docs/processed
    - docs/test_data

    # Generated reports & logs
    - logs
    - reports
    - docs/reports
    - docs/artifacts
    - evaluation/reports
    - mlruns
    - langfuse_logs

    # Test fixtures (noise for semantic search)
    - tests/data
    - tests/fixtures

    # Archive & legacy
    - legacy
    - docs/archive

    # Infrastructure (not app logic)
    - qdrant_storage
    - node_modules
    - k8s/secrets
    - deploy
    - docker/rclone

    # Claude internal (machine-specific)
    - .claude/skills
    - .claude/prompts
    - .claude/hooks
    - .claude/worktrees
    - .claude/tsc-cache
    - .signals
    - .planning

    # Media & binary
    - telegram_bot/static
    - "*.jpg"
    - "*.jpeg"
    - "*.png"
    - "*.gif"
    - "*.tar.gz"
    - "*.backup"
    - "*.session"
update:
    check_on_startup: false
```

**Step 3: Проверить конфиг**

```bash
head -6 .grepai/config.yaml
```
Expected: `provider: ollama`, `model: bge-m3`, `dimensions: 1024`

---

### Task 4: Добавить GrepAI MCP server

По оф докам: https://yoanbernabeu.github.io/grepai/mcp/

**Step 1: Убедиться что grepai в PATH**

```bash
grep -q 'local/bin' ~/.zshrc && echo "OK" || echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.zshrc
```

**Step 2: Зарегистрировать через CLI (user-level)**

```bash
claude mcp add grepai -s user -- grepai mcp-serve
```
Expected: `Added grepai MCP server`

**Step 3: Добавить в `.mcp.json` (project-level)**

В `.mcp.json` добавить в объект `mcpServers` (по оф докам формат без `type`):

```json
"grepai": {
    "command": "grepai",
    "args": ["mcp-serve"]
}
```

**Step 4: Проверить JSON**

```bash
python3 -c "import json; json.load(open('.mcp.json')); print('OK')"
```
Expected: `OK`

---

### Task 5: Проверить .gitignore

**Step 1: Проверить что .grepai/ в .gitignore**

```bash
grep -q '.grepai' .gitignore && echo "ALREADY_IGNORED" || echo "NEED_TO_ADD"
```

**Step 2: Если NEED_TO_ADD — добавить**

```bash
echo ".grepai/" >> .gitignore
```

---

### Task 6: Запустить индексацию и дождаться завершения

**Step 1: Запустить grepai watch в tmux**

```bash
mkdir -p logs
tmux new-window -n "W-GREPAI" -c /home/user/projects/rag-fresh
tmux send-keys -t "W-GREPAI" "grepai watch --no-ui 2>&1 | tee logs/grepai-watch.log; echo '[COMPLETE]'" Enter
```

**Step 2: Мониторить прогресс**

```bash
tail -f logs/grepai-watch.log
```
Expected: `Embedding [████████████████████] 100%` для каждого worktree, затем `Initial scan complete`

**Step 3: Проверить статус**

```bash
grepai status --no-ui
```
Expected: `Files indexed: >80`, `Total chunks: >400`, `Provider: ollama (bge-m3)`

---

### Task 7: Тестирование CLI

**Step 1: Semantic search**

```bash
grepai search "hybrid search with RRF fusion and reranking"
```
Expected: Результаты из `src/retrieval/search_engines.py` с score > 0.5

**Step 2: Trace callers**

```bash
grepai trace callers "create_search_engine"
```
Expected: Callers из `pipeline.py`, `run_ab_test.py`

**Step 3: Trace callees**

```bash
grepai trace callees "create_search_engine"
```
Expected: Callees — `BaselineSearchEngine`, `HybridRRFSearchEngine`, etc.

**Step 4: Search JSON compact**

```bash
grepai search "voice transcription" --json --compact | python3 -c "import sys,json; r=json.load(sys.stdin); print(f'{len(r)} results, top={r[0][\"file_path\"]}')"
```
Expected: Результаты, top = `src/voice/...`

---

### Task 8: Тестирование MCP через Claude Code

**Step 1: Перезапустить Claude Code**

Выйти и зайти заново, или проверить `/mcp` что grepai виден.

**Step 2: Проверить доступные tools**

Должны быть:
- `grepai_search`
- `grepai_trace_callers`
- `grepai_trace_callees`
- `grepai_trace_graph`
- `grepai_index_status`

**Step 3: Тестовый запрос**

Попросить Claude Code: "используй grepai_search чтобы найти код кеширования"

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
Expected: `Watcher: running`

---

### Task 10: Commit

**Step 1: Проверить**

```bash
git diff --stat
git status -s
```

**Step 2: Commit**

```bash
git add .mcp.json .gitignore docs/plans/2026-03-05-grepai-ollama-setup-design.md docs/plans/2026-03-05-grepai-ollama-setup-impl.md
git commit -m "feat(tools): add GrepAI MCP with Ollama bge-m3 for semantic code search"
```

Note: `.grepai/` НЕ коммитим (в .gitignore). Индекс и конфиг локальные.

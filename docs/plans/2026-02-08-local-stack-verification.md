# Local Dev Stack — Verification & Hardening

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Полностью рабочий локальный стек — от GDrive до ответа бота, с параллельными тестами и оптимизированными Docker-образами.

**Architecture:** VPS (будущий прод) ставим на паузу, вся разработка локально (WSL2). Файлы данных копируем с VPS через scp. Тесты параллелизуем через pytest-xdist (4 workers на 4 физ. ядра). Docker-образы уже имеют multi-stage + non-root — добавляем `.dockerignore` для сервисов.

**Tech Stack:** Python 3.12, uv, pytest + pytest-xdist, Docker BuildKit, aiogram 3

**Hardware:** Ryzen 5 3600 (4C/8T), 12 GB RAM, 1 TB SSD, Docker 8 vCPUs

**Parallelism:** Phase 1 запускает 3 tmux windows параллельно (VPS stop + scp + uv deps). Phase 2 — sequential тестирование. Phase 3 — Docker fix.

---

## Phase 1: Параллельный bootstrap (tmux windows)

Три независимые операции запускаются одновременно в tmux windows.

### Task 1: Setup — tmux windows для параллельных операций

**Files:**
- Create: `logs/` directory

**Step 1: Подготовить логи и определить сессию**

```bash
mkdir -p /home/user/projects/rag-fresh/logs
SESSION=$(TMUX="" tmux list-sessions -F "#{session_name}" | head -1)
echo "Session: $SESSION"
```

Expected: имя текущей tmux-сессии

**Step 2: Запустить 3 параллельных tmux window**

```bash
# Window W-VPS: остановить vps-bot
TMUX="" tmux new-window -t "$SESSION" -n "W-VPS"
sleep 1
TMUX="" tmux send-keys -t "$SESSION:W-VPS" 'ssh vps "docker stop vps-bot" 2>&1 | tee /home/user/projects/rag-fresh/logs/vps-stop.log; echo "[COMPLETE]"' Enter

# Window W-SCP: скопировать drive-sync
TMUX="" tmux new-window -t "$SESSION" -n "W-SCP"
sleep 1
TMUX="" tmux send-keys -t "$SESSION:W-SCP" 'scp -r vps:/opt/rag-fresh/drive-sync/ /home/user/projects/rag-fresh/drive-sync/ 2>&1 | tee /home/user/projects/rag-fresh/logs/scp-sync.log; echo "[COMPLETE]"' Enter

# Window W-DEPS: установить pytest-xdist + pytest-timeout
TMUX="" tmux new-window -t "$SESSION" -n "W-DEPS"
sleep 1
TMUX="" tmux send-keys -t "$SESSION:W-DEPS" 'cd /home/user/projects/rag-fresh && uv add --dev pytest-xdist pytest-timeout 2>&1 | tee /home/user/projects/rag-fresh/logs/deps-install.log; echo "[COMPLETE]"' Enter
```

Expected: 3 окна запустились параллельно. Пользователь видит их в tmux.

**Step 3: Дождаться завершения всех трёх**

```bash
# Проверить [COMPLETE] маркеры
for log in vps-stop scp-sync deps-install; do
  grep -q '\[COMPLETE\]' "/home/user/projects/rag-fresh/logs/${log}.log" 2>/dev/null && echo "$log: DONE" || echo "$log: RUNNING"
done
```

Expected: все три `DONE`

**Step 4: Убрать tmux windows**

```bash
TMUX="" tmux kill-window -t "$SESSION:W-VPS" 2>/dev/null
TMUX="" tmux kill-window -t "$SESSION:W-SCP" 2>/dev/null
TMUX="" tmux kill-window -t "$SESSION:W-DEPS" 2>/dev/null
```

**Step 5: Commit — нет** (пока)

---

### Task 2: Верификация Phase 1

**Files:**
- None (проверочный шаг)

**Step 1: Проверить VPS-бот остановлен**

```bash
docker compose -f docker-compose.dev.yml --profile bot restart bot
sleep 10
docker logs dev-bot --tail 5 2>&1
```

Expected: НЕТ строки `TelegramConflictError`

**Step 2: Проверить drive-sync файлы**

```bash
find /home/user/projects/rag-fresh/drive-sync/ -type f | wc -l
```

Expected: `14`

**Step 3: Проверить pytest-xdist установлен**

```bash
cd /home/user/projects/rag-fresh
uv run python -c "import xdist; print(xdist.__version__)"
uv run python -c "import pytest_timeout; print('OK')"
```

Expected: версия xdist (3.8.0+) и `OK`

**Step 4: Проверить что ingestion подхватит данные**

```bash
# Подождать ~60 секунд, затем проверить
sleep 60
docker logs dev-ingestion --tail 5 2>&1
```

Expected: `source rows: 14` (не `No input data`)

**Step 5: Проверить Qdrant points**

```bash
curl -s localhost:6333/collections/gdrive_documents_bge | python3 -c "import sys,json; print(json.load(sys.stdin)['result']['points_count'])"
```

Expected: `278` (или больше)

---

### Task 3: Commit Phase 1 — deps

**Files:**
- Modified: `pyproject.toml` (dev deps)
- Modified: `uv.lock`

**Step 1: Commit**

```bash
cd /home/user/projects/rag-fresh
git add pyproject.toml uv.lock
git commit -m "chore(deps): add pytest-xdist and pytest-timeout for parallel testing"
```

---

## Phase 2: Тесты (sequential)

### Task 4: Настроить pytest config

**Files:**
- Modify: `pyproject.toml:301-317` (pytest section)

**Step 1: Обновить `[tool.pytest.ini_options]`**

В файле `pyproject.toml` найти блок `[tool.pytest.ini_options]` и заменить:

```toml
addopts = """
    -ra
    --strict-markers
    --strict-config
    --showlocals
"""
```

На:

```toml
addopts = """
    -ra
    --strict-markers
    --strict-config
"""
```

И добавить после строки `norecursedirs = ["tests/legacy"]`:

```toml
timeout = 30
```

Изменения:
- Убрали `--showlocals` (verbose при `-n auto`, включать руками при debug)
- Добавили `timeout = 30` (ловить зависшие тесты)
- НЕ добавляем `-n auto` в addopts — это сломает debug-запуски. Параллелизм явно: `pytest -n auto`.

**Step 2: Проверить конфиг**

```bash
uv run pytest --co -q tests/unit/ 2>&1 | tail -3
```

Expected: `N tests collected` (без ошибок)

**Step 3: Commit**

```bash
git add pyproject.toml
git commit -m "feat(test): configure pytest-timeout (30s default), clean addopts for xdist"
```

---

### Task 5: Запустить unit-тесты sequential — зафиксировать baseline

**Files:**
- None (диагностика)

**Step 1: Запустить**

```bash
uv run pytest tests/unit/ -x -q 2>&1 | tee /tmp/unit-test-baseline.txt
```

Expected: all pass, или список failures.

**Step 2: Замерить время**

```bash
uv run pytest tests/unit/ -q --tb=no 2>&1 | tail -1
```

Expected: строка `N passed in X.XXs`. Запомнить X.

---

### Task 6: Починить failing unit-тесты (если есть)

**Files:**
- Зависит от результатов Task 5. Если всё зелёное — skip этот task.

**Step 1: Для каждого failing теста — прочитать traceback**

```bash
uv run pytest tests/unit/TEST_FILE.py::TEST_NAME -v 2>&1
```

**Step 2: Починить**

Типичные проблемы:
- `ModuleNotFoundError` → добавить зависимость или mock в `tests/conftest.py`
- `ImportError` → обновить import path
- Hardcoded URL → использовать fixture (`qdrant_url`, `redis_url`)

**Step 3: Убедиться все зелёные**

```bash
uv run pytest tests/unit/ -q --tb=short 2>&1 | tail -5
```

Expected: `N passed in X.XXs` (0 failures)

**Step 4: Commit**

```bash
git add -u
git commit -m "fix(test): fix unit test failures after uv migration"
```

---

### Task 7: Запустить unit-тесты параллельно — сравнить с baseline

**Files:**
- None (верификация)

**Step 1: Запустить с xdist**

```bash
uv run pytest tests/unit/ -n auto -q --tb=short 2>&1 | tee /tmp/unit-test-parallel.txt
```

Expected: all pass, время < 50% от sequential.

**Step 2: Если failures — тесты не изолированы**

Фиксы:
- `tmp_path` вместо hardcoded путей
- Уникальный prefix к Redis keys
- `@pytest.mark.xdist_group("redis")` для конфликтных

**Step 3: Сравнить**

```bash
echo "Sequential:" && grep "passed" /tmp/unit-test-baseline.txt | tail -1
echo "Parallel:" && grep "passed" /tmp/unit-test-parallel.txt | tail -1
```

Expected: 2-4x ускорение.

---

### Task 8: Smoke-тесты

**Files:**
- None (верификация, требует running containers)

**Step 1: Проверить контейнеры**

```bash
docker ps --format "table {{.Names}}\t{{.Status}}" | grep dev
```

Expected: 9/9 healthy

**Step 2: Запустить smoke**

```bash
uv run pytest tests/smoke/ -x -q --tb=short 2>&1 | tee /tmp/smoke-test.txt
```

Expected: pass или понятные skip-ы.

**Step 3: Если failures — skip с причиной**

```python
@pytest.mark.skip(reason="Requires VPS-specific config")
```

**Step 4: Commit (если были изменения)**

```bash
git add -u
git commit -m "fix(test): fix smoke tests for local dev environment"
```

---

### Task 9: E2E — сообщение боту

**Files:**
- None (ручная верификация)

**Step 1: Отправить сообщение боту в Telegram**

Найти бота (`@test_nika_homes_bot`), отправить:
```
Какие есть квартиры?
```

**Step 2: Проверить ответ**

Expected: ответ с информацией из Qdrant.

**Step 3: Проверить логи**

```bash
docker logs dev-bot --tail 30 2>&1
```

Expected: нет ошибок, видно обработку, latency.

**Step 4: Если не ответил — диагностика**

```bash
curl -s localhost:4000/health/liveliness
curl -s localhost:8000/health
curl -s localhost:6333/collections/gdrive_documents_bge | python3 -c "import sys,json; d=json.load(sys.stdin); print(d['result']['status'], d['result']['points_count'])"
```

---

## Phase 3: Docker hardening

### Task 10: Docker audit

**Files:**
- None (анализ)

**Step 1: Прочитать все Dockerfile-ы и заполнить таблицу**

| Best Practice | Bot | BGE-M3 | Ingestion | USER-base |
|---|---|---|---|---|
| Multi-stage | Y | Y | Y | Y |
| `--mount=type=cache` | Y | Y | Y | Y |
| `UV_COMPILE_BYTECODE=1` | Y | Y | Y | Y |
| `UV_LINK_MODE=copy` | Y | Y | Y | Y |
| Non-root user | Y | Y | Y | Y |
| `.dockerignore` | Y (root) | N (нет service-level) | Y (root) | N (нет service-level) |
| Pinned base image | Y | Y | Y | Y |
| Deps before code | Y | Y | Y | Y |

**Итог:** Dockerfile-ы уже на 7/8 best practices. Единственный gap — `.dockerignore` для сервисов BGE-M3 и USER-base.

---

### Task 11: Добавить .dockerignore для сервисов

**Files:**
- Create: `services/bge-m3-api/.dockerignore`
- Create: `services/user-base/.dockerignore`

**Step 1: Создать `services/bge-m3-api/.dockerignore`**

```
__pycache__/
*.pyc
.venv/
.git/
*.md
tests/
.ruff_cache/
.pytest_cache/
```

**Step 2: Создать `services/user-base/.dockerignore`**

```
__pycache__/
*.pyc
.venv/
.git/
*.md
tests/
.ruff_cache/
.pytest_cache/
```

**Step 3: Проверить билд в tmux window (не блокировать основной терминал)**

```bash
SESSION=$(TMUX="" tmux list-sessions -F "#{session_name}" | head -1)
TMUX="" tmux new-window -t "$SESSION" -n "W-BUILD"
sleep 1
TMUX="" tmux send-keys -t "$SESSION:W-BUILD" 'cd /home/user/projects/rag-fresh && docker compose -f docker-compose.dev.yml build bge-m3 user-base 2>&1 | tee logs/docker-build.log; echo "[COMPLETE]"' Enter
```

Дождаться `[COMPLETE]` в `logs/docker-build.log`.

```bash
TMUX="" tmux kill-window -t "$SESSION:W-BUILD" 2>/dev/null
```

Expected: `Successfully built` для обоих.

**Step 4: Commit**

```bash
git add services/bge-m3-api/.dockerignore services/user-base/.dockerignore
git commit -m "chore(docker): add .dockerignore for bge-m3-api and user-base services"
```

---

### Task 12: Финальная верификация

**Files:**
- None

**Step 1: Unit-тесты зелёные (parallel)**

```bash
uv run pytest tests/unit/ -n auto -q --tb=short 2>&1 | tail -5
```

Expected: `N passed`

**Step 2: Smoke-тесты**

```bash
uv run pytest tests/smoke/ -q --tb=short 2>&1 | tail -5
```

Expected: pass или документированные skip-ы

**Step 3: Контейнеры healthy**

```bash
docker ps --format "table {{.Names}}\t{{.Status}}" | grep dev | grep -c healthy
```

Expected: `9`

**Step 4: Бот отвечает**

Проверить в Telegram (Task 9).

**Step 5: git status чистый**

```bash
git status
```

Expected: `nothing to commit, working tree clean`

---

## Граф зависимостей

```
Phase 1 (parallel tmux windows):
  W-VPS  ─────┐
  W-SCP  ─────┼──→ Task 2 (verify) → Task 3 (commit deps)
  W-DEPS ─────┘

Phase 2 (sequential):
  Task 4 (pytest config)
    → Task 5 (unit baseline)
      → Task 6 (fix failures)
        → Task 7 (parallel tests)
          → Task 8 (smoke)
            → Task 9 (E2E bot)

Phase 3 (independent):
  Task 10 (audit) → Task 11 (fix .dockerignore)

Final:
  Task 12 (verification) ← depends on all
```

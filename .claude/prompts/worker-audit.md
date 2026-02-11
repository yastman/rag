W-AUDIT: Audit remediation CI + smoke tests (#91)

SKILLS (обязательно вызови):
1. /executing-plans — для пошагового выполнения задач
2. /verification-before-completion — после выполнения, перед финальным отчётом

ПЛАН: /repo/docs/plans/2026-02-11-audit-remediation-plan.md
Работай из /repo

ЗАДАЧИ (выполняй по плану):

Шаг 1: Консолидировать dev-зависимости в pyproject.toml
- Перенести уникальные пакеты из [dependency-groups].dev в [project.optional-dependencies].dev:
  pytest-timeout>=2.4.0, pytest-xdist>=3.8.0, telethon>=1.42.0
- Удалить [dependency-groups].dev секцию целиком (строки 391-399)
- uv lock

Шаг 2: Унифицировать CI в .github/workflows/ci.yml
- Строка 53 job test: заменить --group dev на --extra dev
- Строка 85 job baseline-compare: заменить --group dev на --frozen --extra dev

Шаг 3: Снять маркер legacy_api со smoke-тестов в tests/smoke/test_zoo_smoke.py
- Удалить @pytest.mark.legacy_api с TestZooCache (строка 135-136) и TestZooEndToEnd (строка 166-167)
- Добавить @pytest.mark.smoke к обоим классам
- Убрать алиас CacheService, использовать CacheLayerManager напрямую

Шаг 4: Верификация
- uv run pytest tests/smoke/test_zoo_smoke.py --collect-only -q
- uv run pytest tests/unit/ -q -x -m "not legacy_api" --timeout=30 2>&1 | tail -20

ТЕСТЫ (строго по файлам):
  uv run pytest tests/smoke/test_zoo_smoke.py --collect-only -q
  uv run pytest tests/unit/ -q -x -m "not legacy_api" --timeout=30 2>&1 | tail -20
- НЕ запускай tests/ целиком
- Маппинг:
  pyproject.toml -> uv lock (проверить что lockfile обновляется)
  .github/workflows/ci.yml -> нет тестов, проверь yaml синтаксис
  tests/smoke/test_zoo_smoke.py -> --collect-only

ПРАВИЛА:
1. git commit — ТОЛЬКО конкретные файлы. НЕ git add -A.
2. Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com> в каждом коммите.
3. Коммит: fix(ci): consolidate dev deps + remove legacy_api markers (#91)
4. ВАЖНО: pyproject.toml также меняется в #121 (redis version bump). Твоя область — секция [dependency-groups] и [project.optional-dependencies].dev. НЕ трогай версию redis.

ЛОГИРОВАНИЕ в /repo/logs/worker-audit.log (APPEND):
echo "[START] $(date +%H:%M:%S) Task: description" >> /repo/logs/worker-audit.log
echo "[DONE] $(date +%H:%M:%S) Task: result" >> /repo/logs/worker-audit.log
echo "[COMPLETE] $(date +%H:%M:%S) Worker finished" >> /repo/logs/worker-audit.log

WEBHOOK (после завершения ВСЕХ задач):
Выполни РОВНО ТРИ ОТДЕЛЬНЫХ вызова Bash tool (НЕ объединяй через && или ;):
Вызов 1: TMUX="" tmux send-keys -t "claude:2" "W-AUDIT COMPLETE — проверь logs/worker-audit.log"
Вызов 2: sleep 1
Вызов 3: TMUX="" tmux send-keys -t "claude:2" Enter

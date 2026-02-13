W-PREFLIGHT: Add dirty-worktree preflight guard to verification scripts #165

SKILLS (вызови В ЭТОМ ПОРЯДКЕ):
1. /executing-plans — для пошагового выполнения
2. /requesting-code-review — code review ПОСЛЕ завершения, ПЕРЕД коммитом. ВАЖНО: делай review САМОСТОЯТЕЛЬНО (без субагента) — просмотри git diff, проверь стиль, логику, тесты
3. /verification-before-completion — финальная проверка перед коммитом

ПЛАН: /home/user/projects/rag-fresh/docs/plans/2026-02-12-dev-setup-and-preflight-plan.md
Работай из /home/user/projects/rag-fresh. Ветка: feat/163-semantic-cache-isolation (текущая).

ЗАДАЧИ (выполняй Task 2 из плана):

1. Напиши тест tests/unit/test_preflight_worktree.py:
   - test_clean_worktree_passes: mock subprocess.run returncode=0, check_worktree_clean(strict=True) не бросает
   - test_dirty_worktree_strict_fails: mock returncode=1, check_worktree_clean(strict=True) бросает SystemExit
   - test_dirty_worktree_warn_only: mock returncode=1, check_worktree_clean(strict=False) логирует warning но не бросает

2. Запусти тест, убедись что FAIL (ImportError: cannot import name check_worktree_clean)

3. В scripts/validate_traces.py после функции check_langfuse_config (около строки 150) добавь:
   def check_worktree_clean(strict: bool = False) -> None:
       - subprocess.run(["git", "diff", "--quiet", "HEAD"], capture_output=True)
       - returncode != 0: dirty worktree detected
       - strict=True: logger.error + sys.exit(1)
       - strict=False: logger.warning only

4. В run_validation() (строка ~1093) после check_langfuse_config():
   - Добавь: check_worktree_clean(strict=args.strict_worktree)

5. В main() добавь CLI аргумент:
   parser.add_argument("--strict-worktree", action="store_true", default=False, help="Fail if git worktree is dirty")

6. Запусти тесты: uv run pytest tests/unit/test_preflight_worktree.py -v
   Expected: 3 PASS

7. В tests/baseline/cli.py добавь вызов check_worktree_clean(strict=False) перед compare командой
   import: from scripts.validate_traces import check_worktree_clean

8. Запусти lint: uv run ruff check scripts/validate_traces.py tests/unit/test_preflight_worktree.py tests/baseline/cli.py
   Запусти format: uv run ruff format --check scripts/validate_traces.py tests/unit/test_preflight_worktree.py tests/baseline/cli.py

MCP TOOLS:
- Не требуется для этой задачи (стандартный Python, subprocess, pytest)

ТЕСТЫ (строго по файлам):
- Запускай ТОЛЬКО: uv run pytest tests/unit/test_preflight_worktree.py -v
- НЕ запускай tests/ целиком, НЕ запускай tests/unit/ целиком
- Маппинг source -> test:
  scripts/validate_traces.py -> tests/unit/test_preflight_worktree.py
  tests/baseline/cli.py -> (нет отдельного теста, проверь import)

ПРАВИЛА:
1. git commit — ТОЛЬКО конкретные файлы: scripts/validate_traces.py tests/baseline/cli.py tests/unit/test_preflight_worktree.py
2. НЕ делай git add -A
3. НЕ трогай pyproject.toml, Makefile, ci.yml, uv.lock (параллельный воркер работает с ними)
4. Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com> в коммите
5. Сообщение коммита: fix(validation): add dirty-worktree preflight guard #165

ЛОГИРОВАНИЕ в /home/user/projects/rag-fresh/logs/worker-preflight.log (APPEND):
[START] timestamp Task 2: add preflight guard
[DONE] timestamp Task 2: result summary
[COMPLETE] timestamp Worker finished

WEBHOOK (после завершения ВСЕХ задач):
Выполни РОВНО ТРИ ОТДЕЛЬНЫХ вызова Bash tool (НЕ объединяй через && или ;):
Вызов 1: TMUX="" tmux send-keys -t "claude:ORCH" "W-PREFLIGHT COMPLETE — проверь logs/worker-preflight.log"
Вызов 2: sleep 1
Вызов 3: TMUX="" tmux send-keys -t "claude:ORCH" Enter
ВАЖНО: Три ОТДЕЛЬНЫХ вызова Bash tool. НЕ объединяй в одну команду.

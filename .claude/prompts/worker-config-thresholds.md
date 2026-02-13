W-CONFIG: Config-driven Go/No-Go thresholds (Tasks 1+2 from plan)

SKILLS (вызови В ЭТОМ ПОРЯДКЕ):
1. /executing-plans -- для пошагового выполнения задач
2. /requesting-code-review -- code review ПОСЛЕ каждой таски, ПЕРЕД коммитом. Делай review САМОСТОЯТЕЛЬНО (git diff, стиль, логика, тесты)
3. /verification-before-completion -- финальная проверка

ПЛАН: /home/user/projects/rag-fresh/docs/plans/2026-02-12-validation-thresholds-plan.md
Работай из /home/user/projects/rag-fresh. Ветка: fix/168-validation-thresholds (уже создана, ты в ней).

ЗАДАЧИ (выполняй по порядку):

== Task 1: Add go_no_go section to thresholds.yaml ==

1. Создай тест-файл tests/baseline/test_thresholds_schema.py -- проверяет наличие go_no_go секции, все ключи, позитивные значения, llm_factor >= 1.10
2. Запусти тест, убедись что FAIL (go_no_go секции нет)
3. Обнови tests/baseline/thresholds.yaml:
   - Измени calls.llm_factor: 1.05 -> 1.15 (комментарий: widened per #168)
   - Добавь секцию go_no_go с ключами: cold_p50_ms: 5000, cold_p90_ms: 8000, cold_over_10s_pct: 0.15, cache_hit_p50_ms: 1500, generate_p50_ms: 2000, multi_rewrite_pct: 0.10, rewrite_tokens_p50: 96, ttft_p50_ms: 1000, ttft_min_sample: 3
   - Обнови комментарий в шапке: "Based on official observability/eval guidance (Langfuse docs, Grafana/AWS SLO, Anthropic stats)"
4. Запусти тест, убедись что PASS
5. Коммит: feat(validation): add go_no_go config section and widen llm_factor to 1.15 #168

== Task 2: Load Go/No-Go thresholds from config in evaluate_go_no_go ==

1. Добавь тесты в tests/unit/test_validate_aggregates.py:
   - test_custom_cold_p50_threshold: передать thresholds={"cold_p50_ms": 7000}, latency 6000 -> PASS
   - test_custom_rewrite_tokens_threshold: передать thresholds={"rewrite_tokens_p50": 120}, tokens 110 -> PASS
   - test_default_thresholds_from_yaml: без thresholds, latency 4000 -> PASS (default 5000 из yaml)
   Используй существующий _make_result helper. Для rewrite_tokens тест: _make_result(phase="cold", scores={"rewrite_completion_tokens": 110.0}) -- добавь scores kwarg в _make_result если его нет.
2. Запусти новые тесты, убедись что FAIL
3. В scripts/validate_traces.py:
   a) Добавь import yaml (вверху файла, рядом с другими импортами)
   b) Добавь константу: GO_NO_GO_THRESHOLDS_PATH = Path(__file__).resolve().parent.parent / "tests" / "baseline" / "thresholds.yaml"
   c) Добавь helper-функцию _load_go_no_go_thresholds(custom=None) которая читает yaml, берет секцию go_no_go, мерджит с custom
   d) Обнови сигнатуру evaluate_go_no_go: добавь thresholds: dict[str, Any] | None = None
   e) В начале функции: t = _load_go_no_go_thresholds(thresholds)
   f) Замени все хардкод-значения на t.get(..., default):
      - cold_p50 < 5000 -> cold_p50 < t.get("cold_p50_ms", 5000)
      - cold_p90 < 8000 -> cold_p90 < t.get("cold_p90_ms", 8000)
      - pct_over_10s < 0.15 -> pct_over_10s < t.get("cold_over_10s_pct", 0.15)
      - cache_p50 < 1500 -> cache_p50 < t.get("cache_hit_p50_ms", 1500)
      - generate_p50 < 2000 -> generate_p50 < t.get("generate_p50_ms", 2000)
      - multi_rewrite_pct <= 0.10 -> multi_rewrite_pct <= t.get("multi_rewrite_pct", 0.10)
      - tokens_p50 <= 96 -> tokens_p50 <= t.get("rewrite_tokens_p50", 96)
      - ttft_n < 3 -> ttft_n < t.get("ttft_min_sample", 3)
      - ttft_p50 < 1000 -> ttft_p50 < t.get("ttft_p50_ms", 1000)
   g) Обнови target строки чтобы отражали актуальные значения из config
4. Запусти ВСЕ тесты evaluate_go_no_go:
   uv run pytest tests/unit/test_validate_aggregates.py -v -k "GoNoGo or go_no_go or custom_cold or custom_rewrite or default_thresholds"
5. Также запусти schema тесты: uv run pytest tests/baseline/test_thresholds_schema.py -v
6. Коммит: feat(validation): load Go/No-Go thresholds from config #168

ТЕСТЫ (строго по файлам):
- tests/baseline/thresholds.yaml -> tests/baseline/test_thresholds_schema.py
- scripts/validate_traces.py -> tests/unit/test_validate_aggregates.py
- Запускай ТОЛЬКО эти файлы. НЕ запускай tests/ целиком.
- Финальная проверка: uv run pytest tests/baseline/test_thresholds_schema.py tests/unit/test_validate_aggregates.py -v && uv run ruff check scripts/validate_traces.py tests/baseline/thresholds.yaml tests/baseline/test_thresholds_schema.py tests/unit/test_validate_aggregates.py && uv run ruff format --check scripts/validate_traces.py tests/baseline/test_thresholds_schema.py tests/unit/test_validate_aggregates.py

ПРАВИЛА:
1. git commit -- ТОЛЬКО конкретные файлы. НЕ git add -A.
2. Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com> в каждом коммите.
3. НЕ трогай секции generate_report, _format_go_no_go_status -- их делает другой воркер.
4. НЕ трогай REFERENCE_TRACE_ID -- его удаляет другой воркер.
5. НЕ добавляй stddev -- это делает другой воркер.

ЛОГИРОВАНИЕ в /home/user/projects/rag-fresh/logs/worker-config-thresholds.log (APPEND):
Перед каждым шагом: echo "[START] $(date +%H:%M:%S) Task N Step M: description" >> /home/user/projects/rag-fresh/logs/worker-config-thresholds.log
После каждого шага: echo "[DONE] $(date +%H:%M:%S) Task N Step M: result" >> /home/user/projects/rag-fresh/logs/worker-config-thresholds.log
В конце: echo "[COMPLETE] $(date +%H:%M:%S) W-CONFIG finished" >> /home/user/projects/rag-fresh/logs/worker-config-thresholds.log

WEBHOOK (после завершения ВСЕХ задач):
Выполни РОВНО ТРИ ОТДЕЛЬНЫХ вызова Bash tool (НЕ объединяй через && или ;):
Вызов 1: TMUX="" tmux send-keys -t "claude:ORCH" "W-CONFIG COMPLETE -- проверь logs/worker-config-thresholds.log"
Вызов 2: sleep 1
Вызов 3: TMUX="" tmux send-keys -t "claude:ORCH" Enter
ВАЖНО: Три ОТДЕЛЬНЫХ вызова Bash tool. НЕ объединяй в одну команду. Sleep 1 секунда.
ВАЖНО: Используй ИМЯ окна "claude:ORCH", НЕ индекс.

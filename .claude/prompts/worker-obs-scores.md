W-OBS: Memory observability scores in bot.py (Tasks 2, 4, 5 from plan)

SKILLS (обязательно вызови):
1. /executing-plans — для пошагового выполнения задач
2. /verification-before-completion — после выполнения, перед финальным отчётом

ПЛАН: /repo/docs/plans/2026-02-12-memory-observability-plan.md
Работай из /repo. Task 1 уже завершён (deferred, follow-up issue #162).

ЗАДАЧИ (выполняй по порядку, TDD: сначала падающий тест, потом минимальная реализация):

Task 2: Новые scores memory_messages_count + summarization_triggered
  - Файлы: telegram_bot/bot.py (line 145-148), tests/unit/test_bot_scores.py
  - Прочитай оба файла ПОЛНОСТЬЮ перед началом работы
  - Добавь "messages" key во все result dicts (FULL_PIPELINE_RESULT, CACHE_HIT_RESULT, CHITCHAT_RESULT)
  - Добавь "summarize" в FULL_PIPELINE_RESULT["latency_stages"]
  - Напиши TestMemoryScores class с 4 тестами (см. план Step 2)
  - Запусти тесты — убедись что FAIL
  - Реализуй scores в bot.py (см. план Step 4)
  - Обнови count assertions: 25 -> 27 scores
  - Запусти: uv run pytest tests/unit/test_bot_scores.py -v
  - Коммит: feat(observability): memory_messages_count + summarization_triggered scores #159

Task 4: checkpointer_overhead_proxy_ms score
  - Файлы: telegram_bot/bot.py, tests/unit/test_bot_scores.py
  - Напиши test_compute_checkpointer_overhead_proxy_ms (helper function test)
  - Напиши test_checkpointer_overhead_proxy_score_written (score emission test)
  - Запусти тесты — убедись что FAIL
  - Реализуй _compute_checkpointer_overhead_proxy_ms helper в bot.py
  - Оберни graph.ainvoke() в handle_query и handle_voice с time.perf_counter()
  - Добавь score emission в _write_langfuse_scores
  - Обнови count assertions: 27 -> 28 scores
  - Запусти: uv run pytest tests/unit/test_bot_scores.py -v
  - Коммит: feat(observability): add checkpointer_overhead_proxy_ms score #159

Task 5: memory fields в trace metadata
  - Файлы: telegram_bot/bot.py (line 166-185), tests/unit/test_bot_scores.py
  - Напиши test_trace_metadata_contains_memory_and_overhead в TestVoiceTraceMetadata
  - Запусти тест — убедись что FAIL
  - Добавь memory_messages_count и checkpointer_overhead_proxy_ms в _build_trace_metadata()
  - Запусти: uv run pytest tests/unit/test_bot_scores.py -v
  - Коммит: feat(observability): add memory + overhead fields to trace metadata #159

MCP TOOLS (используй ПЕРЕД реализацией):
- Context7: resolve-library-id(libraryName, query) затем query-docs(libraryId, query) для актуальной документации SDK/API
- Exa: web_search_exa(query) или get_code_context_exa(query) для поиска решений, примеров кода, свежих best practices

ТЕСТЫ (строго по файлам):
- Запускай ТОЛЬКО: uv run pytest tests/unit/test_bot_scores.py -v
- НЕ запускай tests/ целиком, НЕ запускай tests/unit/ целиком
- Используй --lf для перезапуска только упавших
- Маппинг: telegram_bot/bot.py -> tests/unit/test_bot_scores.py
- Финальная проверка: uv run pytest tests/unit/test_bot_scores.py -v && uv run ruff check telegram_bot/bot.py tests/unit/test_bot_scores.py

ПРАВИЛА:
1. git commit — ТОЛЬКО конкретные файлы (git add telegram_bot/bot.py tests/unit/test_bot_scores.py). НЕ git add -A.
2. Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com> в каждом коммите.
3. capture_input=False, capture_output=False на всех @observe (payload bloat prevention)
4. НЕ трогать memory.py — InstrumentedAsyncRedisSaver deferred
5. Conventional commits: feat(observability): ... #159

ЛОГИРОВАНИЕ в /repo/logs/worker-obs-scores.log (APPEND):
В начале каждого Task: echo "[START] $(date +%H:%M:%S) Task N: description" >> /repo/logs/worker-obs-scores.log
По завершении Task: echo "[DONE] $(date +%H:%M:%S) Task N: result" >> /repo/logs/worker-obs-scores.log
После всех задач: echo "[COMPLETE] $(date +%H:%M:%S) Worker finished" >> /repo/logs/worker-obs-scores.log

WEBHOOK (после завершения ВСЕХ задач):
Выполни РОВНО ТРИ ОТДЕЛЬНЫХ вызова Bash tool (НЕ объединяй через && или ;):
Вызов 1: TMUX="" tmux send-keys -t "claude:Claude" "W-OBS COMPLETE — проверь logs/worker-obs-scores.log"
Вызов 2: sleep 1
Вызов 3: TMUX="" tmux send-keys -t "claude:Claude" Enter
ВАЖНО: Используй ИМЯ окна "Claude", НЕ индекс. Индекс сдвигается при kill-window.

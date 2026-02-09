W-SMOKE-FIX: Починить 8 failed smoke тестов — добавить skipIf для missing services

Работай из /repo
GitHub Issue: #44 — Task 8 fix

8 smoke тестов падают потому что сервисы не запущены (не в core profile).
Нужно добавить pytest.mark.skipif с проверкой доступности сервиса.

Фейлы:
1. test_mlflow_health — MLflow не запущен (port 5000)
2. test_lightrag_health — LightRAG не запущен (port 9621)
3. test_langfuse_health — Langfuse не запущен (port 3001)
4. test_llm_api_health — LiteLLM endpoint 404 (wrong path)
5. test_litellm_health — LiteLLM не запущен (port 4000)
6. test_user_base_health — returns "healthy" not "ok"
7. test_generate_preflight_report — quantization_config=None
8. test_quantization_latency_comparison — flaky timing (59ms vs 9ms)

Шаги:

1. Прочитай tests/smoke/test_smoke_services.py
2. Прочитай tests/smoke/test_zoo_smoke.py
3. Прочитай tests/smoke/test_preflight.py
4. Для каждого фейла:
   - Если сервис не в core profile — добавь skipIf с socket check или пометь pytest.mark.skip(reason="requires X service")
   - Если wrong assertion (user_base "healthy" vs "ok") — исправь assertion
   - Если flaky timing — увеличь threshold или пометь xfail
   - Если wrong endpoint — исправь URL
5. Запусти: uv run pytest tests/smoke/ -v --tb=short (Docker services должны быть UP)
6. Убедись что skip/pass для всех

После успеха:
- git add все изменённые smoke файлы
- git commit -m "fix(tests): repair smoke tests — skip missing services, fix assertions

8 smoke tests fixed: skip MLflow/LightRAG/Langfuse when not running,
fix user_base health assertion, increase latency threshold.

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"

Логирование в /repo/logs/worker-smoke-fix.log (APPEND):
[START] timestamp
[DONE] timestamp
[COMPLETE] timestamp

Webhook:
TMUX="" tmux send-keys -t "claude:1" "W-SMOKE-FIX COMPLETE"
sleep 0.5
TMUX="" tmux send-keys -t "claude:1" Enter

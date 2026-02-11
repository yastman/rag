W-SCORES: Langfuse error spans in 4 nodes (#103 P1.2)

SKILLS (обязательно вызови):
1. /executing-plans — для пошагового выполнения задач
2. /verification-before-completion — после выполнения, перед финальным отчётом

ПЛАН: /home/user/projects/rag-fresh/docs/plans/2026-02-11-langfuse-scores-plan.md
Работай из /home/user/projects/rag-fresh
P1.1 уже DONE. Делай ТОЛЬКО P1.2 (Error Span Tracking).

ЗАДАЧИ:

Шаг 1: generate_node — error span на LLM failure
- telegram_bot/graph/nodes/generate.py: строки 280 (streaming fallback WARNING) и 301 (LLM fail ERROR)
- Добавить get_client в import из telegram_bot.observability
- В except блоках: get_client().update_current_span(level="ERROR", status_message=...)

Шаг 2: rewrite_node — error span на LLM rewrite failure
- telegram_bot/graph/nodes/rewrite.py: строка 79
- Добавить get_client в import, update_current_span(level="ERROR")

Шаг 3: rerank_node — error span на ColBERT failure
- telegram_bot/graph/nodes/rerank.py: строка 79
- Добавить get_client в import, update_current_span(level="ERROR")

Шаг 4: respond_node — error span на Telegram send failure
- telegram_bot/graph/nodes/respond.py: строка 49
- Добавить get_client в import, update_current_span(level="ERROR")

Шаг 5: Unit тесты — tests/unit/graph/test_error_spans.py (новый файл)
- 4 теста: generate, rewrite, rerank, respond error paths
- Mock get_client, verify update_current_span called with level="ERROR"

Шаг 6: ruff check + ruff format

ТЕСТЫ (строго по файлам):
  uv run pytest tests/unit/graph/test_error_spans.py -v
  uv run pytest tests/unit/graph/test_generate_node.py tests/unit/graph/test_rewrite_node.py -v
- Маппинг:
  generate.py -> tests/unit/graph/test_generate_node.py + test_error_spans.py
  rewrite.py -> tests/unit/graph/test_rewrite_node.py + test_error_spans.py
  rerank.py -> test_error_spans.py
  respond.py -> test_error_spans.py
- ВАЖНО: generate.py и rewrite.py ТАКЖЕ будут меняться в #124 (TTFT). Твоя область — ТОЛЬКО except блоки (error spans). НЕ трогай основной flow, return dict, imports кроме get_client.

ПРАВИЛА:
1. git commit — ТОЛЬКО конкретные файлы. НЕ git add -A.
2. Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com> в каждом коммите.
3. Коммит: feat(observability): add error spans to generate/rewrite/rerank/respond (#103)

ЛОГИРОВАНИЕ в /home/user/projects/rag-fresh/logs/worker-scores.log (APPEND):
echo "[START] $(date +%H:%M:%S) Step N: description" >> /home/user/projects/rag-fresh/logs/worker-scores.log
echo "[DONE] $(date +%H:%M:%S) Step N: result" >> /home/user/projects/rag-fresh/logs/worker-scores.log
echo "[COMPLETE] $(date +%H:%M:%S) Worker finished" >> /home/user/projects/rag-fresh/logs/worker-scores.log

WEBHOOK (после завершения ВСЕХ задач):
Выполни РОВНО ТРИ ОТДЕЛЬНЫХ вызова Bash tool (НЕ объединяй через && или ;):
Вызов 1: TMUX="" tmux send-keys -t "claude:3" "W-SCORES COMPLETE — проверь logs/worker-scores.log"
Вызов 2: sleep 1
Вызов 3: TMUX="" tmux send-keys -t "claude:3" Enter

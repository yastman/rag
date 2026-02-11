W-TTFT: TTFT variance + provider metadata (#124)

SKILLS (обязательно вызови):
1. /executing-plans — для пошагового выполнения задач
2. /verification-before-completion — после выполнения, перед финальным отчётом

ПЛАН: /home/user/projects/rag-fresh/docs/plans/2026-02-11-ttft-variance-plan.md
Работай из /home/user/projects/rag-fresh

ЗАДАЧИ (выполняй по плану):

Шаг 1: Добавить поля в RAGState (state.py)
- llm_provider_model: str, llm_ttft_ms: float, llm_response_duration_ms: float
- Добавить в make_initial_state с дефолтами

Шаг 2: Извлечь provider metadata в generate_node — non-streaming path
- generate.py: после response = await ... добавить actual_model = getattr(response, "model", config.llm_model)
- Добавить в return dict: llm_provider_model, llm_ttft_ms, llm_response_duration_ms

Шаг 3: Извлечь TTFT в generate_node — streaming path
- _generate_streaming: замерить time.monotonic() до первого chunk
- Извлечь chunk.model
- Вернуть (answer, actual_model, ttft_ms)

Шаг 4: Обработать fallback пути
- StreamingPartialDeliveryError: извлечь response.model из non-streaming fallback
- Exception: actual_model = "fallback", ttft_ms = 0.0

Шаг 5: Извлечь provider metadata в rewrite_node (rewrite.py)
- actual_model = getattr(response, "model", ...)
- НЕ перезаписывать llm_provider_model — записать в latency_stages или отдельным trace metadata

Шаг 6: Добавить Langfuse scores в bot.py
- llm_ttft_ms и llm_response_duration_ms в _write_langfuse_scores
- llm_provider_model в update_current_trace metadata

Шаг 7: Unit тесты
- test_generate_non_streaming_captures_provider_model
- test_generate_streaming_captures_ttft
- test_generate_fallback_sets_fallback_model

Шаг 8: Обновить .claude/rules/observability.md — добавить 2 новых score

MCP TOOLS:
- Context7: resolve-library-id("openai", "response headers model field") для проверки API
- Exa: get_code_context_exa("openai python response.model litellm provider") для примеров

ТЕСТЫ (строго по файлам):
  uv run pytest tests/unit/graph/test_generate_node.py tests/unit/test_bot_handlers.py -v
- Маппинг:
  telegram_bot/graph/nodes/generate.py -> tests/unit/graph/test_generate_node.py
  telegram_bot/graph/nodes/rewrite.py -> tests/unit/graph/test_rewrite_node.py (если есть)
  telegram_bot/bot.py -> tests/unit/test_bot_handlers.py
  telegram_bot/graph/state.py -> косвенно через test_generate_node.py
- ВАЖНО: generate.py уже изменён в #103 (error spans в except блоках). НЕ трогай error span код (get_client().update_current_span). Твоя область — основной flow: response.model, TTFT замер, return dict.
- ВАЖНО: state.py уже изменён в #108 (score_improved field). Добавляй llm_* поля ПОСЛЕ score_improved.

ПРАВИЛА:
1. git commit — ТОЛЬКО конкретные файлы. НЕ git add -A.
2. Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com> в каждом коммите.
3. Коммит: feat(observability): add provider metadata + TTFT tracking (#124)

ЛОГИРОВАНИЕ в /home/user/projects/rag-fresh/logs/worker-ttft.log (APPEND):
echo "[START] $(date +%H:%M:%S) Step N: description" >> /home/user/projects/rag-fresh/logs/worker-ttft.log
echo "[DONE] $(date +%H:%M:%S) Step N: result" >> /home/user/projects/rag-fresh/logs/worker-ttft.log
echo "[COMPLETE] $(date +%H:%M:%S) Worker finished" >> /home/user/projects/rag-fresh/logs/worker-ttft.log

WEBHOOK (после завершения ВСЕХ задач):
Выполни РОВНО ТРИ ОТДЕЛЬНЫХ вызова Bash tool (НЕ объединяй через && или ;):
Вызов 1: TMUX="" tmux send-keys -t "claude:3" "W-TTFT COMPLETE — проверь logs/worker-ttft.log"
Вызов 2: sleep 1
Вызов 3: TMUX="" tmux send-keys -t "claude:3" Enter

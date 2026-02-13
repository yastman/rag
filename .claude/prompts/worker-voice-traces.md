# Worker: Voice Trace Gaps (#158)

## ЗАДАЧА

Выполни план `docs/plans/2026-02-12-voice-trace-gaps-plan.md` — 5 задач по фиксу Langfuse трейсинга для voice pipeline.

Ветка уже создана: `fix/voice-trace-gaps-158`

## КОНТЕКСТ

Issue #158: voice transcription (issue #151) имеет 3 гэпа в Langfuse:
1. **Metadata gap** — `handle_voice` пишет 4 поля в trace metadata, `handle_query` — 12 полей
2. **Payload bloat** — `transcribe_node` не имеет `capture_input=False`, bytes утекают в Langfuse
3. **Test gap** — нет теста на voice-specific scores (`stt_duration_ms`, `voice_duration_s`)

## КЛЮЧЕВЫЕ ФАЙЛЫ

| Файл | Что менять |
|------|-----------|
| `telegram_bot/bot.py` | Extract `_build_trace_metadata()` helper, использовать в обоих handlers |
| `telegram_bot/graph/nodes/transcribe.py` | `capture_input=False, capture_output=False` + curated span |
| `tests/unit/test_bot_scores.py` | Добавить `TestVoiceTraceMetadata` + `TestVoiceScores` |
| `tests/unit/graph/test_transcribe_node.py` | Добавить `test_transcribe_writes_curated_span` |
| `.claude/rules/observability.md` | Добавить transcribe в таблицу curated spans |

## ПАТТЕРН (reference)

Curated span pattern из `telegram_bot/graph/nodes/retrieve.py:22,59-68`:

```python
@observe(name="node-retrieve", capture_input=False, capture_output=False)
async def retrieve_node(state, ...):
    lf = get_client()
    lf.update_current_span(input={"query_preview": query[:120], ...})
    # ... logic ...
    lf.update_current_span(output={"results_count": len(results), ...})
```

**Forbidden keys** в curated spans: `documents`, `query_embedding`, `sparse_embedding`, `state`, `messages`, `voice_audio`.

## ПОРЯДОК ВЫПОЛНЕНИЯ

1. `/executing-plans` — загрузи план из `docs/plans/2026-02-12-voice-trace-gaps-plan.md`
2. TDD: сначала failing test, потом implementation
3. Commit после каждой задачи
4. Task 5 — финальный lint + full test suite

## SKILLS

- `/executing-plans` — основной workflow
- `/test-driven-development` — RED → GREEN → REFACTOR
- `/verification-before-completion` — `make check && make test-unit` перед финальным коммитом

## MCP TOOLS

- **Context7**: ПЕРЕД реализацией внешних SDK/API используй MCP Context7 (`resolve-library-id` → `query-docs`) для актуальной документации Langfuse SDK v3
- **Exa**: Для поиска решений, примеров кода, свежих best practices используй MCP Exa (`web_search_exa`, `get_code_context_exa`)

## ПРОВЕРКА ФИНАЛЬНАЯ

```bash
uv run ruff check telegram_bot/bot.py telegram_bot/graph/nodes/transcribe.py --fix
uv run ruff format telegram_bot/bot.py telegram_bot/graph/nodes/transcribe.py
uv run mypy telegram_bot/bot.py telegram_bot/graph/nodes/transcribe.py
uv run pytest tests/unit/test_bot_scores.py tests/unit/graph/test_transcribe_node.py -v
uv run pytest tests/integration/test_graph_paths.py -v
```

Все тесты должны пройти.

ЛОГИРОВАНИЕ в /home/user/projects/rag-fresh/logs/worker-voice-traces.log (APPEND):
[START] timestamp Task N: description
[DONE] timestamp Task N: result
[COMPLETE] timestamp Worker finished

WEBHOOK (после завершения ВСЕХ задач):
Выполни РОВНО ТРИ ОТДЕЛЬНЫХ вызова Bash tool (НЕ объединяй через && или ;):
Вызов 1: TMUX="" tmux send-keys -t "claude:RAG" "W-VOICE-TRACES COMPLETE — проверь logs/worker-voice-traces.log"
Вызов 2: sleep 1
Вызов 3: TMUX="" tmux send-keys -t "claude:RAG" Enter
ВАЖНО: Используй ИМЯ окна (RAG), НЕ индекс. Три ОТДЕЛЬНЫХ вызова Bash tool.
